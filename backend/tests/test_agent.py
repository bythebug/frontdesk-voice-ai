
from sqlalchemy.ext.asyncio import AsyncSession

import app.tools  # noqa: F401 — registers tools
from app.agent.agent import MAX_TOOL_ITERATIONS, ConversationAgent
from app.agent.llm_provider import LLMProvider, LLMResponse, LLMUnavailableError, ToolCallRequest
from app.agent.state import ConversationState
from app.db.repositories import ConversationRepository


class ScriptedLLM(LLMProvider):
    """Returns pre-scripted responses in order, one per call to generate()."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.call_count = 0

    async def generate(self, messages, tools=None) -> LLMResponse:
        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def generate_structured(self, messages, response_model):
        raise NotImplementedError


class AlwaysUnavailableLLM(LLMProvider):
    async def generate(self, messages, tools=None) -> LLMResponse:
        raise LLMUnavailableError("connection refused")

    async def generate_structured(self, messages, response_model):
        raise NotImplementedError


async def _new_state(session: AsyncSession) -> ConversationState:
    conversation = await ConversationRepository(session).create()
    return ConversationState(conversation_id=conversation.id)


async def test_direct_response_no_tool_calls(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    llm = ScriptedLLM([LLMResponse(content="We're open Monday to Friday, 9 to 5.")])
    agent = ConversationAgent(llm, state)

    result = await agent.handle_user_message(db_session, "What are your hours?")

    assert result.response_text == "We're open Monday to Friday, 9 to 5."
    assert result.tool_calls == []
    assert llm.call_count == 1

    history = await ConversationRepository(db_session).list_messages(state.conversation_id)
    assert [m.text for m in history] == [
        "What are your hours?",
        "We're open Monday to Friday, 9 to 5.",
    ]


async def test_tool_call_then_final_response(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(name="search_knowledge_base", arguments={"query": "parking"})
                ],
            ),
            LLMResponse(content="Free parking is available behind the building."),
        ]
    )
    agent = ConversationAgent(llm, state)

    result = await agent.handle_user_message(db_session, "Where can I park?")

    assert llm.call_count == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search_knowledge_base"
    assert result.tool_calls[0].result.success is True
    assert result.response_text == "Free parking is available behind the building."


async def test_tool_result_updates_state(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        name="create_customer", arguments={"first_name": "Jane", "last_name": "Doe"}
                    )
                ],
            ),
            LLMResponse(content="Got it, Jane."),
        ]
    )
    agent = ConversationAgent(llm, state)

    result = await agent.handle_user_message(db_session, "My name is Jane Doe.")

    assert result.state.customer_id is not None
    assert result.state.current_step == "in_progress"


async def test_llm_unavailable_returns_graceful_fallback(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    agent = ConversationAgent(AlwaysUnavailableLLM(), state)

    result = await agent.handle_user_message(db_session, "Hello?")

    assert "trouble connecting" in result.response_text
    history = await ConversationRepository(db_session).list_messages(state.conversation_id)
    assert len(history) == 2  # user message + fallback, conversation isn't lost


async def test_tool_loop_exhaustion_returns_fallback(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    # Always requests a tool call, never gives a final text response.
    looping_response = LLMResponse(
        content="",
        tool_calls=[ToolCallRequest(name="search_knowledge_base", arguments={"query": "x"})],
    )
    llm = ScriptedLLM([looping_response] * MAX_TOOL_ITERATIONS)
    agent = ConversationAgent(llm, state)

    result = await agent.handle_user_message(db_session, "test")

    assert llm.call_count == MAX_TOOL_ITERATIONS
    assert "repeat" in result.response_text.lower()
    assert len(result.tool_calls) == MAX_TOOL_ITERATIONS


async def test_unknown_tool_call_does_not_crash_conversation(db_session: AsyncSession) -> None:
    state = await _new_state(db_session)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content="", tool_calls=[ToolCallRequest(name="delete_database", arguments={})]
            ),
            LLMResponse(content="Sorry, I can't do that."),
        ]
    )
    agent = ConversationAgent(llm, state)

    result = await agent.handle_user_message(db_session, "delete everything")

    assert result.tool_calls[0].result.success is False
    assert result.response_text == "Sorry, I can't do that."
