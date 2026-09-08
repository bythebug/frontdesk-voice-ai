"""Shared base64 <-> raw-PCM-bytes helpers for the WebSocket audio_chunk/audio
messages. Both STT (Phase 6) and TTS (Phase 7) use these."""

import base64

# Matches the frontend's SILENCE_RMS_THRESHOLD — same semantic threshold,
# used server-side to tell real speech apart from routine mic noise when
# deciding whether an incoming chunk should trigger a barge-in (Phase 9).
SPEECH_RMS_THRESHOLD = 0.02


def decode_audio_chunk(data: str) -> bytes:
    return base64.b64decode(data)


def encode_audio_chunk(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def is_speech(pcm16: bytes, threshold: float = SPEECH_RMS_THRESHOLD) -> bool:
    """Cheap voice-activity check on raw 16-bit PCM: RMS amplitude above a
    fixed threshold. Not a real VAD model — a documented simplification,
    same as the frontend's."""
    # Truncate a trailing odd byte rather than crash on malformed/partial
    # input — a corrupt chunk should be treated as silence, not take the
    # connection down.
    usable_length = len(pcm16) - (len(pcm16) % 2)
    if usable_length == 0:
        return False
    import numpy as np

    samples = np.frombuffer(pcm16[:usable_length], dtype=np.int16).astype(np.float32) / 32768.0
    return bool(np.sqrt(np.mean(samples**2)) > threshold)
