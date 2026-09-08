"""Shared base64 <-> raw-PCM-bytes helpers for the WebSocket audio_chunk/audio
messages. Both STT (Phase 6) and TTS (Phase 7) use these."""

import base64


def decode_audio_chunk(data: str) -> bytes:
    return base64.b64decode(data)


def encode_audio_chunk(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
