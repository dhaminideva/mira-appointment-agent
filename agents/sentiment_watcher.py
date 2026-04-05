"""
agents/sentiment_watcher.py — NoneType safe, bilingual keywords
"""

import re
from graph.state import CallState, SentimentType

FRUSTRATION_KEYWORDS = {
    "frustrated","angry","ridiculous","unbelievable","terrible",
    "this is taking forever","been waiting","keep asking","stupid",
    "useless","hate this","getting nowhere","going in circles",
    "just give me","transfer me","forget it","never mind",
    "waste of time","worst","incompetent",
    "frustrado","frustrada","enojado","enojada","molesto","molesta",
    "ridículo","horrible","está tardando","llevo esperando",
    "inútil","odio esto","pérdida de tiempo","qué fastidio",
}

POSITIVE_KEYWORDS = {
    "thank you","thanks","great","perfect","helpful",
    "appreciate","wonderful","excellent","that's great",
    "gracias","perfecto","excelente","muy bien","genial",
    "agradezco","maravilloso","qué bueno",
}


def _detect_sentiment(utterance: str, current_intent: str) -> SentimentType:
    low = utterance.lower()
    if current_intent == "emergency":
        return "frustrated"
    if current_intent == "express_frustration":
        return "frustrated"
    frust = sum(1 for kw in FRUSTRATION_KEYWORDS if kw in low)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in low)
    if frust >= 2 or (frust >= 1 and any(w in low for w in ("!", "this is", "why"))):
        return "angry" if frust >= 3 else "frustrated"
    if pos >= 1:
        return "positive"
    return "neutral"


async def sentiment_watcher_node(state: CallState) -> dict:
    from langchain_core.messages import HumanMessage
    last_human = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if not last_human:
        return {
            "sentiment_current": state.get("sentiment_current", "neutral"),
            "routing_path": list(state.get("routing_path") or []) + ["sentiment:skip"],
        }

    current_intent = state.get("current_intent", "unclear")
    new_sentiment = _detect_sentiment(last_human, current_intent)
    history = list((state.get("sentiment_history") or []))[-4:] + [new_sentiment]
    frust_count = state.get("frustration_count", 0) or 0

    if new_sentiment in ("frustrated", "angry"):
        frust_count += 1
    else:
        frust_count = max(0, frust_count - 1)

    rapport_injected = state.get("rapport_injected", False)
    if new_sentiment == "positive":
        rapport_injected = False

    return {
        "sentiment_current": new_sentiment,
        "sentiment_history": history,
        "frustration_count": frust_count,
        "rapport_injected": rapport_injected,
        "routing_path": list(state.get("routing_path") or []) + [f"sentiment:{new_sentiment}"],
    }
