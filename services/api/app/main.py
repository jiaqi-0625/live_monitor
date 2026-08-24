import asyncio
import logging
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from imageio_ffmpeg import get_ffmpeg_exe

from .ai_analysis import (
    analyze_session_review,
    analyze_with_llm,
    condense_corpus_markdown,
    normalize_metrics,
)
from .ai_config import (
    AI_CONFIG_PURPOSES,
    ApiKeyCipher,
    ResolvedAiConfig,
    fetch_available_models,
    resolve_ai_config,
    test_ai_connection,
)
from .asr import create_asr_provider
from .audio import Pcm16SignalMonitor, WavRecorder
from .auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from .config import get_settings
from .corpus_files import CorpusFileError, parse_corpus_file, split_corpus_text
from .corpus_retrieval import corpus_retrieval_log_payload, retrieve_corpus_context
from .database import Database
from .live_source import (
    LiveSourceAuthError,
    LiveSourceOfflineError,
    UnsupportedLiveUrlError,
    probe_live_source,
    resolve_live_source,
)
from .realtime import MonitorHub
from .schemas import (
    AiConfigProbe,
    AiConfigTestResult,
    AiConfigUpdate,
    AiConfigView,
    AiModelsResult,
    AudioSourceStatus,
    CorpusEntry,
    CorpusEntryCreate,
    CorpusEntryUpdate,
    CorpusImportFailure,
    CorpusImportResult,
    LiveDashboard,
    LiveSourceProbeResult,
    LoginInput,
    MetricCapture,
    MetricSnapshot,
    MultiRoomOverview,
    RegisterInput,
    ReviewGenerationStatus,
    SessionCreate,
    SessionDetail,
    SessionReview,
    SessionSummary,
    UserAdminUpdate,
    UserProfile,
)

settings = get_settings()
database = Database(settings.database_path)
monitor_hub = MonitorHub()
logger = logging.getLogger(__name__)
active_audio_sessions: set[str] = set()
audio_session_states: dict[str, dict] = {}
direct_ingest_tasks: dict[str, asyncio.Task[None]] = {}
direct_ingest_processes: dict[str, asyncio.subprocess.Process] = {}
ai_analysis_tasks: dict[str, asyncio.Task[None]] = {}
last_ai_analysis_at: dict[str, float] = {}
session_review_tasks: dict[str, asyncio.Task[None]] = {}


def compatibility_admin() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": "compatibility-admin",
        "username": "compatibility-admin",
        "display_name": "兼容模式管理员",
        "role": "admin",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }


def get_current_user(request: Request) -> dict:
    if not settings.auth_required:
        return compatibility_admin()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = database.get_user_by_session(hash_session_token(token))
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="账号当前不可用")
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return current_user


AdminUser = Annotated[dict, Depends(require_admin)]


def get_accessible_session(session_id: str, current_user: dict) -> dict:
    session = database.get_session(session_id)
    if not session or (
        current_user["role"] != "admin"
        and session.get("owner_user_id") != current_user["id"]
    ):
        raise HTTPException(status_code=404, detail="直播场次不存在")
    return session


def idle_audio_status() -> dict:
    return {
        "active": False,
        "connected": False,
        "source": None,
        "message": "等待链接监听、浏览器扩展或Windows采集助手",
    }


def get_audio_status(session_id: str) -> dict:
    return audio_session_states.get(session_id, idle_audio_status())


async def set_audio_status(
    session_id: str,
    *,
    active: bool,
    connected: bool,
    source: str | None,
    message: str,
) -> dict:
    payload = {
        "active": active,
        "connected": connected,
        "source": source,
        "message": message,
    }
    if active:
        audio_session_states[session_id] = payload
    else:
        audio_session_states.pop(session_id, None)
    await monitor_hub.broadcast(
        session_id,
        {"type": "audio_status", "payload": payload},
    )
    return payload


def create_transcript_callback(session_id: str):
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
        if is_final and text.strip():
            schedule_ai_analysis(session_id)

    return on_transcript


async def terminate_process(process: asyncio.subprocess.Process | None) -> None:
    if not process or process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()


