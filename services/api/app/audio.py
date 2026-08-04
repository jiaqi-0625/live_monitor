import wave
from pathlib import Path


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

