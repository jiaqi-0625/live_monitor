from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import soundcard as sc
import websocket

StatusCallback = Callable[[str, str], None]
LevelCallback = Callable[[float], None]


@dataclass(frozen=True)
class AudioDevice:
    id: str
    name: str


def list_loopback_devices() -> list[AudioDevice]:
    devices: list[AudioDevice] = []
    for microphone in sc.all_microphones(include_loopback=True):
        if microphone.isloopback:
            devices.append(AudioDevice(str(microphone.id), microphone.name))
    return devices


class AudioCaptureWorker:
    def __init__(
        self,
        websocket_url: str,
        device_id: str,
        on_status: StatusCallback,
        on_level: LevelCallback,
        sample_rate: int = 16000,
        frames_per_chunk: int = 1600,
    ):
        self.websocket_url = websocket_url
        self.device_id = device_id
        self.on_status = on_status
        self.on_level = on_level
        self.sample_rate = sample_rate
        self.frames_per_chunk = frames_per_chunk
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="audio-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float = 3) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        socket: websocket.WebSocket | None = None
        try:
            self.on_status("connecting", "正在连接云端实时通道…")
            socket = websocket.create_connection(
                self.websocket_url,
                timeout=10,
                enable_multithread=True,
            )
            microphone = sc.get_microphone(self.device_id, include_loopback=True)
            self.on_status("live", "采集中，浏览器工作台将显示实时状态")

            with microphone.recorder(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.frames_per_chunk,
            ) as recorder:
                while not self._stop_event.is_set():
                    frames = recorder.record(numframes=self.frames_per_chunk)
                    mono = np.asarray(frames, dtype=np.float32).reshape(-1)
                    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
                    self.on_level(min(1.0, peak))
                    pcm16 = (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2")
                    socket.send_binary(pcm16.tobytes())
        except Exception as exc:
            self.on_status("error", f"采集失败：{exc}")
        finally:
            if socket:
                try:
                    socket.close()
                except Exception:
                    pass
            self.on_level(0)
            if self._stop_event.is_set():
                self.on_status("stopped", "采集已停止")