async def run_direct_live_ingest(session_id: str, live_url: str) -> None:
    process: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task[bytes] | None = None
    feeder_task: asyncio.Task[None] | None = None
    stream_io = None
    asr = None
    output_path = settings.storage_root / "audio" / f"{session_id}.wav"
    recorder = WavRecorder(output_path)
    final_message = "链接监听已停止"
    stream_finished = False
    session_went_live = False

    try:
        await set_audio_status(
            session_id,
            active=True,
            connected=False,
            source="live_url",
            message="正在解析直播流并连接音频",
        )
        autoengine_cookie = (
            settings.autoengine_cookie.get_secret_value()
            if settings.autoengine_cookie
            else None
        )
        resolved = await asyncio.wait_for(
            asyncio.to_thread(
                resolve_live_source,
                live_url,
                "best",
                autoengine_cookie,
            ),
            timeout=25,
        )
        asr = create_asr_provider(settings)
        stream_io = await asyncio.to_thread(resolved.stream.open)
        process = await asyncio.create_subprocess_exec(
            get_ffmpeg_exe(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        direct_ingest_processes[session_id] = process
        if not process.stdin or not process.stdout or not process.stderr:
            raise RuntimeError("FFmpeg音频管道启动失败")
        stderr_task = asyncio.create_task(process.stderr.read())

        async def feed_stream() -> None:
            try:
                while True:
                    data = await asyncio.to_thread(stream_io.read, 64 * 1024)
                    if not data:
                        break
                    process.stdin.write(data)
                    await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with suppress(BrokenPipeError, ConnectionResetError):
                    if process.stdin.can_write_eof():
                        process.stdin.write_eof()
                    process.stdin.close()
                    await process.stdin.wait_closed()

        feeder_task = asyncio.create_task(feed_stream())

        recorder.open()
        database.set_audio_path(session_id, str(output_path.resolve()))
        await asr.start(create_transcript_callback(session_id))
        session = database.set_session_live(session_id)
        session_went_live = True
        await monitor_hub.broadcast(
            session_id,
            {"type": "session", "payload": session},
        )

        connected = False
        while True:
            chunk = await process.stdout.read(3200)
            if not chunk:
                break
            if not connected:
                connected = True
                await set_audio_status(
                    session_id,
                    active=True,
                    connected=True,
                    source="live_url",
                    message=f"正在监听直播链接（{resolved.quality}）",
                )
            recorder.write(chunk)
            await asr.send_audio(chunk)

        return_code = await process.wait()
        if feeder_task:
            await feeder_task
        error_text = ""
        if stderr_task:
            error_text = (await stderr_task).decode("utf-8", errors="ignore").strip()
        if not connected:
            detail = error_text[-300:] if error_text else f"退出码 {return_code}"
            raise RuntimeError(f"未读取到直播音频：{detail}")
        if return_code != 0:
            detail = error_text[-300:] if error_text else f"退出码 {return_code}"
            raise RuntimeError(f"直播音频管道异常：{detail}")

        stream_finished = True
        final_message = "直播流已结束，链接监听自动停止"
        ended = database.end_session(session_id)
        await monitor_hub.broadcast(
            session_id,
            {"type": "session", "payload": ended},
        )
    except asyncio.CancelledError:
        raise
    except (
        LiveSourceAuthError,
        UnsupportedLiveUrlError,
        LiveSourceOfflineError,
        TimeoutError,
    ) as exc:
        final_message = str(exc) or "直播流连接超时"
        logger.warning("Direct live ingest unavailable for %s: %s", session_id, exc)
        await monitor_hub.broadcast(
            session_id,
            {"type": "session", "payload": database.get_session(session_id)},
        )
        await monitor_hub.broadcast(
            session_id,
            {"type": "warning", "payload": {"message": final_message}},
        )
    except Exception as exc:
        final_message = f"链接监听异常：{exc}"
        logger.exception("Direct live ingest failed for %s", session_id)
        session = (
            database.end_session(session_id, failed=True)
            if session_went_live
            else database.get_session(session_id)
        )
        await monitor_hub.broadcast(
            session_id,
            {"type": "session", "payload": session},
        )
        await monitor_hub.broadcast(
            session_id,
            {"type": "warning", "payload": {"message": final_message}},
        )
    finally:
        if stream_io:
            with suppress(Exception):
                await asyncio.to_thread(stream_io.close)
        if feeder_task and not feeder_task.done():
            feeder_task.cancel()
            with suppress(asyncio.CancelledError):
                await feeder_task
        await terminate_process(process)
        if stderr_task and not stderr_task.done():
            stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await stderr_task
        recorder.close()
        if asr:
            with suppress(Exception):
                await asr.close()
        direct_ingest_processes.pop(session_id, None)
        active_audio_sessions.discard(session_id)
        await set_audio_status(
            session_id,
            active=False,
            connected=False,
            source=None,
            message=final_message,
        )
        if stream_finished:
            await monitor_hub.broadcast(
                session_id,
                {"type": "warning", "payload": {"message": final_message}},
            )


def remove_direct_ingest_task(
    session_id: str,
    task: asyncio.Task[None],
) -> None:
    if direct_ingest_tasks.get(session_id) is task:
        direct_ingest_tasks.pop(session_id, None)


async def stop_direct_ingest(session_id: str) -> bool:
    task = direct_ingest_tasks.get(session_id)
    if not task:
        return False
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    return True


async def run_ai_analysis(session_id: str) -> None:
    try:
        session = database.get_session(session_id)
        if not session:
            return
        metric_records = database.latest_metrics(session_id)
        normalized: dict[str, float] = {}
        for record in metric_records:
            normalized.update(record["normalized"])
            normalized.update(
                normalize_metrics(record["payload"], record["endpoint"])
            )
        transcripts = database.list_transcripts(session_id)
        corpus_entries = retrieve_corpus_context(
            database.list_corpus_entries(
                session["operator_name"],
                enabled_only=True,
                owner_user_id=session.get("owner_user_id"),
            ),
            session=session,
            normalized_metrics=normalized,
            transcripts=transcripts,
            mode="realtime",
        )
        logger.info(
            "Realtime corpus retrieval for %s: %s",
            session_id,
            corpus_retrieval_log_payload(corpus_entries),
        )
        ai_config = resolve_ai_config(database, settings, "realtime")
        result = await asyncio.to_thread(
            analyze_with_llm,
            ai_config.as_settings(settings),
            [record["payload"] for record in metric_records],
            normalized,
            transcripts,
            corpus_entries,
        )
        insight = database.add_ai_insight(
            session_id,
            risk_level=result.risk_level,
            summary=result.summary,
            signals=result.signals,
            actions=result.actions,
            talk_track=result.talk_track,
            model=result.model,
        )
        await monitor_hub.broadcast(
            session_id,
            {"type": "ai_insight", "payload": insight},
        )
    except Exception as exc:
        logger.warning("AI analysis failed for %s: %s", session_id, exc)
        await monitor_hub.broadcast(
            session_id,
            {
                "type": "warning",
                "payload": {"message": f"AI实时分析暂不可用：{exc}"},
            },
        )


async def run_scheduled_ai_analysis(session_id: str, delay: float) -> None:
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        last_ai_analysis_at[session_id] = time.monotonic()
        await run_ai_analysis(session_id)
    finally:
        ai_analysis_tasks.pop(session_id, None)


def schedule_ai_analysis(session_id: str) -> None:
    ai_config = resolve_ai_config(database, settings, "realtime")
    if not ai_config.configured or session_id in ai_analysis_tasks:
        return
    now = time.monotonic()
    last_run = last_ai_analysis_at.get(session_id, 0)
    delay = max(
        0.0,
        settings.llm_analysis_interval_seconds - (now - last_run),
    )
    task = asyncio.create_task(
        run_scheduled_ai_analysis(session_id, delay),
        name=f"ai-analysis-{session_id}",
    )
    ai_analysis_tasks[session_id] = task


def collect_normalized_metrics(session_id: str) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for record in database.latest_metrics(session_id, limit=200):
        normalized.update(record["normalized"])
        normalized.update(normalize_metrics(record["payload"], record["endpoint"]))
    return normalized


async def run_session_review(session_id: str) -> None:
    try:
        session = database.get_session(session_id)
        if not session:
            return
        metrics = collect_normalized_metrics(session_id)
        transcripts = database.list_transcripts(session_id)
        corpus_entries = retrieve_corpus_context(
            database.list_corpus_entries(
                session["operator_name"],
                enabled_only=True,
                owner_user_id=session.get("owner_user_id"),
            ),
            session=session,
            normalized_metrics=metrics,
            transcripts=transcripts,
            mode="review",
        )
        logger.info(
            "Review corpus retrieval for %s: %s",
            session_id,
            corpus_retrieval_log_payload(corpus_entries),
        )
        ai_config = resolve_ai_config(database, settings, "realtime")
        result = await asyncio.to_thread(
            analyze_session_review,
            ai_config.as_settings(settings),
            session,
            metrics,
            transcripts,
            corpus_entries,
        )
        database.upsert_session_review(
            session_id,
            status="completed",
            summary=result.summary,
            metric_summary=result.metric_summary,
            highlights=result.highlights,
            issues=result.issues,
            actions=result.actions,
            key_metrics=metrics,
            model=result.model,
        )
    except Exception as exc:
        logger.warning("Session review failed for %s: %s", session_id, exc)
        database.upsert_session_review(
            session_id,
            status="failed",
            error=str(exc),
            model=resolve_ai_config(database, settings, "realtime").model,
        )
    finally:
        session_review_tasks.pop(session_id, None)


def schedule_session_review(session_id: str) -> None:
    ai_config = resolve_ai_config(database, settings, "realtime")
    if not ai_config.configured or session_id in session_review_tasks:
        return
    database.upsert_session_review(
        session_id,
        status="pending",
        model=ai_config.model,
    )
    task = asyncio.create_task(
        run_session_review(session_id),
        name=f"session-review-{session_id}",
    )
    session_review_tasks[session_id] = task


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    bootstrap_password = (
        settings.bootstrap_admin_password.get_secret_value()
        if settings.bootstrap_admin_password
        else ""
    )
    if settings.bootstrap_admin_username.strip() and bootstrap_password:
        database.ensure_admin_user(
            username=settings.bootstrap_admin_username,
            display_name=settings.bootstrap_admin_display_name,
            password_hash=hash_password(bootstrap_password),
        )
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    yield
    tasks = list(direct_ingest_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    analysis_tasks = list(ai_analysis_tasks.values())
    for task in analysis_tasks:
        task.cancel()
    if analysis_tasks:
        await asyncio.gather(*analysis_tasks, return_exceptions=True)
    review_tasks = list(session_review_tasks.values())
    for task in review_tasks:
        task.cancel()
    if review_tasks:
        await asyncio.gather(*review_tasks, return_exceptions=True)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    issue = exc.errors()[0] if exc.errors() else {}
    location = issue.get("loc", [])
    field = str(location[-1]) if location else "输入内容"
    field_name = {
        "username": "用户名",
        "display_name": "显示姓名",
        "password": "密码",
    }.get(field, field)
    error_type = issue.get("type", "")
    context = issue.get("ctx") or {}
    if error_type == "string_too_short":
        message = f"{field_name}至少需要 {context.get('min_length', '')} 个字符"
    elif error_type == "string_too_long":
        message = f"{field_name}不能超过 {context.get('max_length', '')} 个字符"
    elif error_type == "string_pattern_mismatch":
        message = f"{field_name}只能包含中文、字母、数字、点、下划线或短横线"
    else:
        message = str(issue.get("msg") or f"{field_name}格式不正确").replace(
            "Value error, ",
            "",
        )
    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/api/health")
def health() -> dict:
    realtime_config = resolve_ai_config(database, settings, "realtime")
    return {
        "status": "ok",
        "environment": settings.app_env,
        "asr_provider": settings.asr_provider,
        "asr_configured": settings.asr_configured,
        "llm_model": realtime_config.model,
        "llm_configured": realtime_config.configured,
    }


@app.post("/api/auth/register", response_model=UserProfile, status_code=201)
def register(payload: RegisterInput):
    try:
        return database.create_user(
            username=payload.username,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该用户名已被注册") from exc


@app.post("/api/auth/login", response_model=UserProfile)
def login(payload: LoginInput, response: Response):
    user = database.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user["status"] == "pending":
        raise HTTPException(status_code=403, detail="账号正在等待管理员审核")
    if user["status"] == "disabled":
        raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")

    token = create_session_token()
    database.create_auth_session(
        user_id=user["id"],
        token_hash=hash_session_token(token),
        duration_days=settings.auth_session_days,
    )
    user = database.update_user(user["id"], {"last_login_at": datetime.now(UTC).isoformat()})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        database.delete_auth_session(hash_session_token(token))
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"logged_out": True}


@app.get("/api/auth/me", response_model=UserProfile)
def current_user_profile(current_user: CurrentUser):
    return current_user


@app.get("/api/admin/users", response_model=list[UserProfile])
def list_users(_: AdminUser):
    return database.list_users()


@app.patch("/api/admin/users/{user_id}", response_model=UserProfile)
def update_user(
    user_id: str,
    payload: UserAdminUpdate,
    _: AdminUser,
):
    target = database.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    updates = payload.model_dump(exclude_none=True)
    if "display_name" in updates:
        updates["display_name"] = updates["display_name"].strip()
    removes_active_admin = (
        target["role"] == "admin"
        and target["status"] == "active"
        and (
            updates.get("role", target["role"]) != "admin"
            or updates.get("status", target["status"]) != "active"
        )
    )
    if removes_active_admin and database.count_active_admins() <= 1:
        raise HTTPException(status_code=409, detail="必须保留至少一名启用中的管理员")
    return database.update_user(user_id, updates)


def ai_config_view(purpose: str) -> AiConfigView:
    resolved = resolve_ai_config(database, settings, purpose)
    stored = database.get_ai_config(purpose)
    return AiConfigView(
        purpose=purpose,
        api_base=resolved.api_base,
        model=resolved.model,
        configured=resolved.configured,
        has_api_key=bool(resolved.api_key),
        source=resolved.source,
        updated_at=stored.get("updated_at") if stored else None,
    )


@app.get("/api/admin/ai-configs", response_model=list[AiConfigView])
def list_ai_configs(_: AdminUser):
    return [ai_config_view(purpose) for purpose in ("realtime", "corpus")]


@app.put("/api/admin/ai-configs/{purpose}", response_model=AiConfigView)
def update_ai_config(
    purpose: str,
    payload: AiConfigUpdate,
    admin: AdminUser,
):
    if purpose not in AI_CONFIG_PURPOSES:
        raise HTTPException(status_code=404, detail="AI 配置用途不存在")
    current = database.get_ai_config(purpose)
    encrypted_key = current["api_key_encrypted"] if current else ""
    if payload.api_key is not None:
        normalized_key = payload.api_key.strip()
        if not normalized_key:
            raise HTTPException(status_code=422, detail="API Key 不能为空")
        encrypted_key = ApiKeyCipher(settings).encrypt(normalized_key)
    elif not encrypted_key:
        environment_key = (
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        )
        if not environment_key:
            raise HTTPException(status_code=422, detail="首次保存必须填写 API Key")
        encrypted_key = ApiKeyCipher(settings).encrypt(environment_key)
    database.upsert_ai_config(
        purpose=purpose,
        api_base=payload.api_base.strip().rstrip("/"),
        api_key_encrypted=encrypted_key,
        model=payload.model.strip(),
        updated_by=admin["id"],
    )
    return ai_config_view(purpose)


def probe_ai_config(purpose: str, payload: AiConfigProbe) -> ResolvedAiConfig:
    if purpose not in AI_CONFIG_PURPOSES:
        raise HTTPException(status_code=404, detail="AI 配置用途不存在")
    current = resolve_ai_config(database, settings, purpose)
    return ResolvedAiConfig(
        purpose=purpose,
        api_base=payload.api_base.strip().rstrip("/"),
        api_key=payload.api_key.strip() if payload.api_key else current.api_key,
        model=payload.model.strip() if payload.model else current.model,
        source=current.source,
    )


@app.post("/api/admin/ai-configs/{purpose}/models", response_model=AiModelsResult)
async def list_ai_models(purpose: str, payload: AiConfigProbe, _: AdminUser):
    try:
        models = await asyncio.to_thread(fetch_available_models, probe_ai_config(purpose, payload))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"models": models}


@app.post("/api/admin/ai-configs/{purpose}/test", response_model=AiConfigTestResult)
async def test_ai_config(purpose: str, payload: AiConfigProbe, _: AdminUser):
    try:
        await asyncio.to_thread(test_ai_connection, probe_ai_config(purpose, payload))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"success": True, "message": "DeepSeek 连接及模型调用正常"}


@app.get("/api/corpus", response_model=list[CorpusEntry])
def list_corpus(
    current_user: CurrentUser,
    operator_name: str = "",
):
    return database.list_corpus_entries(
        operator_name.strip(),
        owner_user_id=current_user["id"] if settings.auth_required else None,
    )


@app.post("/api/corpus", response_model=CorpusEntry, status_code=201)
def create_corpus_entry(
    payload: CorpusEntryCreate,
    current_user: CurrentUser,
):
    return database.add_corpus_entry(
        operator_name=(
            current_user["display_name"]
            if settings.auth_required
            else payload.operator_name.strip()
        ),
        category=payload.category.strip(),
        title=payload.title.strip(),
        content=payload.content.strip(),
        enabled=payload.enabled,
        owner_user_id=current_user["id"] if settings.auth_required else None,
    )


@app.post("/api/corpus/import", response_model=CorpusImportResult)
async def import_corpus_files(
    current_user: CurrentUser,
    files: Annotated[list[UploadFile], File()],
    operator_name: Annotated[str, Form(min_length=1, max_length=40)],
    category: Annotated[str, Form(min_length=1, max_length=40)],
):
    if not files:
        raise HTTPException(status_code=400, detail="请选择需要导入的文件")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="单次最多导入 10 个文件")
    corpus_ai_config = resolve_ai_config(database, settings, "corpus")
    if not corpus_ai_config.configured:
        raise HTTPException(status_code=503, detail="大模型服务尚未配置，无法智能整理语料")

    owner_name = (
        current_user["display_name"] if settings.auth_required else operator_name.strip()
    )
    category = category.strip()
    entries: list[dict] = []
    failures: list[CorpusImportFailure] = []
    imported_files = 0
    original_chars = 0
    saved_chars = 0
    fallback_files: list[str] = []

    for upload in files:
        filename = Path(upload.filename or "未命名文件").name
        try:
            data = await upload.read(10 * 1024 * 1024 + 1)
            text = parse_corpus_file(filename, data)
            markdown = await asyncio.to_thread(
                condense_corpus_markdown,
                corpus_ai_config.as_settings(settings),
                filename=filename,
                category=category,
                source_text=text,
            )
            if "大模型本次未生成摘要，已按原文导入" in markdown:
                fallback_files.append(filename)
            chunks = split_corpus_text(markdown)
            base_title = Path(filename).stem.strip() or "导入语料"
            for index, chunk in enumerate(chunks, start=1):
                suffix = f"（{index}/{len(chunks)}）" if len(chunks) > 1 else ""
                title = f"{base_title[: 100 - len(suffix)]}{suffix}"
                entries.append(
                    database.add_corpus_entry(
                        operator_name=owner_name,
                        category=category,
                        title=title,
                        content=chunk,
                        owner_user_id=(
                            current_user["id"] if settings.auth_required else None
                        ),
                        source_name=filename,
                        source_type=Path(filename).suffix.lower().lstrip("."),
                    )
                )
            imported_files += 1
            original_chars += len(text)
            saved_chars += len(markdown)
        except (CorpusFileError, RuntimeError, ValueError) as exc:
            failures.append(CorpusImportFailure(filename=filename, error=str(exc)))
        finally:
            await upload.close()

    return CorpusImportResult(
        imported_files=imported_files,
        imported_entries=len(entries),
        original_chars=original_chars,
        saved_chars=saved_chars,
        fallback_files=fallback_files,
        entries=entries,
        failures=failures,
    )


