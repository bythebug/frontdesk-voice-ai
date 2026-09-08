from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppointmentStatus, ConversationStatus, MessageSpeaker, ToolCallStatus
from app.db.repositories import (
    AppointmentRepository,
    AppointmentTypeRepository,
    AvailabilityRepository,
    CallSummaryRepository,
    ConversationRepository,
    CustomerRepository,
    KnowledgeBaseArticle,
    KnowledgeBaseRepository,
    Provider,
    ToolCallRepository,
)


async def _make_customer(session: AsyncSession, first="John", last="Smith"):
    return await CustomerRepository(session).create(
        first_name=first, last_name=last, phone="555-0100"
    )


async def _make_provider(session: AsyncSession) -> Provider:
    provider = Provider(name="Dr. Test", title="DDS")
    session.add(provider)
    await session.flush()
    return provider


async def _make_appointment_type(session: AsyncSession):
    existing = await AppointmentTypeRepository(session).get_by_name("cleaning")
    return existing or await _seed_appt_type(session)


async def _seed_appt_type(session: AsyncSession):
    from app.db.models import AppointmentType

    at = AppointmentType(name="cleaning", duration_minutes=30, description="test", price_cents=1000)
    session.add(at)
    await session.flush()
    return at


async def test_customer_create_and_lookup(db_session: AsyncSession) -> None:
    created = await _make_customer(db_session)
    found = await CustomerRepository(db_session).find_by_name("john", "smith")
    assert found is not None
    assert found.id == created.id


async def test_customer_lookup_missing_returns_none(db_session: AsyncSession) -> None:
    found = await CustomerRepository(db_session).find_by_name("Nobody", "Here")
    assert found is None


async def test_availability_find_open_slots(db_session: AsyncSession) -> None:
    provider = await _make_provider(db_session)
    from app.db.models import AvailabilitySlot

    day = date.today() + timedelta(days=30)
    slot = AvailabilitySlot(
        provider_id=provider.id, slot_date=day, start_time=time(14, 0), end_time=time(14, 30)
    )
    db_session.add(slot)
    await db_session.flush()

    open_slots = await AvailabilityRepository(db_session).find_open_slots(
        day, start_time=time(12, 0)
    )
    assert len(open_slots) == 1
    assert open_slots[0].id == slot.id


async def test_booking_prevents_double_booking(db_session: AsyncSession) -> None:
    provider = await _make_provider(db_session)
    from app.db.models import AvailabilitySlot

    day = date.today() + timedelta(days=31)
    slot = AvailabilitySlot(
        provider_id=provider.id, slot_date=day, start_time=time(9, 0), end_time=time(9, 30)
    )
    db_session.add(slot)
    await db_session.flush()

    availability_repo = AvailabilityRepository(db_session)
    first_attempt = await availability_repo.try_book(slot.id)
    second_attempt = await availability_repo.try_book(slot.id)

    assert first_attempt is True
    assert second_attempt is False


async def test_book_and_cancel_appointment_frees_slot(db_session: AsyncSession) -> None:
    provider = await _make_provider(db_session)
    customer = await _make_customer(db_session, "Jane", "Doe")
    appt_type = await _make_appointment_type(db_session)
    from app.db.models import AvailabilitySlot

    day = date.today() + timedelta(days=32)
    slot = AvailabilitySlot(
        provider_id=provider.id, slot_date=day, start_time=time(10, 0), end_time=time(10, 30)
    )
    db_session.add(slot)
    await db_session.flush()

    availability_repo = AvailabilityRepository(db_session)
    assert await availability_repo.try_book(slot.id) is True

    appt_repo = AppointmentRepository(db_session)
    appointment = await appt_repo.create(
        customer_id=customer.id,
        provider_id=provider.id,
        appointment_type_id=appt_type.id,
        slot_id=slot.id,
        notes="tooth pain",
    )
    assert appointment.status == AppointmentStatus.SCHEDULED

    cancelled = await appt_repo.cancel(appointment.id)
    assert cancelled is not None
    assert cancelled.status == AppointmentStatus.CANCELLED

    await db_session.refresh(slot)
    assert slot.is_booked is False


async def test_cancel_nonexistent_appointment_returns_none(db_session: AsyncSession) -> None:
    import uuid

    result = await AppointmentRepository(db_session).cancel(uuid.uuid4())
    assert result is None


async def test_conversation_state_and_messages(db_session: AsyncSession) -> None:
    conv_repo = ConversationRepository(db_session)
    conversation = await conv_repo.create()
    assert conversation.status == ConversationStatus.ACTIVE

    await conv_repo.add_message(conversation.id, MessageSpeaker.USER, "Hi, I need an appointment.")
    await conv_repo.add_message(conversation.id, MessageSpeaker.AGENT, "Sure, what day works?")

    await conv_repo.set_status(conversation.id, ConversationStatus.ESCALATED)
    reloaded = await conv_repo.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.status == ConversationStatus.ESCALATED

    messages = await conv_repo.list_messages(conversation.id)
    assert len(messages) == 2


async def test_tool_call_and_summary_recorded(db_session: AsyncSession) -> None:
    conversation = await ConversationRepository(db_session).create()

    tool_call = await ToolCallRepository(db_session).record(
        conversation_id=conversation.id,
        tool_name="check_availability",
        arguments={"date": "2026-09-11"},
        status=ToolCallStatus.SUCCESS,
        result={"slots": []},
        latency_ms=42,
    )
    assert tool_call.status == ToolCallStatus.SUCCESS

    summary = await CallSummaryRepository(db_session).create(
        conversation_id=conversation.id,
        summary="Customer asked about availability.",
        intent="appointment_booking",
        actions_taken=["checked availability"],
    )
    assert summary.conversation_id == conversation.id


async def test_knowledge_base_search(db_session: AsyncSession) -> None:
    db_session.add(
        KnowledgeBaseArticle(
            category="hours",
            title="Opening Hours",
            content="We are open Monday to Friday 9am to 5pm.",
        )
    )
    db_session.add(
        KnowledgeBaseArticle(
            category="parking",
            title="Parking Information",
            content="Free parking is available behind the building.",
        )
    )
    await db_session.flush()

    results = await KnowledgeBaseRepository(db_session).search("parking")
    assert len(results) == 1
    assert results[0].category == "parking"
