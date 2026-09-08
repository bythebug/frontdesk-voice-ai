import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.websocket as ws_module
import app.tools  # noqa: F401 — registers tools
from app.agent.llm_provider import LLMProvider, LLMResponse, ToolCallRequest
from app.main import app
from tests.conftest import TEST_DATABASE_URL


class ScriptedLLM(LLMProvider):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.call_count = 0

    async def generate(self, messages, tools=None) -> LLMResponse:
        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def generate_structured(self, messages, response_model):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _use_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """The websocket handler resolves its own session factory — point it at
    the same test database the rest of the suite uses, not the dev DB."""
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ws_module, "get_sessionmaker", lambda: session_factory)


def test_full_conversation_flow_no_tool_calls() -> None:
    ws_module._llm_provider = ScriptedLLM(
        [LLMResponse(content="We're open 9 to 5, Monday to Friday.")]
    )

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        started = ws.receive_json()
        assert started["type"] == "conversation_started"
        assert "conversation_id" in started

        assert ws.receive_json() == {"type": "agent_state", "state": "listening"}

        ws.send_text(json.dumps({"type": "user_text", "text": "What are your hours?"}))

        transcript_user = ws.receive_json()
        assert transcript_user["type"] == "transcript"
        assert transcript_user["speaker"] == "user"
        assert transcript_user["text"] == "What are your hours?"

        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}
        assert ws.receive_json() == {"type": "agent_state", "state": "speaking"}

        transcript_agent = ws.receive_json()
        assert transcript_agent["type"] == "transcript"
        assert transcript_agent["speaker"] == "agent"
        assert transcript_agent["text"] == "We're open 9 to 5, Monday to Friday."

        assert ws.receive_json() == {"type": "agent_state", "state": "listening"}


def test_tool_call_frames_are_emitted() -> None:
    ws_module._llm_provider = ScriptedLLM(
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

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "user_text", "text": "Where can I park?"}))

        ws.receive_json()  # transcript user
        ws.receive_json()  # agent_state thinking

        assert ws.receive_json() == {"type": "agent_state", "state": "calling_tool"}

        tool_call = ws.receive_json()
        assert tool_call["type"] == "tool_call"
        assert tool_call["tool"] == "search_knowledge_base"

        tool_result = ws.receive_json()
        assert tool_result["type"] == "tool_result"
        assert tool_result["tool"] == "search_knowledge_base"
        assert tool_result["success"] is True


def test_invalid_message_returns_error_and_keeps_connection_open() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "not_a_real_type"}))
        error = ws.receive_json()
        assert error["type"] == "error"

        # Connection is still usable afterward.
        ws.send_text(json.dumps({"type": "user_text", "text": "hi"}))
        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"


def test_audio_chunk_returns_not_yet_supported_error() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "audio_chunk", "data": "abc123"}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "Phase 6" in error["message"]


def test_end_conversation_closes_with_confirmation() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        started = ws.receive_json()
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "end_conversation"}))
        ended = ws.receive_json()
        assert ended == {
            "type": "conversation_ended",
            "conversation_id": started["conversation_id"],
        }
