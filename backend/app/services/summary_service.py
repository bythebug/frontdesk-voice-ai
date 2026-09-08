"""Generates a structured call summary when a conversation ends.

Factual fields (appointment, escalation, tools used) come from
ConversationState / the DB — ground truth from actual tool results, never
guessed. Only the free-text narrative (intent/issue/outcome/summary) comes
from the LLM, and only from what's actually in the transcript.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_provider import LLMProvider, LLMUnavailableError
from app.agent.state import ConversationState
from app.core.logging import get_logger
from app.db.models import CallSummary, MessageSpeaker, ToolCallStatus
from app.db.repositories import (
    CallSummaryRepository,
    ConversationRepository,
    CustomerRepository,
    ToolCallRepository,
)

logger = get_logger(__name__)

SUMMARY_SYSTEM_PROMPT = """Summarize this dental clinic support call. Base \
every field only on what actually happened in the transcript below — never \
invent details. If something didn't come up, leave it null. "outcome" is a \
one-sentence result of the call, e.g. "Appointment successfully booked" or \
"Answered a question about parking"."""


class SummaryContent(BaseModel):
    intent: str | None = None
    issue: str | None = None
    outcome: str


async def generate_call_summary(
    session: AsyncSession, llm: LLMProvider, state: ConversationState
) -> CallSummary:
    conv_repo = ConversationRepository(session)
    messages = await conv_repo.list_messages(state.conversation_id)
    transcript = "\n".join(
        f"{m.speaker.value}: {m.text}" for m in messages if m.speaker != MessageSpeaker.SYSTEM
    )

    customer_name = None
    if state.customer_id:
        customer = await CustomerRepository(session).get_by_id(state.customer_id)
        if customer:
            customer_name = f"{customer.first_name} {customer.last_name}"

    tool_calls = await ToolCallRepository(session).list_for_conversation(state.conversation_id)
    actions_taken = [tc.tool_name for tc in tool_calls if tc.status == ToolCallStatus.SUCCESS]

    try:
        content = await llm.generate_structured(
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript or "(no messages exchanged)"},
            ],
            SummaryContent,
        )
    except LLMUnavailableError as exc:
        logger.error(
            "summary_llm_unavailable",
            extra={"conversation_id": str(state.conversation_id), "error": str(exc)},
        )
        content = SummaryContent(
            outcome="Summary unavailable — the reasoning engine couldn't be reached."
        )

    return await CallSummaryRepository(session).create(
        conversation_id=state.conversation_id,
        summary=content.outcome,
        customer_name=customer_name,
        intent=content.intent or state.intent,
        issue=content.issue,
        actions_taken=actions_taken,
        appointment_id=state.last_appointment_id,
        escalated=state.escalated,
    )
