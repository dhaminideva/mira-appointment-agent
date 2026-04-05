"""
agents/language_detector.py — fixed: single-word Spanish greetings now trigger switch
"""

import re
from graph.state import CallState

SPANISH_SIGNALS = {
    "hola","buenos","buenas","días","tardes","noches",
    "quiero","necesito","tengo","tiene","estoy","están",
    "puedo","puede","ayuda","ayudar","gracias","favor",
    "reclamación","reclamo","seguro","póliza","cobertura",
    "documentos","estado","aprobado","pendiente","denegado",
    "qué","cómo","cuándo","dónde","cuál","cuánto",
    "por","para","con","sobre","muy","más",
    "también","pero","porque","cuando","sí","nada",
    "hablar","español","necesito","puede",
    "usted","señor","señora","claro","sería",
    # Removed: "sin","quiero","tiene" — too common in English context
}

# Phrases that explicitly request English — checked BEFORE Spanish signals
ENGLISH_OVERRIDE_PHRASES = [
    "english", "speak english", "in english", "english please",
    "please english", "i don't speak spanish", "i dont speak spanish",
    "no spanish", "no hablo", "only english", "just english",
    "switch to english", "back to english", "inglés", "ingles",
    "don't understand spanish", "dont understand spanish",
]

# Single Spanish words that alone should trigger a switch
SPANISH_SINGLE_TRIGGERS = {
    "hola", "gracias", "sí", "si", "español", "ayuda",
    "bueno", "buena", "buenos", "buenas", "claro",
}

ENGLISH_SIGNALS = {
    "hello","hi","hey","please","thank","thanks","okay","yes","no",
    "what","when","where","how","why","can","could","would","should",
    "my","your","their","have","need","want","help","claim","status",
    "insurance","policy","number","account","speak","english",
    "representative","agent","person","human",
}

SPANISH_CHAR_PATTERN = re.compile(r"[áéíóúüñ¿¡]", re.IGNORECASE)


def _is_digit_heavy(text: str) -> bool:
    clean = re.sub(r"[^\w]", "", text)
    if not clean:
        return True
    digits = sum(1 for c in clean if c.isdigit())
    return digits / len(clean) > 0.5


def detect_language_change(text: str, current_lang: str) -> tuple[str, bool]:
    if not text or text == "[CALL_CONNECTED]":
        return current_lang, False

    # Never switch on digit-heavy utterances (phone numbers)
    if _is_digit_heavy(text):
        return current_lang, False

    low = text.lower().strip()
    words = set(re.sub(r"[^\w\s]", "", low).split())

    # Explicit language request — highest priority, checked before everything else
    # English override — any of these phrases immediately switch to English
    if any(phrase in low for phrase in ENGLISH_OVERRIDE_PHRASES):
        return "en", current_lang != "en"

    # Spanish request
    if "spanish" in low or "español" in low or "espanol" in low:
        return "es", current_lang != "es"

    # Spanish character detection
    if SPANISH_CHAR_PATTERN.search(low):
        return "es", current_lang != "es"

    # Single-word Spanish triggers (hola, gracias, etc.)
    if len(words) == 1 and low in SPANISH_SINGLE_TRIGGERS:
        return "es", current_lang != "es"

    # Multi-word Spanish detection
    spanish_hits = words & SPANISH_SIGNALS
    if len(spanish_hits) >= 1 and len(words) <= 5:
        return "es", current_lang != "es"
    if len(spanish_hits) >= 2:
        return "es", current_lang != "es"

    # Switching back to English — need strong evidence
    if current_lang == "es":
        english_hits = words & ENGLISH_SIGNALS
        if len(english_hits) >= 3 and not (words & SPANISH_SIGNALS):
            return "en", True
        if len(words) >= 5 and not (words & SPANISH_SIGNALS) and len(english_hits) >= 2:
            return "en", True
        return "es", False

    return "en", False


async def language_detector_node(state: CallState) -> dict:
    from langchain_core.messages import HumanMessage

    current_lang = state.get("preferred_language", "en")
    current_path = list(state.get("routing_path") or [])

    base = {
        "preferred_language": current_lang,
        "language_switched": False,
        "routing_path": current_path + ["lang:check"],
    }

    last_human = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if not last_human or last_human == "[CALL_CONNECTED]":
        return base

    new_lang, switched = detect_language_change(last_human, current_lang)

    if switched:
        print(f"[language_detector] Switched: {current_lang} → {new_lang} ('{last_human[:40]}')")
        return {
            "preferred_language": new_lang,
            "language_switched": True,
            "routing_path": current_path + [f"lang_switch:{current_lang}→{new_lang}"],
        }

    return {
        "preferred_language": new_lang,
        "language_switched": False,
        "routing_path": current_path + [f"lang:{new_lang}"],
    }
