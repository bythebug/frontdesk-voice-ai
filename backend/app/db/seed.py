"""Seed data for the fictional Willow Creek Dental clinic.

Run with: uv run python -m app.db.seed
Idempotent: does nothing if providers already exist.
"""

import asyncio
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.db.database import get_sessionmaker
from app.db.models import AppointmentType, AvailabilitySlot, KnowledgeBaseArticle, Provider

PROVIDERS = [
    {"name": "Dr. Sarah Chen", "title": "DDS"},
    {"name": "Dr. Michael Rodriguez", "title": "DDS"},
]

APPOINTMENT_TYPES = [
    {
        "name": "cleaning",
        "duration_minutes": 30,
        "price_cents": 12000,
        "description": "Routine dental cleaning and polish.",
    },
    {
        "name": "checkup",
        "duration_minutes": 30,
        "price_cents": 9000,
        "description": "General checkup and exam.",
    },
    {
        "name": "filling",
        "duration_minutes": 45,
        "price_cents": 18000,
        "description": "Cavity filling.",
    },
    {
        "name": "emergency",
        "duration_minutes": 30,
        "price_cents": 15000,
        "description": "Urgent care for pain, injury, or infection.",
    },
    {
        "name": "consultation",
        "duration_minutes": 20,
        "price_cents": 0,
        "description": "Free new-patient consultation.",
    },
]

KNOWLEDGE_BASE = [
    {
        "category": "hours",
        "title": "Opening Hours",
        "content": (
            "Willow Creek Dental is open Monday through Friday, 9:00 AM to 5:00 PM. "
            "We are closed on weekends and major holidays."
        ),
    },
    {
        "category": "services",
        "title": "Services Offered",
        "content": (
            "We offer routine cleanings, checkups, fillings, emergency care, and free "
            "new-patient consultations. Our providers are Dr. Sarah Chen and "
            "Dr. Michael Rodriguez, both DDS."
        ),
    },
    {
        "category": "policy",
        "title": "Cancellation Policy",
        "content": (
            "Appointments can be cancelled or rescheduled free of charge up to 24 hours "
            "before the scheduled time. Cancellations within 24 hours may incur a $25 fee."
        ),
    },
    {
        "category": "insurance",
        "title": "Insurance Information",
        "content": (
            "We accept most major dental insurance plans including Delta Dental, Cigna, "
            "and MetLife. Please bring your insurance card to your first appointment. "
            "We also offer a self-pay discount for uninsured patients."
        ),
    },
    {
        "category": "parking",
        "title": "Parking Information",
        "content": (
            "Free parking is available in the lot directly behind our building, accessible "
            "from Maple Avenue. Street parking is also available on Willow Creek Blvd."
        ),
    },
    {
        "category": "emergency",
        "title": "Dental Emergency Instructions",
        "content": (
            "If you are experiencing severe pain, swelling, or a knocked-out tooth, call us "
            "immediately for a same-day emergency appointment. For a knocked-out tooth, keep it "
            "moist (in milk or your cheek) and come in right away — timing matters."
        ),
    },
    {
        "category": "pricing",
        "title": "Pricing Examples",
        "content": (
            "Routine cleaning: $120. General checkup: $90. Cavity filling: starting at $180. "
            "Emergency visit: $150. New-patient consultations are free. Prices may vary based "
            "on treatment complexity and insurance coverage."
        ),
    },
    {
        "category": "appointment_types",
        "title": "Appointment Types",
        "content": (
            "We offer five appointment types: cleaning (30 min), checkup (30 min), filling "
            "(45 min), emergency (30 min, same-day when possible), and consultation (20 min, free)."
        ),
    },
]


def _business_hour_slots(day: date) -> list[tuple[time, time]]:
    slots = []
    start = datetime.combine(day, time(9, 0))
    end = datetime.combine(day, time(17, 0))
    current = start
    while current < end:
        nxt = current + timedelta(minutes=30)
        slots.append((current.time(), nxt.time()))
        current = nxt
    return slots


async def seed() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(select(Provider))
        if result.scalars().first() is not None:
            print("Already seeded — skipping.")
            return

        providers = [Provider(**p) for p in PROVIDERS]
        session.add_all(providers)

        session.add_all(AppointmentType(**t) for t in APPOINTMENT_TYPES)
        session.add_all(KnowledgeBaseArticle(**a) for a in KNOWLEDGE_BASE)
        await session.flush()

        today = date.today()
        for offset in range(14):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5:  # Sat/Sun
                continue
            for provider in providers:
                for start, end in _business_hour_slots(day):
                    session.add(
                        AvailabilitySlot(
                            provider_id=provider.id, slot_date=day, start_time=start, end_time=end
                        )
                    )

        await session.commit()
        print(f"Seeded {len(providers)} providers, {len(APPOINTMENT_TYPES)} appointment types, "
              f"{len(KNOWLEDGE_BASE)} KB articles, and 14 days of availability slots.")


if __name__ == "__main__":
    asyncio.run(seed())
