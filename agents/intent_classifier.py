"""
agents/intent_classifier.py — MIRA Medical Appointment Voice Assistant
Updated intent labels for appointment management context.
Core digit detection and phase-aware fast paths are preserved.
"""

import json, os, re
from langchain_core.messages import HumanMessage
from graph.state import CallState, IntentType
from agents.llm_client import llm_chat

SPOKEN_DIGITS = {
    "zero":"0","one":"1","two":"2","three":"3","four":"4",
    "five":"5","six":"6","seven":"7","eight":"8","nine":"9",
    "oh":"0","nought":"0",
    "cero":"0","uno":"1","dos":"2","tres":"3","cuatro":"4",
    "cinco":"5","seis":"6","siete":"7","ocho":"8","nueve":"9",
}

def spoken_to_digits(text: str) -> str:
    words = text.lower().split()
    result = []
    for word in words:
        clean = word.strip(".,!?()")
        if clean in SPOKEN_DIGITS:
            result.append(SPOKEN_DIGITS[clean])
        elif clean.isdigit():
            result.append(clean)
        else:
            result.append(None)
    digit_parts = [r for r in result if r is not None]
    if len(digit_parts) >= 7:
        return "".join(digit_parts)
    return ""


INTENT_SYSTEM = """You are an intent classifier for a medical appointment voice assistant at a clinic.
Classify the patient's utterance into EXACTLY ONE of these labels:

provide_phone            - patient is giving or trying to give a phone number (digits, or says "my number is")
confirm_identity         - patient confirms they are who we asked (yes/yeah/correct/that's me/sí/correcto)
deny_identity            - patient denies identity (no/wrong/not me/no soy)
confirm_appointment      - patient wants to confirm or check their appointment is still on
cancel_appointment       - patient wants to cancel their appointment
reschedule_appointment   - patient wants to change, move, or rebook their appointment to a different time
ask_faq                  - asks about clinic hours, location, parking, what to bring, preparation, insurance
request_human            - wants a person / receptionist / human agent / supervisor
emergency                - mentions 911, life threat, chest pain, stroke, acute medical emergency
express_frustration      - sounds frustrated, angry, impatient, upset
off_topic                - completely unrelated to medical appointments
goodbye                  - ONLY if clearly ending the call: bye, goodbye, that's all, gracias adiós
unclear                  - short filler, "okay", "ready", "I'm ready", "sure", "mhmm", "uh huh", waiting

IMPORTANT:
- "I'm ready", "okay", "sure", "go ahead", "mhmm" = unclear (NOT confirm_identity, NOT goodbye)
- Only use goodbye if they explicitly say bye/goodbye/that's all/gracias/adiós
- Only use confirm_identity if directly answering "am I speaking with [name]?" question
- "confirm my appointment" = confirm_appointment (not confirm_identity)
- "reschedule", "change", "different time", "move" = reschedule_appointment

Works in both English and Spanish.
Reply ONLY with JSON: {"intent": "<label>", "confidence": <0.0-1.0>}"""


async def intent_classifier_node(state: CallState) -> dict:
    messages = state.get("messages") or []
    last_human = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if not last_human or last_human == "[CALL_CONNECTED]":
        return {
            "current_intent": "unclear",
            "routing_path": list(state.get("routing_path") or []) + ["intent:skip"],
        }

    low = last_human.lower().strip()
    phase = state.get("phase", "greeting")

    # ── Fast digit detection ──────────────────────────────────────────────
    digits = re.sub(r"\D", "", last_human)

    # Check spoken digits if not enough numeric digits
    if len(digits) < 7 and phase in ("auth_phone", "greeting"):
        spoken = spoken_to_digits(last_human)
        if spoken:
            digits = spoken

    if len(digits) >= 7 and phase in ("auth_phone", "greeting"):
        phone = digits[-10:] if len(digits) >= 10 else digits
        return {
            "current_intent": "provide_phone",
            "phone_provided": phone,
            "routing_path": list(state.get("routing_path") or []) + ["intent:provide_phone"],
        }

    # ── Phase-aware fast paths ────────────────────────────────────────────

    # auth_confirm phase — only check yes/no, everything else is unclear
    if phase == "auth_confirm":
        yes_words = {
            "yes","yeah","yep","correct","right","that's me","it's me",
            "speaking","sí","si","correcto","así es","exacto","claro","eso es",
        }
        no_words = {"no","nope","not me","wrong","incorrect","no soy","ese no"}
        words = set(low.replace(".", " ").replace(",", " ").split())
        if words & yes_words:
            return {
                "current_intent": "confirm_identity",
                "routing_path": list(state.get("routing_path") or []) + ["intent:confirm_identity"],
            }
        if words & no_words:
            return {
                "current_intent": "deny_identity",
                "routing_path": list(state.get("routing_path") or []) + ["intent:deny_identity"],
            }
        # Short responses in auth_confirm = treat as confirm
        if len(last_human.strip()) <= 8:
            return {
                "current_intent": "confirm_identity",
                "routing_path": list(state.get("routing_path") or []) + ["intent:confirm_short"],
            }

    # auth_phone phase — filler words should not trigger action
    if phase == "auth_phone":
        filler = {
            "okay","ok","sure","ready","i'm ready","alright","go ahead",
            "yep","yeah","yes","mhmm","uh huh","got it","fine",
        }
        words = set(low.replace("'","").split())
        if words <= filler or low in filler or f"i'm {low}" in filler:
            return {
                "current_intent": "unclear",
                "routing_path": list(state.get("routing_path") or []) + ["intent:filler"],
            }

    # Skip LLM for very short filler
    if len(last_human.strip()) <= 3:
        return {
            "current_intent": "unclear",
            "routing_path": list(state.get("routing_path") or []) + ["intent:too_short"],
        }

    # ── LLM classification ────────────────────────────────────────────────
    try:
        raw = await llm_chat(
            system=INTENT_SYSTEM,
            user=f'Phase: {phase}\nUtterance: "{last_human}"',
            max_tokens=60,
            temperature=0.0,
        )
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        intent: IntentType = parsed.get("intent", "unclear")
    except Exception as e:
        print(f"[intent_classifier] error: {e}")
        intent = "unclear"

    # Safety: never classify as goodbye in auth phases
    if intent == "goodbye" and phase in ("auth_phone", "auth_confirm", "greeting"):
        intent = "unclear"

    updates: dict = {
        "current_intent": intent,
        "routing_path": list(state.get("routing_path") or []) + [f"intent:{intent}"],
    }

    if digits and len(digits) >= 7 and not state.get("phone_provided"):
        updates["phone_provided"] = digits[-10:] if len(digits) >= 10 else digits

    return updates
