from .base import AsrProvider, TranscriptCallback


class MockAsrProvider(AsrProvider):
    """Pipeline-only adapter used before a production ASR account exists.

    It emits periodic status text so the realtime UI can be validated. It does
    not claim to transcribe speech.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.on_transcript: TranscriptCallback | None = None
        self.bytes_received = 0
        self.last_emitted_second = 0

    async def start(self, on_transcript: TranscriptCallback) -> None:
        self.on_transcript = on_transcript

    async def send_audio(self, chunk: bytes) -> None:
        self.bytes_received += len(chunk)
        seconds = self.bytes_received // (self.sample_rate * 2)
        if seconds >= self.last_emitted_second + 10 and self.on_transcript:
            start = self.last_emitted_second * 1000
            end = seconds * 1000
            self.last_emitted_second = seconds
            await self.on_transcript(
                f"已接收约 {seconds} 秒实时音频，正式语音识别服务尚未配置。",
                start,
                end,
                True,
            )

    async def close(self) -> None:
        return None
