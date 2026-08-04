from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .asr import MockAsrProvider
from .audio import WavRecorder
from .config import get_settings
from .database import Database
from .realtime import MonitorHub
from .schemas import SessionCreate, SessionDetail, SessionSummary

settings = get_settings()
database = Database(settings.database_path)
monitor_hub = MonitorHub()
active_audio_sessions: set[str] = set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "asr_provider": settings.asr_provider,
    }


@app.post("/api/sessions", response_model=SessionSummary, status_code=201)
def create_session(payload: SessionCreate):
    return database.create_session(payload)


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions():
    return database.list_sessions()


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str):
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="直播场次不存在")
    return {
        **session,
        "transcripts": database.list_transcripts(session_id),
    }


@app.post("/api/sessions/{session_id}/end", response_model=SessionSummary)
async def end_session(session_id: str):
    session = database.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="直播场次不存在")
    await monitor_hub.broadcast(
        session_id,
        {"type": "session", "payload": session},
    )
    return session


@app.get("/api/sessions/{session_id}/audio")
def get_audio(session_id: str):
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="直播场次不存在")
    if not session["audio_path"]:
        raise HTTPException(status_code=404, detail="该场次暂无录音")
    audio_path = Path(session["audio_path"])
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="录音文件不存在")
    return FileResponse(audio_path, media_type="audio/wav", filename=f"{session_id}.wav")


@app.websocket("/ws/monitor/{session_id}")
async def monitor_socket(websocket: WebSocket, session_id: str):
    if not database.get_session(session_id):
        await websocket.close(code=4404, reason="session not found")
        return
    await monitor_hub.connect(session_id, websocket)
    try:
        await websocket.send_json(
            {
                "type": "session",
                "payload": database.get_session(session_id),
            }
        )
        await websocket.send_json(
            {
                "type": "audio_status",
                "payload": {
                    "connected": session_id in active_audio_sessions,
                    "message": (
                        "Windows采集助手已连接"
                        if session_id in active_audio_sessions
                        else "等待Windows采集助手连接"
                    ),
                },
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await monitor_hub.disconnect(session_id, websocket)


@app.websocket("/ws/audio/{session_id}")
async def audio_socket(websocket: WebSocket, session_id: str):
    session = database.get_session(session_id)
    if not session:
        await websocket.close(code=4404, reason="session not found")
        return
    if session_id in active_audio_sessions:
        await websocket.close(code=4409, reason="audio collector already connected")
        return

    await websocket.accept()
    active_audio_sessions.add(session_id)
    database.set_session_live(session_id)
    output_path = settings.storage_root / "audio" / f"{session_id}.wav"
    recorder = WavRecorder(output_path)
    recorder.open()
    database.set_audio_path(session_id, str(output_path.resolve()))
    asr = MockAsrProvider()

    async def on_transcript(
        text: str,
        start_ms: int,
        end_ms: int,
        is_final: bool,
    ) -> None:
        item = database.add_transcript(
            session_id,
            text,
            start_ms,
            end_ms,
            is_final,
        )
        await monitor_hub.broadcast(
            session_id,
            {"type": "transcript", "payload": item},
        )

    await asr.start(on_transcript)
    await monitor_hub.broadcast(
        session_id,
        {
            "type": "session",
            "payload": database.get_session(session_id),
        },
    )
    await monitor_hub.broadcast(
        session_id,
        {
            "type": "audio_status",
            "payload": {"connected": True, "message": "Windows采集助手已连接"},
        },
    )
    try:
        while True:
            message = await websocket.receive()
            chunk = message.get("bytes")
            if chunk:
                recorder.write(chunk)
                await asr.send_audio(chunk)
            elif message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        database.end_session(session_id, failed=True)
        await monitor_hub.broadcast(
            session_id,
            {
                "type": "warning",
                "payload": {"message": f"音频通道异常：{type(exc).__name__}"},
            },
        )
    finally:
        recorder.close()
        await asr.close()
        active_audio_sessions.discard(session_id)
        await monitor_hub.broadcast(
            session_id,
            {
                "type": "audio_status",
                "payload": {"connected": False, "message": "Windows采集助手已断开"},
            },
        )
