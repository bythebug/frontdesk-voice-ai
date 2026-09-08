"""SQLAlchemy ORM models for the FrontDesk Voice AI schema."""

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class AppointmentStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ConversationStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ESCALATED = "escalated"


class MessageSpeaker(enum.StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class ToolCallStatus(enum.StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppointmentType(Base):
    __tablename__ = "appointment_types"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (UniqueConstraint("provider_id", "slot_date", "start_time"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"))
    slot_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    is_booked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider: Mapped[Provider] = relationship()


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"))
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment_types.id"))
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("availability_slots.id"), unique=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"), default=AppointmentStatus.SCHEDULED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship()
    provider: Mapped[Provider] = relationship()
    appointment_type: Mapped[AppointmentType] = relationship()
    slot: Mapped[AvailabilitySlot] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"), default=ConversationStatus.ACTIVE
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    speaker: Mapped[MessageSpeaker] = mapped_column(Enum(MessageSpeaker, name="message_speaker"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ToolCallStatus] = mapped_column(Enum(ToolCallStatus, name="tool_call_status"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), unique=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions_taken: Mapped[list] = mapped_column(JSON, default=list)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id"), nullable=True
    )
    escalated: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBaseArticle(Base):
    """Small fixed-size clinic KB, retrieved via Postgres full-text search
    (see the functional GIN index added in the initial migration)."""

    __tablename__ = "knowledge_base"

    id: Mapped[uuid.UUID] = _uuid_pk()
    category: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
