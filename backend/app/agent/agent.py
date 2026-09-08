"""Top-level conversation orchestration: state -> LLM -> tool selection ->
tool execution -> LLM response. The only module that wires state.py,
prompts.py, llm_provider.py, and tool_registry.py together.

Tool results are fed back to the LLM as system messages (rather than a
dedicated "tool" role) so no DB schema change was needed for
MessageSpeaker — a deliberate simplification, not a missing feature.
"""

import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_provider import LLMProvider, LLMUnavailableError
from app.agent.prompts import build_messages
from app.agent.state import ConversationState
from app.agent.tool_registry import ToolResult, registry
from app.core.logging import get_logger
from app.db.models import MessageSpeaker, ToolCallStatus
from app.db.repositories import ConversationRepository, ToolCallRepository

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 3
LLM_UNAVAILABLE_MESSAGE = (
    "I'm having trouble connecting to my reasoning engine right now. Please try again in a moment."
)
TOOL_LOOP_EXHAUSTED_MESSAGE = "Let me get back to you on that — could you repeat what you need?"


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict
    result: ToolResult


@dataclass
class AgentTurnResult:
    response_text: str
    state: ConversationState
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


class ConversationAgent:
    def __init__(self, llm: LLMProvider, state: ConversationState) -> None:
        self.llm = llm
        self.state = state

    async def handle_user_message(self, session: AsyncSession, text: str) -> AgentTurnResult:
        conv_repo = ConversationRepository(session)
        tool_call_repo = ToolCallRepository(session)
        await conv_repo.add_message(self.state.conversation_id, MessageSpeaker.USER, text)

        tool_call_records: list[ToolCallRecord] = []
        for _ in range(MAX_TOOL_ITERATIONS):
            history = await conv_repo.list_messages(self.state.conversation_id)
            messages = build_messages(self.state, history)

            llm_start = time.monotonic()
            try:
                response = await self.llm.generate(messages, tools=registry.schemas())
            except LLMUnavailableError as exc:
                logger.error(
                    "llm_unavailable",
                    extra={"conversation_id": str(self.state.conversation_id), "error": str(exc)},
                )
                await conv_repo.add_message(
                    self.state.conversation_id, MessageSpeaker.AGENT, LLM_UNAVAILABLE_MESSAGE
                )
                return AgentTurnResult(
                    response_text=LLM_UNAVAILABLE_MESSAGE,
                    state=self.state,
                    tool_calls=tool_call_records,
                )

            llm_latency_ms = int((time.monotonic() - llm_start) * 1000)
            logger.info(
                "llm_response",
                extra={
                    "conversation_id": str(self.state.conversation_id),
                    "latency_ms": llm_latency_ms,
                    "tool_call_count": len(response.tool_calls),
                },
            )

            if not response.tool_calls:
                await conv_repo.add_message(
                    self.state.conversation_id, MessageSpeaker.AGENT, response.content
                )
                return AgentTurnResult(
                    response_text=response.content, state=self.state, tool_calls=tool_call_records
                )

            for call in response.tool_calls:
                result = await registry.execute(call.name, call.arguments, session)
                self.state.apply_tool_result(call.name, call.arguments, result.success, result.data)
                tool_call_records.append(
                    ToolCallRecord(name=call.name, arguments=call.arguments, result=result)
                )
                await tool_call_repo.record(
                    conversation_id=self.state.conversation_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                    status=ToolCallStatus.SUCCESS if result.success else ToolCallStatus.ERROR,
                    result=result.data,
                    error_message=result.error,
                    latency_ms=result.latency_ms,
                )
                logger.info(
                    "tool_call",
                    extra={
                        "conversation_id": str(self.state.conversation_id),
                        "tool": call.name,
                        "success": result.success,
                        "latency_ms": result.latency_ms,
                    },
                )
                outcome = result.data if result.success else {"error": result.error}
                await conv_repo.add_message(
                    self.state.conversation_id,
                    MessageSpeaker.SYSTEM,
                    f"[tool:{call.name}] {outcome}",
                )

        await conv_repo.add_message(
            self.state.conversation_id, MessageSpeaker.AGENT, TOOL_LOOP_EXHAUSTED_MESSAGE
        )
        return AgentTurnResult(
            response_text=TOOL_LOOP_EXHAUSTED_MESSAGE,
            state=self.state,
            tool_calls=tool_call_records,
        )
