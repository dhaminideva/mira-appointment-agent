"""
agents/supervisor.py

The Supervisor is deterministic — no LLM, just logic.
It reads state and returns a node name. This is the architectural heart
of the LangGraph pattern.

ROUTING PRIORITY (highest to lowest):
1. Emergency override → always routes to escalation_agent
2. Human request → escalation_agent
3. Goodbye / wrapup intent → wrapup_agent
4. Frustration override → rapport_agent if frustration_count >= 2
5. Language switch acknowledgment
6. Phase-based routing
7. Fallback

Why no LLM here? Speed and reliability. A deterministic supervisor adds <5ms
and cannot hallucinate routing decisions. Industry best practice for
production voice agents.
"""

from langgraph.graph import END
from graph.state import CallState


def supervisor_node(state: CallState) -> dict:
    """Update routing_path with supervisor decision. Routing happens in route_from_supervisor."""
    next_node = _decide_next_node(state)
    return {
        "routing_path": state["routing_path"] + [f"supervisor→{next_node}"],
    }


def route_from_supervisor(state: CallState) -> str:
    """
    The conditional edge function LangGraph calls to decide the next node.
    Returns a node name string.
    """
    return _decide_next_node(state)


def _decide_next_node(state: CallState) -> str:
    intent = state.get("current_intent", "unclear")
    phase = state.get("phase", "greeting")
    frust_count = state.get("frustration_count", 0)
    rapport_injected = state.get("rapport_injected", False)
    is_auth = state.get("is_authenticated", False)

    # ── PRIORITY 1: Emergency — always wins ───────────────────────────────
    if intent == "emergency" or state.get("emergency_detected"):
        return "escalation_agent"

    # ── PRIORITY 2: Human escalation request ──────────────────────────────
    if intent == "request_human":
        return "escalation_agent"

    # ── PRIORITY 3: Goodbye / wrapup ─────────────────────────────────────
    if intent == "goodbye" or phase in ("wrapup", "ended"):
        return "wrapup_agent"

    # ── PRIORITY 4: Frustration override (engagement mechanic) ────────────
    # Only fires if: 2+ consecutive frustrated turns AND rapport not already given
    if frust_count >= 2 and not rapport_injected:
        return "rapport_agent"

    # ── PRIORITY 5: Language switch — acknowledge in auth_agent ───────────
    if state.get("language_switched"):
        if phase in ("greeting", "auth_phone", "auth_confirm") or not is_auth:
            return "auth_agent"

    # ── PRIORITY 6: Phase-based routing ──────────────────────────────────
    if phase in ("greeting", "auth_phone", "auth_confirm", "new_patient"):
        return "auth_agent"

    if phase == "rapport_recovery":
        # After rapport, resume where we left off
        if is_auth:
            return "appointment_agent"
        return "auth_agent"

    if phase == "main" and is_auth:
        # Appointment-specific intents
        if intent in (
            "confirm_appointment",
            "cancel_appointment",
            "reschedule_appointment",
            "confirm_identity",
            "ask_faq",
            "off_topic",
            "unclear",
        ):
            return "appointment_agent"
        return "appointment_agent"

    # ── PRIORITY 7: Fallback ──────────────────────────────────────────────
    if not is_auth:
        return "auth_agent"

    return "appointment_agent"
