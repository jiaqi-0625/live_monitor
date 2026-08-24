import wave
from array import array
from pathlib import Path
from sys import byteorder


class Pcm16SignalMonitor:
    """Detect a connected PCM16 stream that contains only silence."""

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_seconds: float = 8,
        amplitude_threshold: int = 8,
    ) -> None:
        self.silent_byte_limit = int(sample_rate * 2 * silence_seconds)
        self.amplitude_threshold = amplitude_threshold
        self.silent_bytes = 0
        self.warning_active = False

    def observe(self, chunk: bytes) -> str | None:
        if not chunk:
            return None
        usable = chunk[: len(chunk) - (len(chunk) % 2)]
        samples = array("h")
        samples.frombytes(usable)
        if byteorder != "little":
            samples.byteswap()
        audible = any(abs(sample) > self.amplitude_threshold for sample in samples)
        if audible:
            self.silent_bytes = 0
            if self.warning_active:
                self.warning_active = False
                return "resumed"
            return None

        self.silent_bytes += len(usable)
        if (
            not self.warning_active
            and self.silent_bytes >= self.silent_byte_limit
        ):
            self.warning_active = True
            return "silent"
        return None


class WavRecorder:
    def __init__(self, output_path: Path, sample_rate: int = 16000):
        self.output_path = output_path
        self.sample_rate = sample_rate
        self._wave: wave.Wave_write | None = None
        self.bytes_written = 0

    def open(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._wave = wave.open(str(self.output_path), "wb")
        self._wave.setnchannels(1)
        self._wave.setsampwidth(2)
        self._wave.setframerate(self.sample_rate)

    def write(self, chunk: bytes) -> None:
        if not self._wave:
            raise RuntimeError("Recorder is not open")
        self._wave.writeframesraw(chunk)
        self.bytes_written += len(chunk)

    def close(self) -> None:
        if self._wave:
            self._wave.close()
            self._wave = None
