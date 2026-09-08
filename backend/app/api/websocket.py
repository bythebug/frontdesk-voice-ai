"""WebSocket endpoint — the browser's only channel to the backend. All
business logic (LLM, tools, DB) stays server-side; the client only ever
exchanges these JSON messages.

Client -> server:
  {"type": "user_text", "text": "..."}          direct text input
  {"type": "audio_chunk", "data": "<base64>"}    raw 16-bit PCM mono audio, buffered server-side.
                                                  If real speech (not silence) arrives while the
                                                  agent is still working on the previous turn,
                                                  that turn is cancelled — barge-in (see
                                                  Interruption below).
  {"type": "audio_end"}                          user stopped speaking — transcribe the buffer
  {"type": "end_conversation"}

Server -> client:
  {"type": "conversation_started", "conversation_id": "..."}
  {"type": "transcript", "speaker": "user"|"agent", "text": "...", "timestamp": "..."}
  {"type": "agent_state", "state": "listening"|"thinking"|"calling_tool"|"speaking"|"interrupted"}
  {"type": "tool_call", "tool": "...", "arguments": {...}}
  {"type": "tool_result", "tool": "...", "success": bool, "data": {...}|null, "error": str|null}
  {"type": "audio", "data": "<base64>"}          synthesized speech (raw 16-bit PCM)
  {"type": "call_summary", "intent": ..., "customer_name": ..., "appointment": {...}|null,
   "issue": ..., "outcome": ..., "tools_used": [...]}   sent just before conversation_ended
  {"type": "conversation_ended", "conversation_id": "..."}
  {"type": "error", "message": "..."}

Interruption / barge-in: each turn (from user input to the agent's full
response) runs as a cancellable asyncio task, not inline in the receive
loop — that's what lets the server keep listening for new input while a
turn is in progress. Barge-in cancels that task, rolls back any of its
uncommitted DB writes (the interrupted turn is not partially persisted),
and sends agent_state "interrupted" then "listening" before the new input
is processed. Known limitation: once frames for a turn (e.g. its "audio"
message) have actually been sent to the client, they can't be un-sent —
cancellation only stops further work, matching how real barge-in is most
valuable (during the "thinking"/"calling_tool" latency, not after audio
already went out). The client additionally stops local audio playback
immediately on detecting new speech, which is the practical mechanism for
"stop what's already playing."
"""

import asyncio
import binascii
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.agent import ConversationAgent
from app.agent.llm_provider import LLMProvider, OllamaProvider
from app.agent.state import ConversationState
from app.core.logging import get_logger
from app.db.database import get_sessionmaker
from app.db.repositories import ConversationRepository
from app.services.summary_service import generate_call_summary
from app.voice.audio import decode_audio_chunk, encode_audio_chunk, is_speech
from app.voice.stt import FasterWhisperSTT, SpeechToText, SttUnavailableError
from app.voice.tts import PiperTTS, TextToSpeech, TtsUnavailableError

logger = get_logger(__name__)
router = APIRouter()

# Module-level so tests can swap in fakes without live Ollama/Whisper/Piper —
# referenced by (dynamic) name inside the handler below, not captured at
# import time, so monkeypatching these attributes takes effect.
_llm_provider: LLMProvider = OllamaProvider()
_stt: SpeechToText = FasterWhisperSTT()
_tts: TextToSpeech = PiperTTS()


class ClientMessage(BaseModel):
    type: Literal["user_text", "audio_chunk", "audio_end", "end_conversation"]
    text: str | None = None
    data: str | None = None


async def _send(websocket: WebSocket, type_: str, **fields: Any) -> None:
    await websocket.send_json({"type": type_, **fields})


def _now() -> str:
    return datetime.now(UTC).isoformat()


