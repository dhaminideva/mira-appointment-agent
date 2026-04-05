"""
graph/state.py
The single source of truth that flows through every node in the LangGraph.
All agents read from and write to this TypedDict — no hidden state anywhere.
"""

from typing import TypedDict, Literal, Optional, Annotated
from langgraph.graph.message import add_messages


SentimentType = Literal["positive", "neutral", "frustrated", "angry"]
LanguageType = Literal["en", "es"]
PhaseType = Literal[
    "greeting",
    "auth_phone",
    "auth_confirm",
    "new_patient",       # ← no record found after 2 attempts
    "main",
    "rapport_recovery",  # ← triggered by sentiment watcher
    "wrapup",
    "ended",
]
IntentType = Literal[
    "provide_phone",
    "confirm_identity",
    "deny_identity",
    "confirm_appointment",
    "cancel_appointment",
    "reschedule_appointment",
    "ask_faq",
    "request_human",
    "emergency",
    "express_frustration",
    "off_topic",
    "goodbye",
    "unclear",
]


class CallState(TypedDict):
    # ── Conversation ──────────────────────────────────────────────────────
    messages: Annotated[list, add_messages]   # Full LangChain message history
    phase: PhaseType
    current_intent: IntentType
    turn_count: int

    # ── Language ──────────────────────────────────────────────────────────
    preferred_language: LanguageType      # "en" or "es" — auto-detected each turn
    language_switched: bool               # True when mid-call switch detected

    # ── Authentication ────────────────────────────────────────────────────
    phone_provided: Optional[str]
    auth_attempts: int
    confirm_attempts: int
    patient_record: Optional[dict]        # Full patient + appointment record from Google Sheets
    is_authenticated: bool

    # ── Sentiment tracking (rolling window) ──────────────────────────────
    sentiment_current: SentimentType
    sentiment_history: list[SentimentType]    # Last 5 turns
    frustration_count: int                    # Consecutive frustrated turns
    rapport_injected: bool                    # Prevent repeat rapport interrupts

    # ── Appointment context ───────────────────────────────────────────────
    appointment_details: Optional[dict]       # {date, time, doctor, department, status}
    appointment_communicated: bool            # True once appointment info delivered to patient
    reschedule_requested: bool                # True when patient wants to reschedule
    new_appointment_slot: Optional[str]       # The slot the patient selected
    cancellation_confirmed: bool              # True once cancellation processed
    change_requested: bool                    # True once we asked cancel-or-reschedule

    # ── Call flags ────────────────────────────────────────────────────────
    escalation_requested: bool
    emergency_detected: bool

    # ── Call metadata (for post-call log) ────────────────────────────────
    call_start_iso: str
    call_topics: list[str]                    # e.g. ["appointment_confirm", "faq_parking"]
    agent_responses: list[str]                # Last 3 MIRA responses for summary
    routing_path: list[str]                   # Which nodes fired, in order — audit trail


def initial_state() -> CallState:
    from datetime import datetime, timezone
    return CallState(
        messages=[],
        phase="greeting",
        current_intent="unclear",
        turn_count=0,
        preferred_language="en",
        language_switched=False,
        phone_provided=None,
        auth_attempts=0,
        confirm_attempts=0,
        patient_record=None,
        is_authenticated=False,
        sentiment_current="neutral",
        sentiment_history=[],
        frustration_count=0,
        rapport_injected=False,
        appointment_details=None,
        appointment_communicated=False,
        reschedule_requested=False,
        new_appointment_slot=None,
        cancellation_confirmed=False,
        change_requested=False,
        escalation_requested=False,
        emergency_detected=False,
        call_start_iso=datetime.now(timezone.utc).isoformat(),
        call_topics=[],
        agent_responses=[],
        routing_path=[],
    )
