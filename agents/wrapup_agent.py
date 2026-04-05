"""
agents/wrapup_agent.py (also contains rapport_agent and escalation_agent)

EMAIL RULE: Email is NOT sent here — it fires exclusively in the finally
block of twilio_server.py after the WebSocket closes. This file only
generates the farewell message and logs the interaction.

Wrapup responsibilities:
  - Generate farewell response
  - Build LLM call summary (always in English, for the log)
  - Log interaction to Google Sheets via n8n
"""

import os
from agents.llm_client import llm_chat
from langchain_core.messages import AIMessage
from graph.state import CallState
from tools.patient_tools import log_interaction_tool
from agents.lang_prompts import format_prompt, lang_system, get_prompt


def _safe_record(record):
    if isinstance(record, dict): return record
    if isinstance(record, str):
        try:
            import json
            return json.loads(record)
        except: return None
    return None


# ── RAPPORT AGENT ─────────────────────────────────────────────────────────────

async def rapport_agent_node(state: CallState) -> dict:
    lang = state.get("preferred_language", "en")
    sentiment = state.get("sentiment_current", "frustrated")
    prompt_key = "rapport_angry" if sentiment == "angry" else "rapport_frustrated"
    response = await _gen(format_prompt(prompt_key, lang), lang)
    return {
        "messages": [AIMessage(content=response)],
        "rapport_injected": True,
        "frustration_count": 0,
        "phase": "rapport_recovery",
        "language_switched": False,
        "routing_path": (state.get("routing_path") or []) + ["rapport_agent"],
        "agent_responses": (state.get("agent_responses") or [])[-2:] + [response],
    }


# ── ESCALATION AGENT ──────────────────────────────────────────────────────────

async def escalation_agent_node(state: CallState) -> dict:
    lang = state.get("preferred_language", "en")
    intent = state.get("current_intent", "unclear")
    updates: dict = {
        "routing_path": (state.get("routing_path") or []) + ["escalation_agent"],
        "escalation_requested": True,
        "phase": "wrapup",
        "language_switched": False,
    }
    if intent == "emergency" or state.get("emergency_detected"):
        response = get_prompt("emergency", lang)
        updates["emergency_detected"] = True
    else:
        response = await _gen(format_prompt("escalation_callback", lang), lang)
    return {
        **updates,
        "messages": [AIMessage(content=response)],
        "agent_responses": (state.get("agent_responses") or [])[-2:] + [response],
    }


# ── WRAPUP AGENT ──────────────────────────────────────────────────────────────

async def wrapup_agent_node(state: CallState) -> dict:
    lang = state.get("preferred_language", "en")
    patient = _safe_record(state.get("patient_record")) or {}
    first = patient.get("first_name", "")
    is_authenticated = state.get("is_authenticated", False)
    appt_communicated = state.get("appointment_communicated", False)
    appt = state.get("appointment_details") or {}
    appt_status = appt.get("status", patient.get("appointment_status", ""))
    clinic_phone = os.getenv("CLINIC_PHONE", "1-800-555-0200")

    # ── Generate farewell ─────────────────────────────────────────────────
    if state.get("emergency_detected"):
        farewell = get_prompt("emergency", lang)

    elif state.get("escalation_requested"):
        farewell = await _gen(format_prompt("farewell_escalation", lang), lang)

    elif not is_authenticated:
        # Hardcoded — no LLM, no hallucination risk
        if lang == "es":
            farewell = (
                "No se preocupe, estas cosas pasan. "
                "Uno de nuestros recepcionistas se pondrá en contacto con usted "
                "personalmente dentro del próximo día hábil. "
                "Muchas gracias por llamar a Riverside Medical Centre — que tenga un excelente día."
            )
        else:
            farewell = (
                "No worries at all — these things happen. "
                "One of our receptionists will reach out to you personally within the next business day. "
                "Thank you so much for calling Riverside Medical Centre — have a wonderful day!"
            )

    elif appt_communicated:
        # Tell patient they'll receive a summary email, then say goodbye
        if lang == "es":
            farewell_prompt = (
                f"La llamada está terminando. El paciente es {first}, cita: {appt_status}. "
                f"Menciona que recibirá un correo electrónico de resumen. "
                f"Luego da una despedida cálida y breve. "
                f"2 oraciones. Natural y cálido."
            )
        else:
            farewell_prompt = (
                f"Call is ending. Patient is {first}, appointment status: {appt_status}. "
                f"Tell them they'll receive a summary email shortly. "
                f"Then say a warm brief goodbye using their name. "
                f"2 sentences. Natural and warm."
            )
        farewell = await _gen(farewell_prompt, lang)

    else:
        farewell = await _gen(
            format_prompt("farewell_normal", lang,
                first_name=first if first else ("you" if lang == "en" else "usted")),
            lang,
        )

    # ── Build LLM summary (always English, for the log) ──────────────────
    topics = state.get("call_topics") or ["general inquiry"]
    auth_status = "authenticated" if is_authenticated else "could not be verified"
    new_slot = state.get("new_appointment_slot", "")
    reschedule_note = f" Rescheduled to: {new_slot}." if new_slot else ""
    summary_prompt = (
        f"Write a 2-sentence post-call summary in English. "
        f"Patient: {patient.get('first_name','Unknown')} {patient.get('last_name','')}. "
        f"Status: {auth_status}. "
        f"Appointment status: {appt_status or 'N/A'}.{reschedule_note} "
        f"Topics: {', '.join(topics)}. "
        f"Escalation: {state.get('escalation_requested',False)}. "
        f"Language: {'Spanish' if lang == 'es' else 'English'}. "
        f"Past tense, professional, factual. "
        f"Reply with ONLY the summary — no intro like 'Here is a summary'."
    )
    summary = await _gen(summary_prompt, "en")

    # ── Determine final sentiment ─────────────────────────────────────────
    history = state.get("sentiment_history") or []
    if not history:
        final_sentiment = "neutral"
    else:
        counts: dict[str, int] = {}
        for s in history:
            counts[s] = counts.get(s, 0) + 1
        raw = max(counts, key=counts.get)
        final_sentiment = (
            "negative" if raw in ("frustrated","angry") else
            ("positive" if raw == "positive" else "neutral")
        )

    # Logging happens exclusively in twilio_server.py finally block — not here.
    # This prevents double-logging when wrapup_agent and finally both fire.

    return {
        "messages": [AIMessage(content=farewell)],
        "phase": "ended",
        "routing_path": (state.get("routing_path") or []) + ["wrapup_agent"],
    }


async def _gen(prompt: str, lang: str) -> str:
    return await llm_chat(
        system=lang_system(lang),
        user=prompt,
        max_tokens=120,
        temperature=0.65,
    )