@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        conv_repo = ConversationRepository(session)
        try:
            conversation = await conv_repo.create()
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — DB unavailable shouldn't crash the process
            logger.error("conversation_create_failed", extra={"error": str(exc)})
            await _send(websocket, "error", message="Could not start a conversation right now.")
            await websocket.close()
            return

        state = ConversationState(conversation_id=conversation.id)
        agent = ConversationAgent(_llm_provider, state)
        audio_buffer = bytearray()
        current_turn: asyncio.Task[None] | None = None

        async def cancel_current_turn() -> None:
            nonlocal current_turn
            if current_turn is not None and not current_turn.done():
                current_turn.cancel()
                try:
                    await current_turn
                except asyncio.CancelledError:
                    pass
                logger.info(
                    "turn_interrupted", extra={"conversation_id": str(conversation.id)}
                )
                await _send(websocket, "agent_state", state="interrupted")
                await _send(websocket, "agent_state", state="listening")
            current_turn = None

        async def start_turn(text: str) -> None:
            nonlocal current_turn
            await cancel_current_turn()
            current_turn = asyncio.create_task(
                _run_turn(session_factory, websocket, agent, text)
            )

        await _send(websocket, "conversation_started", conversation_id=str(conversation.id))
        await _send(websocket, "agent_state", state="listening")

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = ClientMessage.model_validate_json(raw)
                except ValidationError as exc:
                    await _send(websocket, "error", message=f"Invalid message: {exc}")
                    continue

                if message.type == "user_text":
                    if not message.text:
                        await _send(websocket, "error", message="user_text requires 'text'")
                        continue
                    await start_turn(message.text)

                elif message.type == "audio_chunk":
                    if not message.data:
                        await _send(websocket, "error", message="audio_chunk requires 'data'")
                        continue
                    try:
                        chunk = decode_audio_chunk(message.data)
                    except (binascii.Error, ValueError):
                        await _send(
                            websocket, "error", message="audio_chunk 'data' isn't valid base64"
                        )
                        continue
                    audio_buffer.extend(chunk)
                    if is_speech(chunk) and current_turn is not None and not current_turn.done():
                        await cancel_current_turn()

                elif message.type == "audio_end":
                    if not audio_buffer:
                        await _send(websocket, "error", message="No audio received yet.")
                        continue
                    try:
                        text = await _stt.transcribe(bytes(audio_buffer))
                    except SttUnavailableError as exc:
                        logger.error(
                            "stt_unavailable",
                            extra={"conversation_id": str(conversation.id), "error": str(exc)},
                        )
                        await _send(
                            websocket,
                            "error",
                            message="Speech recognition failed. Please try again.",
                        )
                        audio_buffer.clear()
                        continue
                    audio_buffer.clear()
                    if not text:
                        await _send(
                            websocket, "error", message="Didn't catch that — could you repeat?"
                        )
                        continue
                    await start_turn(text)

                elif message.type == "end_conversation":
                    await cancel_current_turn()
                    await conv_repo.end(conversation.id)
                    summary = await generate_call_summary(session, _llm_provider, state)
                    await session.commit()
                    appointment = (
                        {"date": str(state.appointment_date), "time": state.appointment_time}
                        if state.appointment_date and state.appointment_time
                        else None
                    )
                    await _send(
                        websocket,
                        "call_summary",
                        intent=summary.intent,
                        customer_name=summary.customer_name,
                        appointment=appointment,
                        issue=summary.issue,
                        outcome=summary.summary,
                        tools_used=summary.actions_taken,
                    )
                    await _send(
                        websocket, "conversation_ended", conversation_id=str(conversation.id)
                    )
                    break

        except WebSocketDisconnect:
            logger.info("websocket_disconnected", extra={"conversation_id": str(conversation.id)})
            if current_turn is not None and not current_turn.done():
                current_turn.cancel()
                try:
                    await current_turn
                except asyncio.CancelledError:
                    pass


async def _run_turn(
    session_factory: async_sessionmaker[AsyncSession],
    websocket: WebSocket,
    agent: ConversationAgent,
    text: str,
) -> None:
    """Each turn gets its own DB session, opened and closed within this
    task. Cancelling a task that shares a session with other concurrent
    work risks corrupting SQLAlchemy's async/greenlet bridge for later
    reuse — self-contained per-turn sessions sidestep that entirely, and
    exiting this `async with` block (including via cancellation) rolls
    back any uncommitted work from an interrupted turn automatically."""
    async with session_factory() as session:
        await _handle_user_text(websocket, session, agent, text)


async def _handle_user_text(
    websocket: WebSocket, session: AsyncSession, agent: ConversationAgent, text: str
) -> None:
    await _send(websocket, "transcript", speaker="user", text=text, timestamp=_now())
    await _send(websocket, "agent_state", state="thinking")

    result = await agent.handle_user_message(session, text)

    for record in result.tool_calls:
        await _send(websocket, "agent_state", state="calling_tool")
        await _send(websocket, "tool_call", tool=record.name, arguments=record.arguments)
        await _send(
            websocket,
            "tool_result",
            tool=record.name,
            success=record.result.success,
            data=record.result.data,
            error=record.result.error,
        )

    await _send(websocket, "agent_state", state="speaking")
    await _send(
        websocket, "transcript", speaker="agent", text=result.response_text, timestamp=_now()
    )

    try:
        audio = await _tts.synthesize(result.response_text)
    except TtsUnavailableError as exc:
        logger.error("tts_unavailable", extra={"error": str(exc)})
        audio = b""
    if audio:
        await _send(websocket, "audio", data=encode_audio_chunk(audio))

    # Commit before the final state frame, not after — otherwise a client
    # that reacts to "listening" by immediately sending its next message
    # can race the still-in-flight commit, and the still-not-done() task
    # gets mistaken for an in-progress turn worth interrupting.
    await session.commit()
    await _send(websocket, "agent_state", state="listening")
