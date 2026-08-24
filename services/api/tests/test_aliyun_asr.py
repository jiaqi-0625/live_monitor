import asyncio
import json
import time
from typing import Any

import pytest

from app.asr.aliyun import (
    SUCCESS_STATUS,
    AliyunAsrError,
    AliyunAsrProvider,
    AliyunTokenProvider,
)
from app.asr.factory import create_asr_provider
from app.config import Settings


class StaticTokenProvider:
    async def get_token(self) -> str:
        return "test token"


class FakeWebSocket:
    def __init__(self, fail_on_start: bool = False):
        self.fail_on_start = fail_on_start
        self.incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str | bytes] = []
        self.closed = False

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)
        if not isinstance(message, str):
            return
        command = json.loads(message)
        name = command["header"]["name"]
        if name == "StartTranscription":
            if self.fail_on_start:
                await self.emit(
                    "TaskFailed",
                    status=40000000,
                    status_text="invalid appkey",
                )
            else:
                await self.emit("TranscriptionStarted")
        if name == "StopTranscription":
            await self.emit("TranscriptionCompleted")

    async def recv(self) -> str:
        return await self.incoming.get()

    async def close(self) -> None:
        self.closed = True

    async def emit(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        status: int = SUCCESS_STATUS,
        status_text: str = "",
    ) -> None:
        await self.incoming.put(
            json.dumps(
                {
                    "header": {
                        "name": name,
                        "status": status,
                        "status_text": status_text,
                    },
                    "payload": payload or {},
                }
            )
        )


def test_aliyun_streaming_protocol_and_final_transcript():
    async def scenario():
        socket = FakeWebSocket()
        connected_urls: list[str] = []
        transcripts: list[tuple[str, int, int, bool]] = []
        transcript_received = asyncio.Event()

        async def fake_connect(url: str, **_: Any) -> FakeWebSocket:
            connected_urls.append(url)
            return socket

        async def on_transcript(
            text: str,
            start_ms: int,
            end_ms: int,
            is_final: bool,
        ) -> None:
            transcripts.append((text, start_ms, end_ms, is_final))
            transcript_received.set()

        provider = AliyunAsrProvider(
            appkey="test-appkey",
            token_provider=StaticTokenProvider(),
            vocabulary_id="cars-vocabulary",
            connect_callable=fake_connect,
        )
        await provider.start(on_transcript)
        await provider.send_audio(b"\x00\x00" * 1600)
        await socket.emit(
            "SentenceEnd",
            {
                "result": "欢迎来到汽车直播间。",
                "begin_time": 100,
                "time": 1800,
            },
        )
        await asyncio.wait_for(transcript_received.wait(), timeout=1)
        await provider.close()

        assert connected_urls == [
            "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token=test+token"
        ]
        start_command = json.loads(next(item for item in socket.sent if isinstance(item, str)))
        assert start_command["header"]["name"] == "StartTranscription"
        assert start_command["header"]["appkey"] == "test-appkey"
        assert start_command["payload"] == {
            "format": "pcm",
            "sample_rate": 16000,
            "enable_intermediate_result": True,
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
            "enable_ignore_sentence_timeout": True,
            "vocabulary_id": "cars-vocabulary",
        }
        assert b"\x00\x00" * 1600 in socket.sent
        assert transcripts == [("欢迎来到汽车直播间。", 100, 1800, True)]
        assert socket.closed is True

    asyncio.run(scenario())


def test_aliyun_start_failure_is_reported():
    async def scenario():
        socket = FakeWebSocket(fail_on_start=True)

        async def fake_connect(_: str, **__: Any) -> FakeWebSocket:
            return socket

        provider = AliyunAsrProvider(
            appkey="invalid",
            token_provider=StaticTokenProvider(),
            connect_callable=fake_connect,
        )
        with pytest.raises(AliyunAsrError, match="invalid appkey"):
            await provider.start(lambda *_: asyncio.sleep(0))
        await provider.close()

    asyncio.run(scenario())


def test_token_provider_caches_unexpired_token(monkeypatch):
    provider = AliyunTokenProvider("key-id", "key-secret")
    calls = 0

    def create_token() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "cached-token", int(time.time()) + 3600

    monkeypatch.setattr(provider, "_create_token", create_token)

    async def scenario():
        assert await provider.get_token() == "cached-token"
        assert await provider.get_token() == "cached-token"

    asyncio.run(scenario())
    assert calls == 1


def test_token_request_uses_explicit_nls_endpoint():
    provider = AliyunTokenProvider("key-id", "key-secret", region_id="cn-shanghai")
    request = provider._build_token_request()

    assert request.get_protocol_type() == "https"
    assert request.get_method() == "POST"
    assert request.get_domain() == "nls-meta.cn-shanghai.aliyuncs.com"
    assert request.get_version() == "2019-02-28"
    assert request.get_action_name() == "CreateToken"


def test_token_response_reports_aliyun_permission_error():
    with pytest.raises(AliyunAsrError, match=r"No permission.*40020503"):
        AliyunTokenProvider._parse_token_response(
            {
                "ErrCode": 40020503,
                "ErrMsg": "No permission!",
                "RequestId": "request-id",
            }
        )


def test_factory_requires_aliyun_credentials():
    incomplete = Settings(_env_file=None, asr_provider="aliyun")
    assert incomplete.asr_configured is False
    with pytest.raises(ValueError, match="ALIYUN_NLS_APPKEY"):
        create_asr_provider(incomplete)

    configured = Settings(
        _env_file=None,
        asr_provider="aliyun",
        aliyun_nls_appkey="appkey",
        aliyun_access_key_id="access-key-id",
        aliyun_access_key_secret="access-key-secret",
    )
    assert configured.asr_configured is True
    assert isinstance(create_asr_provider(configured), AliyunAsrProvider)