@app.put("/api/corpus/{entry_id}", response_model=CorpusEntry)
def update_corpus_entry(
    entry_id: int,
    payload: CorpusEntryUpdate,
    current_user: CurrentUser,
):
    updates = payload.model_dump(exclude_none=True)
    operator_name = str(updates.pop("operator_name")).strip()
    for key in {"category", "title", "content"} & updates.keys():
        updates[key] = str(updates[key]).strip()
    entry = database.update_corpus_entry(
        entry_id,
        operator_name,
        updates,
        owner_user_id=current_user["id"] if settings.auth_required else None,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="语料不存在或不属于当前优化师")
    return entry


@app.delete("/api/corpus/{entry_id}")
def delete_corpus_entry(
    entry_id: int,
    current_user: CurrentUser,
    operator_name: str = "",
):
    if not database.delete_corpus_entry(
        entry_id,
        operator_name.strip(),
        owner_user_id=current_user["id"] if settings.auth_required else None,
    ):
        raise HTTPException(status_code=404, detail="语料不存在或不属于当前优化师")
    return {"deleted": True}


@app.post("/api/sessions", response_model=SessionSummary, status_code=201)
def create_session(
    payload: SessionCreate,
    current_user: CurrentUser,
):
    return database.create_session(
        payload,
        owner_user_id=current_user["id"] if settings.auth_required else None,
        operator_name=(
            current_user["display_name"] if settings.auth_required else payload.operator_name
        ),
    )


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions(current_user: CurrentUser):
    owner_user_id = None if current_user["role"] == "admin" else current_user["id"]
    return database.list_sessions(owner_user_id=owner_user_id)


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    current_user: CurrentUser,
):
    session = get_accessible_session(session_id, current_user)
    return {
        **session,
        "transcripts": database.list_transcripts(session_id),
    }


