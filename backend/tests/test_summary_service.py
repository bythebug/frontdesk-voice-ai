from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_provider import LLMProvider, LLMUnavailableError
from app.agent.state import ConversationState
from app.db.models import MessageSpeaker, ToolCallStatus
from app.db.repositories import ConversationRepository, CustomerRepository, ToolCallRepository
from app.services.summary_service import SummaryContent, generate_call_summary


class ScriptedStructuredLLM(LLMProvider):
    def __init__(self, content: SummaryContent | None = None, fail: bool = False) -> None:
        self.content = content
        self.fail = fail

    async def generate(self, messages, tools=None):
        raise NotImplementedError

    async def generate_structured(self, messages, response_model):
        if self.fail:
            raise LLMUnavailableError("connection refused")
        assert self.content is not None
        return self.content


async def test_generate_call_summary_persists_expected_fields(db_session: AsyncSession) -> None:
    customer = await CustomerRepository(db_session).create(first_name="John", last_name="Smith")
    conversation = await ConversationRepository(db_session).create(customer_id=customer.id)
    await ConversationRepository(db_session).add_message(
        conversation.id, MessageSpeaker.USER, "I'd like to book a cleaning."
    )
    await ToolCallRepository(db_session).record(
        conversation_id=conversation.id,
        tool_name="check_availability",
        arguments={},
        status=ToolCallStatus.SUCCESS,
        result={"slots": []},
    )
    await ToolCallRepository(db_session).record(
        conversation_id=conversation.id,
        tool_name="book_appointment",
        arguments={},
        status=ToolCallStatus.ERROR,
        error_message="not confirmed",
    )

    state = ConversationState(
        conversation_id=conversation.id,
        customer_id=customer.id,
        intent="appointment_booking",
    )
    llm = ScriptedStructuredLLM(
        content=SummaryContent(
            intent="appointment_booking", issue=None, outcome="Booked a cleaning."
        )
    )

    summary = await generate_call_summary(db_session, llm, state)

    assert summary.customer_name == "John Smith"
    assert summary.intent == "appointment_booking"
    assert summary.summary == "Booked a cleaning."
    # Only the successful tool call counts as an action actually taken.
    assert summary.actions_taken == ["check_availability"]
    assert summary.escalated is False


async def test_generate_call_summary_degrades_gracefully_when_llm_unavailable(
    db_session: AsyncSession,
) -> None:
    conversation = await ConversationRepository(db_session).create()
    state = ConversationState(conversation_id=conversation.id)
    llm = ScriptedStructuredLLM(fail=True)

    summary = await generate_call_summary(db_session, llm, state)

    assert "unavailable" in summary.summary.lower()
