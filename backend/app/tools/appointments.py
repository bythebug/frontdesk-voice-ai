"""Appointment scheduling tools: availability, booking, cancellation.

Simplification: every appointment consumes exactly one 30-minute slot,
regardless of appointment_type.duration_minutes. A production system would
reserve multiple contiguous slots for longer procedures (e.g. fillings);
that's out of scope for this portfolio project.
"""

import uuid
from datetime import date as date_type
from datetime import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_registry import ToolExecutionError, registry
from app.db.repositories import (
    AppointmentRepository,
    AppointmentTypeRepository,
    AvailabilityRepository,
    CustomerRepository,
    ProviderRepository,
)

TimeRange = Literal["morning", "afternoon", "all_day"]

_TIME_RANGE_BOUNDS: dict[TimeRange, tuple[time, time]] = {
    "morning": (time(9, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "all_day": (time(9, 0), time(17, 0)),
}


class CheckAvailabilityInput(BaseModel):
    date: date_type
    time_range: TimeRange = "all_day"
    provider_name: str | None = None


class SlotOut(BaseModel):
    slot_id: str
    provider_name: str
    date: date_type
    start_time: str
    end_time: str


class CheckAvailabilityOutput(BaseModel):
    slots: list[SlotOut]


@registry.register(
    "check_availability",
    "Find open appointment slots on a given date and time of day (morning/afternoon/all_day).",
    CheckAvailabilityInput,
)
async def check_availability(
    session: AsyncSession, args: CheckAvailabilityInput
) -> CheckAvailabilityOutput:
    provider_id = None
    if args.provider_name:
        provider = await ProviderRepository(session).find_by_name(args.provider_name)
        if provider is None:
            raise ToolExecutionError(f"No provider found matching '{args.provider_name}'.")
        provider_id = provider.id

    start, end = _TIME_RANGE_BOUNDS[args.time_range]
    slots = await AvailabilityRepository(session).find_open_slots(
        args.date, start_time=start, end_time=end, provider_id=provider_id
    )

    providers_by_id = {p.id: p for p in await ProviderRepository(session).list_all()}
    return CheckAvailabilityOutput(
        slots=[
            SlotOut(
                slot_id=str(slot.id),
                provider_name=providers_by_id[slot.provider_id].name,
                date=slot.slot_date,
                start_time=slot.start_time.strftime("%H:%M"),
                end_time=slot.end_time.strftime("%H:%M"),
            )
            for slot in slots
        ]
    )


class BookAppointmentInput(BaseModel):
    customer_id: str
    slot_id: str
    appointment_type: str
    notes: str | None = None
    confirmed: bool = Field(
        description="Must be true. The caller must have already read the slot back to the "
        "user and gotten explicit confirmation before setting this."
    )


class BookAppointmentOutput(BaseModel):
    appointment_id: str
    date: date_type
    start_time: str
    provider_name: str
    appointment_type: str


@registry.register(
    "book_appointment",
    "Book a previously checked slot for a customer. Only call this after the user has "
    "explicitly confirmed the specific date/time — never book speculatively.",
    BookAppointmentInput,
)
async def book_appointment(
    session: AsyncSession, args: BookAppointmentInput
) -> BookAppointmentOutput:
    if not args.confirmed:
        raise ToolExecutionError(
            "Booking requires explicit user confirmation. Ask the user to confirm the "
            "specific date and time before calling this tool again with confirmed=true."
        )

    customer = await CustomerRepository(session).get_by_id(uuid.UUID(args.customer_id))
    if customer is None:
        raise ToolExecutionError(f"No customer found with id {args.customer_id}.")

    slot = await AvailabilityRepository(session).get_by_id(uuid.UUID(args.slot_id))
    if slot is None:
        raise ToolExecutionError(f"No such slot: {args.slot_id}.")

    appt_type = await AppointmentTypeRepository(session).get_by_name(args.appointment_type)
    if appt_type is None:
        raise ToolExecutionError(f"Unknown appointment type: '{args.appointment_type}'.")

    booked = await AvailabilityRepository(session).try_book(slot.id)
    if not booked:
        raise ToolExecutionError(
            "That slot was just booked by someone else. Please check availability again."
        )

    provider = await ProviderRepository(session).get_by_id(slot.provider_id)
    assert provider is not None  # FK guarantees this

    appointment = await AppointmentRepository(session).create(
        customer_id=customer.id,
        provider_id=slot.provider_id,
        appointment_type_id=appt_type.id,
        slot_id=slot.id,
        notes=args.notes,
    )
    return BookAppointmentOutput(
        appointment_id=str(appointment.id),
        date=slot.slot_date,
        start_time=slot.start_time.strftime("%H:%M"),
        provider_name=provider.name,
        appointment_type=appt_type.name,
    )


class CancelAppointmentInput(BaseModel):
    appointment_id: str
    confirmed: bool = Field(
        description="Must be true. Confirm with the user before cancelling."
    )


class CancelAppointmentOutput(BaseModel):
    appointment_id: str
    status: str


@registry.register(
    "cancel_appointment",
    "Cancel an existing appointment. Only call this after the user has explicitly "
    "confirmed they want to cancel.",
    CancelAppointmentInput,
)
async def cancel_appointment(
    session: AsyncSession, args: CancelAppointmentInput
) -> CancelAppointmentOutput:
    if not args.confirmed:
        raise ToolExecutionError(
            "Cancellation requires explicit user confirmation. Ask the user to confirm "
            "before calling this tool again with confirmed=true."
        )

    appointment = await AppointmentRepository(session).cancel(uuid.UUID(args.appointment_id))
    if appointment is None:
        raise ToolExecutionError(
            f"No schedulable appointment found with id {args.appointment_id} "
            "(it may not exist or is already cancelled)."
        )
    return CancelAppointmentOutput(
        appointment_id=str(appointment.id), status=appointment.status.value
    )
