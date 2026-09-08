"""WebSocket endpoint — the browser's only channel to the backend. All
business logic (LLM, tools, DB) stays server-side; the client only ever
exchanges these JSON messages.

Client -> server:
  {"type": "user_text", "text": "..."}          direct text input
  {"type": "audio_chunk", "data": "<base64>"}    mic audio (wired in Phase 6/7)
  {"type": "end_conversation"}

Server -> client:
  {"type": "conversation_started", "conversation_id": "..."}
  {"type": "transcript", "speaker": "user"|"agent", "text": "...", "timestamp": "..."}
  {"type": "agent_state", "state": "listening"|"thinking"|"calling_tool"|"speaking"}
  {"type": "tool_call", "tool": "...", "arguments": {...}}
  {"type": "tool_result", "tool": "...", "success": bool, "data": {...}|null, "error": str|null}
  {"type": "audio", "data": "<base64>"}          synthesized speech (Phase 7)
  {"type": "conversation_ended", "conversation_id": "..."}
  {"type": "error", "message": "..."}
"""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import ConversationAgent
from app.agent.llm_provider import LLMProvider, OllamaProvider
from app.agent.state import ConversationState
from app.core.logging import get_logger
from app.db.database import get_sessionmaker
from app.db.repositories import ConversationRepository

logger = get_logger(__name__)
router = APIRouter()

# Module-level so tests can swap in a fake LLM without a live Ollama —
# referenced by (dynamic) name inside the handler below, not captured at
# import time, so monkeypatching this attribute takes effect.
_llm_provider: LLMProvider = OllamaProvider()


class ClientMessage(BaseModel):
    type: Literal["user_text", "audio_chunk", "end_conversation"]
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
                    await _handle_user_text(websocket, session, agent, message.text)
                    await session.commit()

                elif message.type == "audio_chunk":
                    await _send(
                        websocket,
                        "error",
                        message="Audio input isn't wired up yet — use user_text for now "
                        "(speech-to-text lands in Phase 6).",
                    )

                elif message.type == "end_conversation":
                    await conv_repo.end(conversation.id)
                    await session.commit()
                    await _send(
                        websocket, "conversation_ended", conversation_id=str(conversation.id)
                    )
                    break

        except WebSocketDisconnect:
            logger.info("websocket_disconnected", extra={"conversation_id": str(conversation.id)})


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
    # Phase 7 adds a real "audio" message with synthesized speech here.
    await _send(websocket, "agent_state", state="listening")
