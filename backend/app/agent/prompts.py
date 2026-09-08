"""System prompt and message-building for the LLM. Kept separate from the
orchestration loop (agent.py) and the LLM transport (llm_provider.py)."""

from app.agent.state import ConversationState
from app.db.models import Message, MessageSpeaker

SYSTEM_PROMPT = """You are the voice support agent for Willow Creek Dental, \
a dental clinic. You help patients over a live voice call: answer questions \
using the search_knowledge_base tool, look up or create their patient record, \
check appointment availability, and book or cancel appointments.

Rules you must follow:
- Never claim to have booked, cancelled, or changed anything unless a tool \
call actually succeeded. Only report what the tool result says.
- Before calling book_appointment or cancel_appointment, you must first \
read the specific date/time back to the user in plain language and get an \
explicit yes. Only then call the tool with confirmed=true. If a tool \
rejects a call for lack of confirmation, ask the user directly and wait for \
their answer before retrying.
- If the user asks something you don't know, use search_knowledge_base \
before answering — don't guess clinic policy, hours, or pricing.
- If a request is outside what you can help with, or the user asks for a \
human, call transfer_to_human.
- Keep responses short and conversational — this is a spoken phone call, \
not a chat window. No markdown, no bullet lists in your replies.
"""

# Only the last N messages are sent verbatim; older context is summarized
# into the structured ConversationState fields (customer_id, intent, etc.)
# instead of being replayed to the model every turn.
_HISTORY_WINDOW = 10


def _state_summary(state: ConversationState) -> str:
    known: list[str] = []
    if state.customer_id:
        known.append(f"customer_id={state.customer_id}")
    if state.intent:
        known.append(f"intent={state.intent}")
    if state.appointment_date:
        known.append(f"last_appointment_date={state.appointment_date}")
    if state.last_appointment_id:
        known.append(f"last_appointment_id={state.last_appointment_id}")
    if state.awaiting_confirmation:
        known.append("a booking/cancellation is pending user confirmation")
    if not known:
        return "Nothing confirmed yet this call."
    return "Known so far: " + "; ".join(known) + "."


def build_messages(
    state: ConversationState, recent_messages: list[Message]
) -> list[dict[str, str]]:
    # MessageSpeaker.SYSTEM is only ever used for tool results (see
    # agent.py) — mapped to Ollama's "tool" role, not "system", so the
    # chat template doesn't confuse the model about whose turn it is.
    # Sending tool output as a literal "system" message caused Ollama to
    # echo a stray "assistant\n\n" role label into its own response.
    role_map = {
        MessageSpeaker.USER: "user",
        MessageSpeaker.AGENT: "assistant",
        MessageSpeaker.SYSTEM: "tool",
    }
    windowed = recent_messages[-_HISTORY_WINDOW:]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _state_summary(state)},
    ]
    messages.extend({"role": role_map[m.speaker], "content": m.text} for m in windowed)
    return messages
