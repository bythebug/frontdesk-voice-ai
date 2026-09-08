"""Text-to-speech abstraction over the Piper CLI. The rest of the app
depends only on TextToSpeech — swapping the backend means implementing
this interface, not touching callers.

Piper is invoked as a subprocess (`piper --model <voice>.onnx --output_raw`),
text piped via stdin, raw 16-bit PCM audio read back from stdout. This
matches Piper's documented CLI usage and avoids coupling to a specific
Python binding's API — install via `pip install piper-tts` or a
downloaded release binary (see README).
"""

import asyncio
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class TextToSpeech(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Returns raw 16-bit PCM mono audio at Settings.audio_sample_rate."""


class TtsUnavailableError(Exception):
    """Raised when synthesis fails: binary missing, model missing, or the
    piper process itself failed."""


class PiperTTS(TextToSpeech):
    def __init__(
        self, voice: str | None = None, model_path: str | None = None, binary: str = "piper"
    ) -> None:
        settings = get_settings()
        self.voice = voice or settings.piper_voice
        self.model_path = model_path or settings.piper_model_path
        self.binary = binary

    def _model_file(self) -> Path:
        return Path(self.model_path) / f"{self.voice}.onnx"

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        if shutil.which(self.binary) is None:
            raise TtsUnavailableError(
                f"The '{self.binary}' binary isn't on PATH. See README for install steps."
            )
        model_file = self._model_file()
        if not model_file.exists():
            raise TtsUnavailableError(
                f"Piper voice model not found at {model_file}. See README for how to download one."
            )

        try:
            process = await asyncio.create_subprocess_exec(
                self.binary,
                "--model",
                str(model_file),
                "--output_raw",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(text.encode("utf-8"))
        except OSError as exc:
            raise TtsUnavailableError(f"Failed to run {self.binary}: {exc}") from exc

        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            logger.error(
                "tts_process_failed",
                extra={"returncode": process.returncode, "stderr": message},
            )
            raise TtsUnavailableError(f"piper exited with {process.returncode}: {message}")

        return stdout
