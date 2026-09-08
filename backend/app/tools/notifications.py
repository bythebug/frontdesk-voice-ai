"""Simulated notification/escalation tools.

No paid SMS/email provider is used (see CLAUDE.md — $0 recurring cost).
send_confirmation logs a structured "confirmation sent" event instead of
actually sending anything; this is a deliberate simulation, not a fake
success — the tool result and logs both say so explicitly.
"""

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_registry import ToolExecutionError, registry
from app.core.logging import get_logger
from app.db.models import ConversationStatus
from app.db.repositories import AppointmentRepository, ConversationRepository, CustomerRepository

logger = get_logger(__name__)


class SendConfirmationInput(BaseModel):
    appointment_id: str


class SendConfirmationOutput(BaseModel):
    simulated: bool
    message: str


@registry.register(
    "send_confirmation",
    "Send a booking confirmation to the customer for a given appointment.",
    SendConfirmationInput,
)
async def send_confirmation(
    session: AsyncSession, args: SendConfirmationInput
) -> SendConfirmationOutput:
    appointment = await AppointmentRepository(session).get_by_id(uuid.UUID(args.appointment_id))
    if appointment is None:
        raise ToolExecutionError(f"No appointment found with id {args.appointment_id}.")
    customer = await CustomerRepository(session).get_by_id(appointment.customer_id)
    assert customer is not None  # FK guarantees this

    message = (
        f"Confirmation for {customer.first_name} {customer.last_name}: appointment on "
        f"{appointment.created_at.date()} — this is simulated, no real email/SMS was sent "
        "(no paid provider configured)."
    )
    logger.info(
        "confirmation_sent_simulated",
        extra={"appointment_id": str(appointment.id), "customer_id": str(customer.id)},
    )
    return SendConfirmationOutput(simulated=True, message=message)


class TransferToHumanInput(BaseModel):
    conversation_id: str
    reason: str | None = None


class TransferToHumanOutput(BaseModel):
    escalated: bool
    conversation_id: str


@registry.register(
    "transfer_to_human",
    "Escalate the conversation to a human support representative. Use this when the "
    "request is outside what the agent can safely handle, or the user asks for a human.",
    TransferToHumanInput,
)
async def transfer_to_human(
    session: AsyncSession, args: TransferToHumanInput
) -> TransferToHumanOutput:
    conversation_id = uuid.UUID(args.conversation_id)
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.get_by_id(conversation_id)
    if conversation is None:
        raise ToolExecutionError(f"No conversation found with id {args.conversation_id}.")

    await conv_repo.set_status(conversation_id, ConversationStatus.ESCALATED)
    logger.info(
        "human_escalation_requested",
        extra={"conversation_id": args.conversation_id, "reason": args.reason},
    )
    return TransferToHumanOutput(escalated=True, conversation_id=args.conversation_id)
