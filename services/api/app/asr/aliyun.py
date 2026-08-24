from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .base import AsrProvider, TranscriptCallback

SUCCESS_STATUS = 20000000


class AliyunAsrError(RuntimeError):
    """Raised when Aliyun NLS rejects or interrupts a recognition task."""


class TokenProvider(Protocol):
    async def get_token(self) -> str: ...


class WebSocketConnection(Protocol):
    async def send(self, message: str | bytes) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def close(self) -> None: ...


ConnectCallable = Callable[..., Awaitable[WebSocketConnection]]


class AliyunTokenProvider:
    """Fetch and cache the short-lived NLS token using RAM credentials."""

    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        region_id: str = "cn-shanghai",
        refresh_margin_seconds: int = 300,
    ):
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.region_id = region_id
        self.refresh_margin_seconds = refresh_margin_seconds
        self._token: str | None = None
        self._expires_at = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._token_is_valid():
            return self._token or ""

        async with self._lock:
            if self._token_is_valid():
                return self._token or ""
            token, expires_at = await asyncio.to_thread(self._create_token)
            self._token = token
            self._expires_at = expires_at
            return token

    def _token_is_valid(self) -> bool:
        return bool(self._token and time.time() < self._expires_at - self.refresh_margin_seconds)

    def _create_token(self) -> tuple[str, int]:
        try:
            from aliyunsdkcore.client import AcsClient
        except ImportError as exc:
            raise AliyunAsrError("阿里云Token SDK尚未安装") from exc

        client = AcsClient(
            self.access_key_id,
            self.access_key_secret,
            self.region_id,
        )
        request = self._build_token_request()
        try:
            response = client.do_action_with_exception(request)
            payload = json.loads(response)
        except Exception as exc:
            raise AliyunAsrError("获取阿里云语音识别Token失败") from exc
        return self._parse_token_response(payload)

    def _build_token_request(self) -> Any:
        from aliyunsdkcore.request import CommonRequest

        request = CommonRequest()
        request.set_accept_format("JSON")
        request.set_protocol_type("https")
        request.set_method("POST")
        request.set_domain(f"nls-meta.{self.region_id}.aliyuncs.com")
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")
        return request

    @staticmethod
    def _parse_token_response(payload: dict[str, Any]) -> tuple[str, int]:
        token_payload = payload.get("Token") or {}
        token = str(token_payload.get("Id") or "")
        if not token:
            code = payload.get("ErrCode") or payload.get("Code") or "unknown"
            message = payload.get("ErrMsg") or payload.get("Message") or "未返回Token"
            raise AliyunAsrError(f"阿里云Token请求失败：{message}（{code}）")
        try:
            expires_at = int(token_payload["ExpireTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AliyunAsrError("阿里云Token响应缺少有效期") from exc
        return token, expires_at


class AliyunAsrProvider(AsrProvider):
    """Aliyun NLS SpeechTranscriber adapter for PCM16 16 kHz mono audio."""

    def __init__(
        self,
        appkey: str,
        token_provider: TokenProvider,
        websocket_url: str = "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1",
        sample_rate: int = 16000,
        vocabulary_id: str | None = None,
        connect_timeout_seconds: float = 10,
        connect_callable: ConnectCallable = connect,
    ):
        self.appkey = appkey
        self.token_provider = token_provider
        self.websocket_url = websocket_url
        self.sample_rate = sample_rate
        self.vocabulary_id = vocabulary_id
        self.connect_timeout_seconds = connect_timeout_seconds
        self.connect_callable = connect_callable

        self.on_transcript: TranscriptCallback | None = None
        self._websocket: WebSocketConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._completed = asyncio.Event()
        self._fatal_error: AliyunAsrError | None = None
        self._task_id = uuid4().hex
        self._last_final_end_ms = 0
        self._closing = False

    async def start(self, on_transcript: TranscriptCallback) -> None:
        self.on_transcript = on_transcript
        token = await self.token_provider.get_token()
        separator = "&" if "?" in self.websocket_url else "?"
        url = f"{self.websocket_url}{separator}{urlencode({'token': token})}"
        try:
            self._websocket = await asyncio.wait_for(
                self.connect_callable(
                    url,
                    max_size=4 * 1024 * 1024,
                    ping_interval=20,
                    ping_timeout=20,
                ),
                timeout=self.connect_timeout_seconds,
            )
        except Exception as exc:
            raise AliyunAsrError("连接阿里云实时语音识别失败") from exc

        self._reader_task = asyncio.create_task(
            self._read_messages(),
            name=f"aliyun-asr-{self._task_id[:8]}",
        )
        await self._send_command(
            "StartTranscription",
            self._start_payload(),
        )
        try:
            await asyncio.wait_for(
                self._started.wait(),
                timeout=self.connect_timeout_seconds,
            )
        except TimeoutError as exc:
            await self.close()
            raise AliyunAsrError("等待阿里云开始识别超时") from exc
        self._raise_if_failed()

    async def send_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._raise_if_failed()
        if not self._websocket or not self._started.is_set():
            raise AliyunAsrError("阿里云实时语音识别尚未启动")
        try:
            await self._websocket.send(chunk)
        except Exception as exc:
            raise AliyunAsrError("向阿里云发送音频失败") from exc

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        websocket = self._websocket
        if websocket:
            if self._started.is_set() and not self._completed.is_set():
                with suppress(Exception):
                    await self._send_command("StopTranscription")
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._completed.wait(), timeout=3)
            with suppress(Exception):
                await websocket.close()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        self._websocket = None

    def _start_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": "pcm",
            "sample_rate": self.sample_rate,
            "enable_intermediate_result": True,
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
            "enable_ignore_sentence_timeout": True,
        }
        if self.vocabulary_id:
            payload["vocabulary_id"] = self.vocabulary_id
        return payload

    async def _send_command(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self._websocket:
            raise AliyunAsrError("阿里云WebSocket尚未连接")
        message: dict[str, Any] = {
            "header": {
                "message_id": uuid4().hex,
                "task_id": self._task_id,
                "namespace": "SpeechTranscriber",
                "name": name,
                "appkey": self.appkey,
            }
        }
        if payload:
            message["payload"] = payload
        await self._websocket.send(json.dumps(message, ensure_ascii=False, separators=(",", ":")))

    async def _read_messages(self) -> None:
        if not self._websocket:
            return
        try:
            while True:
                raw_message = await self._websocket.recv()
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                message = json.loads(raw_message)
                await self._handle_message(message)
                if self._completed.is_set() or self._fatal_error:
                    return
        except ConnectionClosed as exc:
            if not self._closing and not self._completed.is_set():
                self._set_fatal_error(AliyunAsrError(f"阿里云识别连接已断开（{exc.code}）"))
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closing:
                self._set_fatal_error(AliyunAsrError("读取阿里云识别结果失败"))

    async def _handle_message(self, message: dict[str, Any]) -> None:
        header = message.get("header") or {}
        payload = message.get("payload") or {}
        status = int(header.get("status", SUCCESS_STATUS))
        name = str(header.get("name", ""))
        if status != SUCCESS_STATUS or name in {"TaskFailed", "TranscriptionFailed"}:
            status_text = header.get("status_text") or "阿里云识别任务失败"
            self._set_fatal_error(AliyunAsrError(f"{status_text}（{status}）"))
            return

        if name == "TranscriptionStarted":
            self._started.set()
            return
        if name == "TranscriptionCompleted":
            self._completed.set()
            return
        if name != "SentenceEnd" or not self.on_transcript:
            return

        text = str(payload.get("result", "")).strip()
        if not text:
            return
        end_ms = max(
            self._last_final_end_ms,
            int(payload.get("time") or self._last_final_end_ms),
        )
        start_ms = int(payload.get("begin_time") or self._last_final_end_ms)
        if end_ms < start_ms:
            end_ms = start_ms
        self._last_final_end_ms = end_ms
        await self.on_transcript(text, start_ms, end_ms, True)

    def _set_fatal_error(self, error: AliyunAsrError) -> None:
        self._fatal_error = error
        self._started.set()
        self._completed.set()

    def _raise_if_failed(self) -> None:
        if self._fatal_error:
            raise self._fatal_error
        if self._reader_task and self._reader_task.done():
            exception = self._reader_task.exception()
            if exception:
                raise AliyunAsrError("阿里云识别结果通道异常") from exception