@app.post("/api/sessions/{session_id}/end", response_model=SessionSummary)
async def end_session(
    session_id: str,
    current_user: CurrentUser,
):
    get_accessible_session(session_id, current_user)
    await stop_direct_ingest(session_id)
    session = database.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="直播场次不存在")
    await monitor_hub.broadcast(
        session_id,
        {"type": "session", "payload": session},
    )
    schedule_session_review(session_id)
    return session


@app.get(
    "/api/sessions/{session_id}/review",
    response_model=SessionReview | None,
)
def get_session_review(
    session_id: str,
    current_user: CurrentUser,
):
    get_accessible_session(session_id, current_user)
    return database.get_session_review(session_id)


@app.post(
    "/api/sessions/{session_id}/review/generate",
    response_model=ReviewGenerationStatus,
    status_code=202,
)
def generate_session_review(
    session_id: str,
    current_user: CurrentUser,
):
    session = get_accessible_session(session_id, current_user)
    if session["status"] not in {"ended", "failed"}:
        raise HTTPException(status_code=409, detail="请先结束直播场次")
    if not resolve_ai_config(database, settings, "realtime").configured:
        raise HTTPException(status_code=503, detail="大模型服务尚未配置")
    schedule_session_review(session_id)
    return {"status": "pending"}


