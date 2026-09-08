"""Speech-to-text abstraction. The rest of the app depends only on
SpeechToText — swapping the backend (e.g. off faster-whisper) means
implementing this one interface, not touching callers."""

import asyncio
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SpeechToText(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes) -> str:
        """audio is raw 16-bit PCM, mono, at Settings.audio_sample_rate."""


class SttUnavailableError(Exception):
    """Raised when transcription fails (model load failure, bad audio, etc.)."""


class FasterWhisperSTT(SpeechToText):
    """Runs faster-whisper's synchronous, CPU/GPU-bound inference in a
    thread executor so it doesn't block the event loop."""

    def __init__(self, model_size: str | None = None, device: str | None = None) -> None:
        settings = get_settings()
        self.model_size = model_size or settings.whisper_model
        self.device = device or settings.whisper_device
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            from faster_whisper import WhisperModel

            compute_type = "int8" if self.device in ("cpu", "auto") else "float16"
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=compute_type
            )
        return self._model

    async def transcribe(self, audio: bytes) -> str:
        if not audio:
            return ""
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._transcribe_sync, audio)
        except Exception as exc:  # noqa: BLE001 — surfaced as a clear domain error
            logger.error("stt_failed", extra={"error": str(exc)})
            raise SttUnavailableError(f"Transcription failed: {exc}") from exc

    def _transcribe_sync(self, audio: bytes) -> str:
        import numpy as np

        model = self._get_model()
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(samples, language="en")  # type: ignore[attr-defined]
        return " ".join(segment.text.strip() for segment in segments).strip()
