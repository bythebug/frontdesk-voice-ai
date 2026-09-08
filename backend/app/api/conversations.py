"""Read-only REST API for conversation observability (the debug timeline page)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories import ConversationRepository, ToolCallRepository

router = APIRouter(prefix="/api/conversations")


class TimelineEvent(BaseModel):
    event_type: str
    timestamp: datetime
    speaker: str | None = None
    text: str | None = None
    tool_name: str | None = None
    status: str | None = None
    latency_ms: int | None = None


class ConversationTimelineResponse(BaseModel):
    conversation_id: str
    status: str
    events: list[TimelineEvent]


@router.get("/{conversation_id}/timeline", response_model=ConversationTimelineResponse)
async def get_conversation_timeline(
    conversation_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ConversationTimelineResponse:
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.get_by_id(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await conv_repo.list_messages(conversation_id)
    tool_calls = await ToolCallRepository(session).list_for_conversation(conversation_id)

    events = [
        TimelineEvent(
            event_type=f"{message.speaker.value.upper()}_MESSAGE",
            timestamp=message.created_at,
            speaker=message.speaker.value,
            text=message.text,
        )
        for message in messages
    ] + [
        TimelineEvent(
            event_type="TOOL_CALL",
            timestamp=tool_call.created_at,
            tool_name=tool_call.tool_name,
            status=tool_call.status.value,
            latency_ms=tool_call.latency_ms,
        )
        for tool_call in tool_calls
    ]
    events.sort(key=lambda e: e.timestamp)

    return ConversationTimelineResponse(
        conversation_id=str(conversation.id), status=conversation.status.value, events=events
    )