@app.get("/api/sessions/{session_id}/audio")
def get_audio(
    session_id: str,
    current_user: CurrentUser,
):
    session = get_accessible_session(session_id, current_user)
    if not session["audio_path"]:
        raise HTTPException(status_code=404, detail="该场次暂无录音")
    audio_path = Path(session["audio_path"])
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="录音文件不存在")
    return FileResponse(audio_path, media_type="audio/wav", filename=f"{session_id}.wav")


@app.get(
    "/api/sessions/{session_id}/dashboard",
    response_model=LiveDashboard,
)
def get_live_dashboard(
    session_id: str,
    current_user: CurrentUser,
):
    get_accessible_session(session_id, current_user)
    return build_live_dashboard(session_id)


def build_live_dashboard(session_id: str) -> dict:
    records = database.latest_metrics(session_id)
    latest_metrics: dict[str, float] = {}
    latest_metric_at = None
    for record in records:
        record_metrics = {
            **record["normalized"],
            **normalize_metrics(record["payload"], record["endpoint"]),
        }
        if record_metrics:
            latest_metrics.update(record_metrics)
            latest_metric_at = record["captured_at"]
    return {
        "latest_metrics": latest_metrics,
        "latest_metric_at": latest_metric_at,
        "latest_insight": database.latest_ai_insight(session_id),
    }


