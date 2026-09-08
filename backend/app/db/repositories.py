"""Data-access layer. Tools (Phase 3) call these; they never touch the ORM directly."""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    AvailabilitySlot,
    CallSummary,
    Conversation,
    ConversationStatus,
    Customer,
    KnowledgeBaseArticle,
    Message,
    MessageSpeaker,
    Provider,
    ToolCall,
    ToolCallStatus,
)


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        return await self.session.get(Customer, customer_id)

    async def find_by_name(self, first_name: str, last_name: str) -> Customer | None:
        stmt = select(Customer).where(
            Customer.first_name.ilike(first_name), Customer.last_name.ilike(last_name)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self, first_name: str, last_name: str, phone: str | None = None, email: str | None = None
    ) -> Customer:
        customer = Customer(first_name=first_name, last_name=last_name, phone=phone, email=email)
        self.session.add(customer)
        await self.session.flush()
        return customer


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Provider]:
        return list((await self.session.execute(select(Provider))).scalars().all())

    async def get_by_id(self, provider_id: uuid.UUID) -> Provider | None:
        return await self.session.get(Provider, provider_id)

    async def find_by_name(self, name: str) -> Provider | None:
        stmt = select(Provider).where(Provider.name.ilike(f"%{name}%"))
        return (await self.session.execute(stmt)).scalars().first()


class AppointmentTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, name: str) -> AppointmentType | None:
        stmt = select(AppointmentType).where(AppointmentType.name.ilike(name))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[AppointmentType]:
        return list((await self.session.execute(select(AppointmentType))).scalars().all())


class AvailabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, slot_id: uuid.UUID) -> AvailabilitySlot | None:
        return await self.session.get(AvailabilitySlot, slot_id)

    async def find_open_slots(
        self,
        slot_date: date,
        start_time: time | None = None,
        end_time: time | None = None,
        provider_id: uuid.UUID | None = None,
    ) -> list[AvailabilitySlot]:
        stmt = select(AvailabilitySlot).where(
            AvailabilitySlot.slot_date == slot_date, AvailabilitySlot.is_booked.is_(False)
        )
        if start_time is not None:
            stmt = stmt.where(AvailabilitySlot.start_time >= start_time)
        if end_time is not None:
            stmt = stmt.where(AvailabilitySlot.start_time < end_time)
        if provider_id is not None:
            stmt = stmt.where(AvailabilitySlot.provider_id == provider_id)
        stmt = stmt.order_by(AvailabilitySlot.start_time)
        return list((await self.session.execute(stmt)).scalars().all())

    async def try_book(self, slot_id: uuid.UUID) -> bool:
        """Atomically claim a slot. Returns False if it was already booked
        (or doesn't exist) — the caller must not proceed to create an
        appointment in that case, preventing double-booking races."""
        stmt = (
            update(AvailabilitySlot)
            .where(AvailabilitySlot.id == slot_id, AvailabilitySlot.is_booked.is_(False))
            .values(is_booked=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount == 1  # type: ignore[attr-defined]  # CursorResult at runtime

    async def release(self, slot_id: uuid.UUID) -> None:
        stmt = (
            update(AvailabilitySlot)
            .where(AvailabilitySlot.id == slot_id)
            .values(is_booked=False)
        )
        await self.session.execute(stmt)


class AppointmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        customer_id: uuid.UUID,
        provider_id: uuid.UUID,
        appointment_type_id: uuid.UUID,
        slot_id: uuid.UUID,
        notes: str | None = None,
    ) -> Appointment:
        appointment = Appointment(
            customer_id=customer_id,
            provider_id=provider_id,
            appointment_type_id=appointment_type_id,
            slot_id=slot_id,
            notes=notes,
        )
        self.session.add(appointment)
        await self.session.flush()
        return appointment

    async def get_by_id(self, appointment_id: uuid.UUID) -> Appointment | None:
        return await self.session.get(Appointment, appointment_id)

    async def cancel(self, appointment_id: uuid.UUID) -> Appointment | None:
        appointment = await self.get_by_id(appointment_id)
        if appointment is None or appointment.status != AppointmentStatus.SCHEDULED:
            return None
        appointment.status = AppointmentStatus.CANCELLED
        await AvailabilityRepository(self.session).release(appointment.slot_id)
        await self.session.flush()
        return appointment


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, customer_id: uuid.UUID | None = None) -> Conversation:
        conversation = Conversation(customer_id=customer_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def add_message(
        self, conversation_id: uuid.UUID, speaker: MessageSpeaker, text_content: str
    ) -> Message:
        message = Message(conversation_id=conversation_id, speaker=speaker, text=text_content)
        self.session.add(message)
        await self.session.flush()
        return message

    async def set_status(self, conversation_id: uuid.UUID, status: ConversationStatus) -> None:
        conversation = await self.get_by_id(conversation_id)
        if conversation is not None:
            conversation.status = status
            await self.session.flush()

    async def end(self, conversation_id: uuid.UUID) -> None:
        """Mark a conversation as ended. Leaves an already-ESCALATED status
        alone; otherwise marks it COMPLETED."""
        conversation = await self.get_by_id(conversation_id)
        if conversation is None:
            return
        conversation.ended_at = datetime.now(UTC)
        if conversation.status != ConversationStatus.ESCALATED:
            conversation.status = ConversationStatus.COMPLETED
        await self.session.flush()

    async def list_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class ToolCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        conversation_id: uuid.UUID,
        tool_name: str,
        arguments: dict,
        status: ToolCallStatus,
        result: dict | None = None,
        error_message: str | None = None,
        latency_ms: int | None = None,
        message_id: uuid.UUID | None = None,
    ) -> ToolCall:
        tool_call = ToolCall(
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            status=status,
            error_message=error_message,
            latency_ms=latency_ms,
        )
        self.session.add(tool_call)
        await self.session.flush()
        return tool_call

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[ToolCall]:
        stmt = (
            select(ToolCall)
            .where(ToolCall.conversation_id == conversation_id)
            .order_by(ToolCall.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class CallSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        conversation_id: uuid.UUID,
        summary: str,
        customer_name: str | None = None,
        intent: str | None = None,
        issue: str | None = None,
        actions_taken: list[str] | None = None,
        appointment_id: uuid.UUID | None = None,
        escalated: bool = False,
    ) -> CallSummary:
        call_summary = CallSummary(
            conversation_id=conversation_id,
            customer_name=customer_name,
            intent=intent,
            issue=issue,
            actions_taken=actions_taken or [],
            appointment_id=appointment_id,
            escalated=escalated,
            summary=summary,
        )
        self.session.add(call_summary)
        await self.session.flush()
        return call_summary


class KnowledgeBaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, limit: int = 3) -> list[KnowledgeBaseArticle]:
        matches = text(
            "to_tsvector('english', title || ' ' || content) @@ plainto_tsquery('english', :q)"
        ).bindparams(q=query)
        rank = text(
            "ts_rank(to_tsvector('english', title || ' ' || content), "
            "plainto_tsquery('english', :q)) DESC"
        ).bindparams(q=query)
        stmt = select(KnowledgeBaseArticle).where(matches).order_by(rank).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
