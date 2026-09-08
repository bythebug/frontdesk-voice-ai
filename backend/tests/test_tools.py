import asyncio
from datetime import date, time, timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import app.agent.tool_registry as tool_registry_module
import app.tools  # noqa: F401 — registers all tools on import
from app.agent.tool_registry import ToolRegistry, registry
from app.db.models import (
    AppointmentType,
    AvailabilitySlot,
    ConversationStatus,
    KnowledgeBaseArticle,
    Provider,
)
from app.db.repositories import ConversationRepository, CustomerRepository


async def _seed_provider(session: AsyncSession) -> Provider:
    provider = Provider(name="Dr. Test", title="DDS")
    session.add(provider)
    await session.flush()
    return provider


async def _seed_appointment_type(session: AsyncSession) -> AppointmentType:
    appt_type = AppointmentType(
        name="cleaning", duration_minutes=30, description="", price_cents=1000
    )
    session.add(appt_type)
    await session.flush()
    return appt_type


async def _seed_slot(
    session: AsyncSession, provider: Provider, day: date, hour: int
) -> AvailabilitySlot:
    slot = AvailabilitySlot(
        provider_id=provider.id, slot_date=day, start_time=time(hour, 0), end_time=time(hour, 30)
    )
    session.add(slot)
    await session.flush()
    return slot


async def test_unknown_tool_returns_error(db_session: AsyncSession) -> None:
    result = await registry.execute("does_not_exist", {}, db_session)
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


async def test_tool_execution_times_out(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowInput(BaseModel):
        pass

    class SlowOutput(BaseModel):
        ok: bool = True

    local_registry = ToolRegistry()

    @local_registry.register("slow_tool", "A deliberately slow tool.", SlowInput)
    async def slow_tool(session: AsyncSession, args: SlowInput) -> SlowOutput:
        await asyncio.sleep(1)
        return SlowOutput()

    class FakeSettings:
        tool_timeout_seconds = 0.05

    monkeypatch.setattr(tool_registry_module, "get_settings", lambda: FakeSettings())

    result = await local_registry.execute("slow_tool", {}, db_session)
    assert result.success is False
    assert "timed out" in (result.error or "")


async def test_lookup_customer_not_found(db_session: AsyncSession) -> None:
    result = await registry.execute(
        "lookup_customer", {"first_name": "Nobody", "last_name": "Here"}, db_session
    )
    assert result.success is True
    assert result.data == {
        "found": False,
        "customer_id": None,
        "first_name": None,
        "last_name": None,
        "phone": None,
        "email": None,
    }


async def test_create_then_lookup_customer(db_session: AsyncSession) -> None:
    created = await registry.execute(
        "create_customer",
        {"first_name": "Jane", "last_name": "Doe", "phone": "555-1234"},
        db_session,
    )
    assert created.success is True
    assert created.data is not None

    found = await registry.execute(
        "lookup_customer", {"first_name": "jane", "last_name": "doe"}, db_session
    )
    assert found.success is True
    assert found.data is not None
    assert found.data["found"] is True
    assert found.data["customer_id"] == created.data["customer_id"]


async def test_lookup_customer_invalid_arguments(db_session: AsyncSession) -> None:
    result = await registry.execute("lookup_customer", {"first_name": "Jane"}, db_session)
    assert result.success is False
    assert "Invalid arguments" in (result.error or "")


async def test_check_availability_and_book_full_flow(db_session: AsyncSession) -> None:
    provider = await _seed_provider(db_session)
    await _seed_appointment_type(db_session)
    day = date.today() + timedelta(days=40)
    slot = await _seed_slot(db_session, provider, day, 14)

    customer = await CustomerRepository(db_session).create(first_name="John", last_name="Smith")

    availability = await registry.execute(
        "check_availability", {"date": day.isoformat(), "time_range": "afternoon"}, db_session
    )
    assert availability.success is True
    assert availability.data is not None
    assert len(availability.data["slots"]) == 1
    assert availability.data["slots"][0]["slot_id"] == str(slot.id)

    # Booking without confirmation is rejected.
    unconfirmed = await registry.execute(
        "book_appointment",
        {
            "customer_id": str(customer.id),
            "slot_id": str(slot.id),
            "appointment_type": "cleaning",
            "confirmed": False,
        },
        db_session,
    )
    assert unconfirmed.success is False
    assert "confirmation" in (unconfirmed.error or "").lower()

    booked = await registry.execute(
        "book_appointment",
        {
            "customer_id": str(customer.id),
            "slot_id": str(slot.id),
            "appointment_type": "cleaning",
            "confirmed": True,
        },
        db_session,
    )
    assert booked.success is True
    assert booked.data is not None
    appointment_id = booked.data["appointment_id"]

    # Second booking attempt on the same slot must fail (double-booking).
    double_book = await registry.execute(
        "book_appointment",
        {
            "customer_id": str(customer.id),
            "slot_id": str(slot.id),
            "appointment_type": "cleaning",
            "confirmed": True,
        },
        db_session,
    )
    assert double_book.success is False

    # Cancel requires confirmation too.
    cancel_unconfirmed = await registry.execute(
        "cancel_appointment", {"appointment_id": appointment_id, "confirmed": False}, db_session
    )
    assert cancel_unconfirmed.success is False

    cancel_confirmed = await registry.execute(
        "cancel_appointment", {"appointment_id": appointment_id, "confirmed": True}, db_session
    )
    assert cancel_confirmed.success is True
    assert cancel_confirmed.data is not None
    assert cancel_confirmed.data["status"] == "cancelled"

    # Cancelling again fails — already cancelled.
    cancel_again = await registry.execute(
        "cancel_appointment", {"appointment_id": appointment_id, "confirmed": True}, db_session
    )
    assert cancel_again.success is False


async def test_send_confirmation_for_missing_appointment(db_session: AsyncSession) -> None:
    result = await registry.execute(
        "send_confirmation", {"appointment_id": "00000000-0000-0000-0000-000000000000"}, db_session
    )
    assert result.success is False
    assert "No appointment found" in (result.error or "")


async def test_search_knowledge_base(db_session: AsyncSession) -> None:
    db_session.add(
        KnowledgeBaseArticle(
            category="hours", title="Opening Hours", content="Open Monday to Friday, 9am to 5pm."
        )
    )
    await db_session.flush()

    result = await registry.execute("search_knowledge_base", {"query": "hours"}, db_session)
    assert result.success is True
    assert result.data is not None
    assert len(result.data["results"]) == 1
    assert result.data["results"][0]["category"] == "hours"


async def test_transfer_to_human_escalates_conversation(db_session: AsyncSession) -> None:
    conv_repo = ConversationRepository(db_session)
    conversation = await conv_repo.create()

    result = await registry.execute(
        "transfer_to_human",
        {"conversation_id": str(conversation.id), "reason": "requested a human"},
        db_session,
    )
    assert result.success is True

    reloaded = await conv_repo.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.status == ConversationStatus.ESCALATED