@app.get("/api/overview", response_model=MultiRoomOverview)
def get_multi_room_overview(
    current_user: CurrentUser,
    operator_name: str = "",
):
    owner_user_id = None if current_user["role"] == "admin" else current_user["id"]
    normalized_operator = operator_name.strip()
    active_sessions = [
        session
        for session in database.list_sessions(owner_user_id=owner_user_id)
        if session["status"] in {"created", "live"}
        and (
            settings.auth_required
            or not normalized_operator
            or session["operator_name"] == normalized_operator
        )
    ]
    return {
        "rooms": [
            {
                "session": session,
                "dashboard": build_live_dashboard(session["id"]),
            }
            for session in active_sessions
        ],
        "updated_at": datetime.now(UTC),
    }


@app.post(
    "/api/sessions/{session_id}/metrics",
    response_model=MetricSnapshot,
)
async def capture_metrics(session_id: str, payload: MetricCapture):
    if not database.get_session(session_id):
        raise HTTPException(status_code=404, detail="直播场次不存在")
    normalized = normalize_metrics(payload.payload, payload.endpoint)
    snapshot = database.add_metric_snapshot(
        session_id,
        payload.endpoint,
        payload.page_url,
        payload.payload,
        normalized,
        payload.captured_at.isoformat() if payload.captured_at else None,
    )
    await monitor_hub.broadcast(
        session_id,
        {"type": "metrics", "payload": snapshot},
    )
    schedule_ai_analysis(session_id)
    return snapshot


