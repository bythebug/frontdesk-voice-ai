"""Structured conversation state — not a prompt blob. Durable facts here
come from actual tool results, not from asking the LLM to remember things."""

import uuid
from datetime import date as date_type

from pydantic import BaseModel


class ConversationState(BaseModel):
    conversation_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    intent: str | None = None
    appointment_date: date_type | None = None
    appointment_time: str | None = None
    appointment_type: str | None = None
    last_appointment_id: uuid.UUID | None = None
    awaiting_confirmation: bool = False
    current_step: str = "greeting"
    escalated: bool = False

    def apply_tool_result(
        self, tool_name: str, arguments: dict, success: bool, data: dict | None
    ) -> None:
        """Update structured state from a completed tool call. Called by the
        agent loop after every tool execution — never guessed by the LLM."""
        if not success:
            if tool_name in ("book_appointment", "cancel_appointment"):
                self.awaiting_confirmation = True
            return

        self.awaiting_confirmation = False
        if self.current_step == "greeting":
            self.current_step = "in_progress"

        if tool_name in ("lookup_customer", "create_customer") and data:
            customer_id = data.get("customer_id")
            if customer_id:
                self.customer_id = uuid.UUID(customer_id)
        elif tool_name == "check_availability":
            self.intent = "appointment_booking"
        elif tool_name == "book_appointment" and data:
            self.last_appointment_id = uuid.UUID(data["appointment_id"])
            self.appointment_date = date_type.fromisoformat(data["date"])
            self.appointment_time = data.get("start_time")
            self.appointment_type = data.get("appointment_type")
            self.current_step = "completed"
        elif tool_name == "cancel_appointment":
            self.current_step = "completed"
        elif tool_name == "transfer_to_human":
            self.escalated = True
            self.current_step = "escalated"
