"""
graph/graph.py
Builds and compiles the LangGraph StateGraph for MIRA.

Key design decisions:

1. SUPERVISOR PATTERN: The Supervisor node is not an LLM — it's a deterministic router.
   It reads intent + sentiment from state and emits the next node name.
   Sub-5ms routing with zero hallucination risk on control flow.

2. CONDITIONAL EDGES: LangGraph's conditional_edges() lets each node signal
   where it wants to go next. The Supervisor is the central hub.

3. SENTIMENT OVERRIDE: SentimentWatcher runs before the Supervisor.
   If frustration_count >= 2, Supervisor is forced to route to RapportAgent.

4. SHARED STATE: Every node receives the full CallState TypedDict and returns
   a partial update. LangGraph merges these automatically.
"""

from langgraph.graph import StateGraph, END
from graph.state import CallState
from agents.language_detector import language_detector_node
from agents.intent_classifier import intent_classifier_node
from agents.sentiment_watcher import sentiment_watcher_node
from agents.supervisor import supervisor_node, route_from_supervisor
from agents.auth_agent import auth_agent_node
from agents.appointment_agent import appointment_agent_node
from agents.wrapup_agent import wrapup_agent_node, rapport_agent_node, escalation_agent_node


def build_graph() -> StateGraph:
    """
    Assembles the full agent graph.

    Node execution order on each turn:
      patient_utterance
        → language_detector    (detects en/es, supports mid-call switching)
        → intent_classifier    (classifies what the patient wants)
        → sentiment_watcher    (updates frustration score, bilingual keywords)
        → supervisor           (decides which specialist fires next)
        → [auth | appointment | rapport | escalation | wrapup]
        → END                  (one response per utterance — no loops)
    """
    g = StateGraph(CallState)

    # ── Register all nodes ────────────────────────────────────────────────
    g.add_node("language_detector",    language_detector_node)
    g.add_node("intent_classifier",    intent_classifier_node)
    g.add_node("sentiment_watcher",    sentiment_watcher_node)
    g.add_node("supervisor",           supervisor_node)
    g.add_node("auth_agent",           auth_agent_node)
    g.add_node("appointment_agent",    appointment_agent_node)
    g.add_node("rapport_agent",        rapport_agent_node)
    g.add_node("escalation_agent",     escalation_agent_node)
    g.add_node("wrapup_agent",         wrapup_agent_node)

    # ── Entry point ────────────────────────────────────────────────────────
    g.set_entry_point("language_detector")

    # ── Fixed edges (always fire in this order) ───────────────────────────
    g.add_edge("language_detector",  "intent_classifier")
    g.add_edge("intent_classifier",  "sentiment_watcher")
    g.add_edge("sentiment_watcher",  "supervisor")

    # ── Supervisor routes conditionally to specialist agents ──────────────
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "auth_agent":          "auth_agent",
            "appointment_agent":   "appointment_agent",
            "rapport_agent":       "rapport_agent",
            "escalation_agent":    "escalation_agent",
            "wrapup_agent":        "wrapup_agent",
            END:                   END,
        },
    )

    # ── All specialist agents go to END — one response per utterance ──────
    # Never loop back to supervisor — pipeline calls graph once per utterance
    for agent in ["auth_agent", "appointment_agent", "rapport_agent", "escalation_agent"]:
        g.add_edge(agent, END)

    # ── Wrapup is terminal ─────────────────────────────────────────────────
    g.add_edge("wrapup_agent", END)

    return g.compile()


# Singleton compiled graph — import this everywhere
mira_graph = build_graph()
