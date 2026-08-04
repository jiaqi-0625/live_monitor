from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

TranscriptCallback = Callable[[str, int, int, bool], Awaitable[None]]


class AsrProvider(ABC):
    """Streaming ASR provider contract.

    Production adapters should accept PCM16, 16 kHz, mono audio and call
    ``on_transcript`` for partial or final results.
    """

    @abstractmethod
    async def start(self, on_transcript: TranscriptCallback) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

