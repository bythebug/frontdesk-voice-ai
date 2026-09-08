import asyncio
import base64
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.websocket as ws_module
import app.tools  # noqa: F401 — registers tools
from app.agent.llm_provider import LLMProvider, LLMResponse, ToolCallRequest
from app.main import app
from app.voice.stt import SpeechToText, SttUnavailableError
from tests.conftest import TEST_DATABASE_URL


class ScriptedLLM(LLMProvider):
    def __init__(self, responses: list[LLMResponse], delay: float = 0.0) -> None:
        self.responses = responses
        self.delay = delay
        self.call_count = 0

    async def generate(self, messages, tools=None) -> LLMResponse:
        # Claim this call's response before sleeping — if this call gets
        # cancelled mid-sleep (barge-in), the *next* call still advances
        # rather than replaying the same response.
        response = self.responses[self.call_count]
        self.call_count += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return response

    async def generate_structured(self, messages, response_model):
        # Only SummaryContent is ever requested (end_conversation's summary
        # generation) — a minimal valid instance is enough for these tests.
        return response_model(outcome="Call completed.")


class CrashingLLM(LLMProvider):
    """Simulates an unexpected (non-LLMUnavailableError) failure deep in a
    turn, e.g. a DB connection dropping mid-conversation."""

    async def generate(self, messages, tools=None) -> LLMResponse:
        raise RuntimeError("simulated unexpected failure")

    async def generate_structured(self, messages, response_model):
        raise RuntimeError("simulated unexpected failure")


def _loud_audio_chunk() -> str:
    samples = (np.ones(800, dtype=np.int16) * 20000).tobytes()
    return base64.b64encode(samples).decode("ascii")


class FakeSTT(SpeechToText):
    def __init__(self, transcript: str = "", raise_error: bool = False) -> None:
        self.transcript = transcript
        self.raise_error = raise_error
        self.received_audio: bytes | None = None

    async def transcribe(self, audio: bytes) -> str:
        self.received_audio = audio
        if self.raise_error:
            raise SttUnavailableError("model failed to load")
        return self.transcript


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


def test_malformed_audio_chunk_returns_error_without_crashing() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "audio_chunk", "data": "not valid base64!!"}))
        error = ws.receive_json()
        assert error["type"] == "error"

        # Connection survives.
        ws.send_text(json.dumps({"type": "user_text", "text": "hi"}))
        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"


def test_audio_chunk_then_end_transcribes_and_drives_agent() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="We're open 9 to 5.")])
    fake_stt = FakeSTT(transcript="What are your hours?")
    ws_module._stt = fake_stt

    audio_bytes = b"\x01\x02\x03\x04"
    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(
            json.dumps(
                {"type": "audio_chunk", "data": base64.b64encode(audio_bytes).decode("ascii")}
            )
        )
        ws.send_text(json.dumps({"type": "audio_end"}))

        transcript_user = ws.receive_json()
        assert transcript_user["type"] == "transcript"
        assert transcript_user["speaker"] == "user"
        assert transcript_user["text"] == "What are your hours?"

    assert fake_stt.received_audio == audio_bytes


def test_audio_end_with_no_chunks_is_an_error() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])
    ws_module._stt = FakeSTT(transcript="hello")

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "audio_end"}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "No audio" in error["message"]


def test_stt_failure_returns_error_without_crashing_connection() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])
    ws_module._stt = FakeSTT(raise_error=True)

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "audio_chunk", "data": base64.b64encode(b"x").decode()}))
        ws.send_text(json.dumps({"type": "audio_end"}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "Speech recognition failed" in error["message"]

        # Connection survives — can still use text.
        ws.send_text(json.dumps({"type": "user_text", "text": "hi"}))
        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"


def test_unexpected_turn_failure_sends_error_and_connection_survives() -> None:
    # LLMProvider is captured once per connection, so this simulates an
    # unexpected failure (e.g. a dropped DB connection) that would recur
    # on every turn — proving the *connection* survives it repeatedly
    # (no hang, no disconnect) is what matters here, not recovery to a
    # successful response from the same broken provider.
    ws_module._llm_provider = CrashingLLM()

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        for _ in range(2):
            ws.send_text(json.dumps({"type": "user_text", "text": "hi"}))
            ws.receive_json()  # transcript user
            ws.receive_json()  # agent_state thinking

            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["message"]

            assert ws.receive_json() == {"type": "agent_state", "state": "listening"}


def test_empty_transcript_asks_user_to_repeat() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])
    ws_module._stt = FakeSTT(transcript="")  # silence / no speech detected

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "audio_chunk", "data": base64.b64encode(b"x").decode()}))
        ws.send_text(json.dumps({"type": "audio_end"}))
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "repeat" in error["message"].lower()


def test_end_conversation_closes_with_confirmation() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="ok")])

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        started = ws.receive_json()
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "end_conversation"}))

        summary = ws.receive_json()
        assert summary["type"] == "call_summary"
        assert summary["outcome"] == "Call completed."

        ended = ws.receive_json()
        assert ended == {
            "type": "conversation_ended",
            "conversation_id": started["conversation_id"],
        }


def test_barge_in_interrupts_in_flight_turn_and_new_turn_still_works() -> None:
    # Delay every call generously — barge-in can land during the agent's DB
    # work before the LLM is even reached, or during the LLM call itself;
    # either is a legitimate interruption point, so the response content
    # itself (not which call index survives) isn't what this test checks.
    ws_module._llm_provider = ScriptedLLM(
        [LLMResponse(content="a response"), LLMResponse(content="a response")], delay=0.3
    )

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "user_text", "text": "first message"}))
        assert ws.receive_json()["text"] == "first message"
        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}

        # The first turn is still in flight. Loud audio arriving now is a
        # real barge-in signal, not routine mic noise.
        ws.send_text(json.dumps({"type": "audio_chunk", "data": _loud_audio_chunk()}))

        assert ws.receive_json() == {"type": "agent_state", "state": "interrupted"}
        assert ws.receive_json() == {"type": "agent_state", "state": "listening"}

        # A fresh turn starts cleanly after the interruption — no crash, no
        # leftover frames from the cancelled one, normal state sequence.
        ws.send_text(json.dumps({"type": "user_text", "text": "second message"}))
        assert ws.receive_json()["text"] == "second message"
        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}
        assert ws.receive_json() == {"type": "agent_state", "state": "speaking"}
        transcript = ws.receive_json()
        assert transcript["speaker"] == "agent"
        assert transcript["text"] == "a response"
        assert ws.receive_json() == {"type": "agent_state", "state": "listening"}


def test_quiet_audio_chunk_during_a_turn_does_not_interrupt() -> None:
    ws_module._llm_provider = ScriptedLLM([LLMResponse(content="a response")], delay=0.2)

    with TestClient(app) as client, client.websocket_connect("/ws/conversation") as ws:
        ws.receive_json()  # conversation_started
        ws.receive_json()  # agent_state listening

        ws.send_text(json.dumps({"type": "user_text", "text": "hello"}))
        ws.receive_json()  # transcript user
        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}

        silent = base64.b64encode(np.zeros(800, dtype=np.int16).tobytes()).decode("ascii")
        ws.send_text(json.dumps({"type": "audio_chunk", "data": silent}))

        # No interruption — the turn runs to completion normally.
        assert ws.receive_json() == {"type": "agent_state", "state": "speaking"}
        transcript = ws.receive_json()
        assert transcript["text"] == "a response"