@app.post(
    "/api/sessions/{session_id}/live-source/probe",
    response_model=LiveSourceProbeResult,
)
async def probe_session_live_source(
    session_id: str,
    current_user: CurrentUser,
):
    session = get_accessible_session(session_id, current_user)
    if not session["live_url"]:
        raise HTTPException(status_code=400, detail="该场次未填写直播间链接")
    try:
        autoengine_cookie = (
            settings.autoengine_cookie.get_secret_value()
            if settings.autoengine_cookie
            else None
        )
        result = await asyncio.wait_for(
            asyncio.to_thread(
                probe_live_source,
                session["live_url"],
                autoengine_cookie,
            ),
            timeout=25,
        )
    except (UnsupportedLiveUrlError, LiveSourceAuthError) as exc:
        return LiveSourceProbeResult(status="unsupported", message=str(exc))
    except TimeoutError:
        return LiveSourceProbeResult(
            status="error",
            message="直播平台响应超时，请稍后再试",
        )
    return LiveSourceProbeResult(**result.__dict__)


@app.post(
    "/api/sessions/{session_id}/live-source/start",
    response_model=AudioSourceStatus,
)
async def start_live_source(
    session_id: str,
    current_user: CurrentUser,
):
    session = get_accessible_session(session_id, current_user)
    retryable_failure = (
        session["status"] == "failed"
        and session["transcript_count"] == 0
        and session["duration_seconds"] <= 5
    )
    if retryable_failure:
        session = database.reset_session_for_retry(session_id)
    if session["status"] in {"ended", "failed"}:
        raise HTTPException(status_code=409, detail="已结束场次不能启动监听")
    if not session["live_url"]:
        raise HTTPException(status_code=400, detail="该场次未填写直播间链接")
    if session_id in active_audio_sessions:
        raise HTTPException(status_code=409, detail="该场次已有音频采集连接")

    active_audio_sessions.add(session_id)
    payload = {
        "active": True,
        "connected": False,
        "source": "live_url",
        "message": "正在启动链接监听",
    }
    audio_session_states[session_id] = payload
    task = asyncio.create_task(
        run_direct_live_ingest(session_id, session["live_url"]),
        name=f"direct-live-ingest-{session_id}",
    )
    direct_ingest_tasks[session_id] = task
    task.add_done_callback(lambda completed: remove_direct_ingest_task(session_id, completed))
    await monitor_hub.broadcast(
        session_id,
        {"type": "audio_status", "payload": payload},
    )
    return AudioSourceStatus(**payload)


