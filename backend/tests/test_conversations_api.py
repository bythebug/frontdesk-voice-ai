import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.db.models import MessageSpeaker, ToolCallStatus
from app.db.repositories import ConversationRepository, ToolCallRepository
from app.main import app
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def _use_test_database():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


async def _seed_conversation(db_session):
    conv_repo = ConversationRepository(db_session)
    conversation = await conv_repo.create()
    await conv_repo.add_message(conversation.id, MessageSpeaker.USER, "Hi")
    await conv_repo.add_message(conversation.id, MessageSpeaker.AGENT, "Hello")
    await ToolCallRepository(db_session).record(
        conversation_id=conversation.id,
        tool_name="search_knowledge_base",
        arguments={"query": "hours"},
        status=ToolCallStatus.SUCCESS,
        latency_ms=42,
    )
    await db_session.commit()
    return conversation


async def test_timeline_returns_ordered_events(db_session) -> None:
    conversation = await _seed_conversation(db_session)

    with TestClient(app) as client:
        response = client.get(f"/api/conversations/{conversation.id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == str(conversation.id)
    assert body["status"] == "active"
    event_types = [e["event_type"] for e in body["events"]]
    assert event_types == ["USER_MESSAGE", "AGENT_MESSAGE", "TOOL_CALL"]
    tool_event = body["events"][2]
    assert tool_event["tool_name"] == "search_knowledge_base"
    assert tool_event["latency_ms"] == 42


def test_timeline_404_for_unknown_conversation() -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/conversations/{uuid.uuid4()}/timeline")
    assert response.status_code == 404