@app.post(
    "/api/sessions/{session_id}/live-source/stop",
    response_model=AudioSourceStatus,
)
async def stop_live_source(
    session_id: str,
    current_user: CurrentUser,
):
    get_accessible_session(session_id, current_user)
    status = get_audio_status(session_id)
    if status.get("source") in {"windows", "browser_extension"}:
        collector_name = (
            "浏览器扩展"
            if status.get("source") == "browser_extension"
            else "Windows采集助手"
        )
        raise HTTPException(status_code=409, detail=f"请在{collector_name}中停止采集")
    await stop_direct_ingest(session_id)
    return AudioSourceStatus(**get_audio_status(session_id))


@app.websocket("/ws/monitor/{session_id}")
async def monitor_socket(websocket: WebSocket, session_id: str):
    session = database.get_session(session_id)
    if settings.auth_required:
        token = websocket.cookies.get(SESSION_COOKIE_NAME)
        user = (
            database.get_user_by_session(hash_session_token(token))
            if token
            else None
        )
        if not user or user["status"] != "active":
            await websocket.close(code=4401, reason="authentication required")
            return
        if user["role"] != "admin" and (
            not session or session.get("owner_user_id") != user["id"]
        ):
            await websocket.close(code=4404, reason="session not found")
            return
    if not session:
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
                "payload": get_audio_status(session_id),
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
    try:
        asr = create_asr_provider(settings)
    except ValueError as exc:
        await monitor_hub.broadcast(
            session_id,
            {
                "type": "warning",
                "payload": {"message": str(exc)},
            },
        )
        await websocket.close(code=1011, reason="ASR configuration error")
        return

    requested_source = websocket.query_params.get("source", "windows")
    collector_source = (
        "browser_extension"
        if requested_source == "browser_extension"
        else "windows"
    )
    collector_name = (
        "浏览器扩展"
        if collector_source == "browser_extension"
        else "Windows采集助手"
    )
    await websocket.accept()
    active_audio_sessions.add(session_id)
    audio_session_states[session_id] = {
        "active": True,
        "connected": True,
        "source": collector_source,
        "message": f"{collector_name}已连接",
    }
    database.set_session_live(session_id)
    output_path = settings.storage_root / "audio" / f"{session_id}.wav"
    recorder = WavRecorder(output_path)
    signal_monitor = Pcm16SignalMonitor()

    try:
        recorder.open()
        database.set_audio_path(session_id, str(output_path.resolve()))
        await asr.start(create_transcript_callback(session_id))
        await monitor_hub.broadcast(
            session_id,
            {
                "type": "session",
                "payload": database.get_session(session_id),
            },
        )
        await set_audio_status(
            session_id,
            active=True,
            connected=True,
            source=collector_source,
            message=f"{collector_name}已连接",
        )
        while True:
            message = await websocket.receive()
            chunk = message.get("bytes")
            if chunk:
                signal_state = signal_monitor.observe(chunk)
                if signal_state == "silent":
                    silence_action = (
                        "请确认懂车云店直播画面正在播放且未静音，然后重新采集"
                        if collector_source == "browser_extension"
                        else "请确认采集设备正在播放直播声音"
                    )
                    await set_audio_status(
                        session_id,
                        active=True,
                        connected=True,
                        source=collector_source,
                        message=(
                            f"{collector_name}已连接，但连续8秒未检测到声音；"
                            f"{silence_action}"
                        ),
                    )
                elif signal_state == "resumed":
                    await set_audio_status(
                        session_id,
                        active=True,
                        connected=True,
                        source=collector_source,
                        message=f"{collector_name}声音已恢复，正在识别",
                    )
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
        with suppress(Exception):
            await asr.close()
        active_audio_sessions.discard(session_id)
        await set_audio_status(
            session_id,
            active=False,
            connected=False,
            source=None,
            message=f"{collector_name}已断开",
        )
