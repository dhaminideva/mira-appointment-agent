"""
agents/appointment_agent.py — MIRA streamlined flow
After auth delivers appointment + "would you like to confirm it?":
  YES → confirm it, anything else?
  NO  → "would you like to cancel or reschedule?"
    CANCEL     → confirm cancellation, offer rebook
    RESCHEDULE → ask preference, offer 3 slots, confirm choice
Everything else (FAQ, human, emergency) handled naturally.
No random LLM detours.
"""
import os, re, json
from agents.llm_client import llm_chat
from langchain_core.messages import AIMessage, HumanMessage
from graph.state import CallState
from tools.patient_tools import search_faq_tool
from agents.lang_prompts import format_prompt, lang_system

CLINIC_PHONE  = os.getenv("CLINIC_PHONE",  "1-800-555-0200")
CLINIC_PORTAL = os.getenv("CLINIC_PORTAL", "portal.riversidemedical.com")

AVAILABLE_SLOTS    = ["Tuesday April 15th at 9:00 AM", "Wednesday April 16th at 2:30 PM", "Friday April 18th at 11:00 AM"]
AVAILABLE_SLOTS_ES = ["martes 15 de abril a las 9:00 AM", "miércoles 16 de abril a las 2:30 PM", "viernes 18 de abril a las 11:00 AM"]

def _safe_record(r):
    if isinstance(r, dict): return r
    if isinstance(r, str):
        try: return json.loads(r)
        except: return None
    return None

YES = {"yes","yeah","yep","sure","okay","ok","correct","confirm","confirmed","keep","sounds good",
       "that works","perfect","great","absolutely","sí","si","claro","por favor","de acuerdo"}
NO  = {"no","nope","not really","nah","don't","do not","no thanks","cancel","change","reschedule",
       "different","another","no gracias","no quiero","cancelar","reprogramar","cambiar"}
CANCEL_WORDS     = {"cancel","cancellation","cannot","can't","won't","cancelar","cancelación"}
RESCHEDULE_WORDS = {"reschedule","rebook","change","move","different","another","reprogramar","cambiar","mover"}
DONE_WORDS       = {"thank you","thanks","bye","goodbye","that's all","perfect","got it","gracias","adiós","hasta luego"}


async def appointment_agent_node(state: CallState) -> dict:
    lang    = state.get("preferred_language", "en")
    intent  = state.get("current_intent", "unclear")
    patient = _safe_record(state.get("patient_record")) or {}
    first   = patient.get("first_name", "there" if lang == "en" else "usted")
    appt    = state.get("appointment_details") or {}
    doc     = appt.get("doctor", patient.get("doctor_name", "your doctor"))
    date    = appt.get("date",   patient.get("appointment_date", ""))
    time_   = appt.get("time",   patient.get("appointment_time", ""))
    dept    = appt.get("department", patient.get("department", ""))
    reschedule_requested = state.get("reschedule_requested", False)
    updates = {"routing_path": list(state.get("routing_path") or []) + ["appointment_agent"]}

    last_human = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            last_human = msg.content; break
    low   = last_human.lower().strip()
    words = set(re.sub(r"[^\w\s]", "", low).split())

    # ── EMERGENCY (always wins) ───────────────────────────────────────────
    if intent == "emergency":
        updates["emergency_detected"] = True; updates["phase"] = "wrapup"
        return _msg("Please hang up and call 911 immediately — I want to make sure you get help right away.", updates)

    # ── HUMAN REQUEST ─────────────────────────────────────────────────────
    if intent == "request_human":
        updates["escalation_requested"] = True; updates["phase"] = "wrapup"
        resp = (f"Of course, {first}. I'll have a receptionist call you back within 2 business hours — Monday to Friday, 8 AM to 5 PM. Thank you for your patience!"
                if lang == "en" else
                f"Por supuesto, {first}. Un recepcionista le llamará en 2 horas hábiles — lunes a viernes, 8 AM a 5 PM. ¡Gracias por su paciencia!")
        return _msg(resp, updates)

    # ── GOODBYE ───────────────────────────────────────────────────────────
    if intent == "goodbye" or words & DONE_WORDS:
        return await _end_call(first, lang, updates)

    # ── ALREADY RESCHEDULED — handle "anything else?" responses ─────────
    if state.get("new_appointment_slot"):
        slot = state.get("new_appointment_slot")
        no_signals = {"no","nothing","nope","all good","all set","that's all","that's it",
                      "no gracias","eso es todo","nada","okay","ok","great","perfect","thanks","thank you",
                      "gracias","bye","goodbye","adiós"}
        if words & no_signals or low in no_signals or intent in ("goodbye", "unclear") or len(words) <= 3:
            return await _end_call(first, lang, updates)
        # Any substantive question — answer it then end
        faq = await search_faq_tool(last_human)
        if faq:
            prompt = (f"Answer '{last_human}' using: {faq}. 1 sentence." if lang == "en"
                      else f"Responde '{last_human}' usando: {faq}. 1 oración.")
            resp = await _gen(prompt, lang)
        else:
            resp = (f"Is there anything else I can help you with, {first}?"
                    if lang == "en" else
                    f"¿Hay algo más en lo que pueda ayudarle, {first}?")
        return _msg(resp, updates)

    # ── ALREADY CANCELLED — handle "anything else?" responses ────────────
    if state.get("cancellation_confirmed"):
        no_signals = {"no","nothing","nope","all good","that's all","no gracias","eso es todo","okay","ok","thanks","thank you","gracias","bye","goodbye"}
        if words & no_signals or low in no_signals or intent == "goodbye" or len(words) <= 3:
            return await _end_call(first, lang, updates)
        resp = (f"Is there anything else I can help you with, {first}?"
                if lang == "en" else
                f"¿Hay algo más en lo que pueda ayudarle, {first}?")
        return _msg(resp, updates)

    # ── STEP 1: Patient answered "would you like to confirm?" ─────────────
    # Only fires ONCE — before change_requested or reschedule_requested is set
    change_requested = state.get("change_requested", False)
    if state.get("appointment_communicated") and not change_requested and not state.get("reschedule_requested") and not state.get("new_appointment_slot") and not state.get("cancellation_confirmed"):

        is_yes = (bool(words & YES) or intent in ("confirm_appointment", "confirm_identity") or
                  any(w in low for w in ["yes","yeah","keep","confirm","sure","okay"]))
        is_no  = (bool(words & NO)  or intent in ("cancel_appointment", "reschedule_appointment") or
                  any(w in low for w in ["no","cancel","reschedule","change","don't","want"]))

        if is_yes and not any(w in low for w in ["cancel","reschedule","change","no","don't"]):
            # Patient confirmed — done
            updates["call_topics"] = list(state.get("call_topics") or []) + ["confirmed_by_patient"]
            if lang == "es":
                resp = f"Perfecto, {first}. Su cita está confirmada. ¿Hay algo más en lo que pueda ayudarle?"
            else:
                resp = f"Perfect, {first}. Your appointment is all confirmed. Is there anything else I can help you with?"
            return _msg(resp, updates)

        if is_no or any(w in low for w in ["cancel","reschedule","change","different","no","don't","want"]):
            # Patient doesn't want to keep it — set flag and ask cancel or reschedule
            updates["change_requested"] = True
            updates["call_topics"] = list(state.get("call_topics") or []) + ["change_requested"]
            if lang == "es":
                resp = f"Entendido, {first}. ¿Prefiere cancelar su cita o reprogramarla para otro horario?"
            else:
                resp = f"Of course, {first}. Would you like to cancel your appointment or reschedule it for a different time?"
            return _msg(resp, updates)

    # ── STEP 1b: Patient answering "cancel or reschedule?" ────────────────
    # change_requested=True means we asked the question — now route their answer
    if change_requested and not state.get("reschedule_requested") and not state.get("cancellation_confirmed"):
        wants_reschedule = (intent == "reschedule_appointment" or
                           any(w in low for w in ["reschedule","rebook","change","different","reprogramar","cambiar"]))
        wants_cancel     = (intent == "cancel_appointment" or
                           any(w in low for w in ["cancel","cancelar"]))
        if wants_reschedule:
            updates["reschedule_requested"] = True
            updates["call_topics"] = list(state.get("call_topics") or []) + ["reschedule"]
            if lang == "es":
                resp = f"Por supuesto. ¿Tiene alguna fecha o horario preferido para su cita con {doc}?"
            else:
                resp = f"Of course. Do you have a preferred date or time in mind for your appointment with {doc}?"
            return _msg(resp, updates)
        if wants_cancel:
            updates["cancellation_confirmed"] = True
            updates["call_topics"] = list(state.get("call_topics") or []) + ["cancelled"]
            if lang == "es":
                resp = (f"Entendido. He cancelado su cita con {doc} el {date}. "
                        f"Puede llamarnos al {CLINIC_PHONE} o visitar {CLINIC_PORTAL} para reservar otra cita. "
                        f"¿Hay algo más en lo que pueda ayudarle?")
            else:
                resp = (f"Done. I've cancelled your appointment with {doc} on {date}. "
                        f"You can call us at {CLINIC_PHONE} or visit {CLINIC_PORTAL} to rebook anytime. "
                        f"Is there anything else I can help you with?")
            return _msg(resp, updates)
        # Unclear — re-ask cleanly
        if lang == "es":
            resp = f"Disculpe, {first}. ¿Desea cancelar su cita o reprogramarla?"
        else:
            resp = f"Sorry {first}, just to clarify — would you like to cancel your appointment or reschedule it?"
        return _msg(resp, updates)

    # ── STEP 2: Patient said cancel (direct, not via change flow) ────────
    if (intent == "cancel_appointment" or any(w in low for w in ["cancel","cancelar"])):
        if not state.get("cancellation_confirmed"):
            updates["cancellation_confirmed"] = True
            updates["call_topics"] = list(state.get("call_topics") or []) + ["cancelled"]
            if lang == "es":
                resp = (f"Entendido, {first}. He cancelado su cita con {doc} el {date}. "
                        f"Si desea reservar una nueva cita, puede llamarnos al {CLINIC_PHONE} o visitar {CLINIC_PORTAL}. "
                        f"¿Hay algo más en lo que pueda ayudarle?")
            else:
                resp = (f"Done, {first}. I've cancelled your appointment with {doc} on {date}. "
                        f"Whenever you're ready to rebook, you can call us at {CLINIC_PHONE} or visit {CLINIC_PORTAL}. "
                        f"Is there anything else I can help you with?")
            return _msg(resp, updates)

    # ── STEP 3: Patient said reschedule ───────────────────────────────────
    if (intent == "reschedule_appointment" or any(w in low for w in ["reschedule","rebook","change","reprogramar","cambiar"])):
        if not reschedule_requested:
            # Step 3a — ask preference first
            updates["reschedule_requested"] = True
            updates["call_topics"] = list(state.get("call_topics") or []) + ["reschedule"]
            if lang == "es":
                resp = f"Por supuesto, {first}. ¿Tiene alguna fecha o horario preferido para su cita con {doc}?"
            else:
                resp = f"Of course, {first}. Do you have a preferred date or time in mind for your appointment with {doc}?"
            return _msg(resp, updates)

        if reschedule_requested and not state.get("new_appointment_slot"):
            # Step 3b — they've told us their preference, offer the 3 slots
            slot = _match_slot(low, lang)
            if slot:
                # They already named a specific slot
                updates["new_appointment_slot"] = slot
                updates["call_topics"] = list(state.get("call_topics") or []) + ["reschedule_confirmed"]
                if lang == "es":
                    resp = (f"Perfecto, {first}. He reservado su cita para el {slot} con {doc}. "
                            f"Recibirá una confirmación por mensaje de texto. "
                            f"¿Hay algo más en lo que pueda ayudarle?")
                else:
                    resp = (f"Perfect, {first}. I've booked your appointment for {slot} with {doc}. "
                            f"You'll receive a text confirmation shortly. "
                            f"Is there anything else I can help you with?")
                return _msg(resp, updates)
            else:
                # Patient stated a preference or asked for options — offer the 3 slots
                if lang == "es":
                    resp = (f"Tengo estas citas disponibles próximamente: "
                            f"opción uno — {AVAILABLE_SLOTS_ES[0]}, "
                            f"opción dos — {AVAILABLE_SLOTS_ES[1]}, "
                            f"o opción tres — {AVAILABLE_SLOTS_ES[2]}. "
                            f"¿Cuál le viene mejor?")
                else:
                    resp = (f"Here are the next available appointments: "
                            f"option one — {AVAILABLE_SLOTS[0]}, "
                            f"option two — {AVAILABLE_SLOTS[1]}, "
                            f"or option three — {AVAILABLE_SLOTS[2]}. "
                            f"Which works best for you?")
                return _msg(resp, updates)

    # ── STEP 3c: Patient selecting a slot ─────────────────────────────────
    if reschedule_requested and not state.get("new_appointment_slot"):
        slot = _match_slot(low, lang)
        if slot:
            updates["new_appointment_slot"] = slot
            updates["call_topics"] = list(state.get("call_topics") or []) + ["reschedule_confirmed"]
            if lang == "es":
                resp = (f"Perfecto, {first}. He reservado su cita para el {slot} con {doc}. "
                        f"Recibirá confirmación por mensaje. ¿Hay algo más?")
            else:
                resp = (f"Perfect, {first}. I've booked your appointment for {slot} with {doc}. "
                        f"You'll get a text confirmation shortly. Is there anything else I can help you with?")
            return _msg(resp, updates)
        # Couldn't match — re-offer
        if lang == "es":
            resp = (f"Disculpe, ¿podría indicarme cuál prefiere? Tengo: {AVAILABLE_SLOTS_ES[0]}, "
                    f"{AVAILABLE_SLOTS_ES[1]}, o {AVAILABLE_SLOTS_ES[2]}.")
        else:
            resp = (f"Sure, Could you tell me which one works best? I have: {AVAILABLE_SLOTS[0]}, "
                    f"{AVAILABLE_SLOTS[1]}, or {AVAILABLE_SLOTS[2]}.")
        return _msg(resp, updates)

    # ── FAQ ───────────────────────────────────────────────────────────────
    if intent in ("ask_faq", "off_topic"):
        faq = await search_faq_tool(last_human)
        if faq:
            prompt = (f"Answer '{last_human}' using: {faq}. 1-2 sentences." if lang == "en"
                      else f"Responde '{last_human}' usando: {faq}. 1-2 oraciones.")
        else:
            prompt = (f"Can't fully answer. Direct to reception at {CLINIC_PHONE}. 1 sentence." if lang == "en"
                      else f"No puedo responder. Dirige al {CLINIC_PHONE}. 1 oración.")
        updates["call_topics"] = list(state.get("call_topics") or []) + ["faq"]
        return _msg(await _gen(prompt, lang), updates)

    # ── ANYTHING ELSE check ────────────────────────────────────────────────
    no_signals = {"no","nothing","nope","all good","all set","that's all","that's it","no gracias","eso es todo","nada"}
    if words & no_signals or low in no_signals:
        return await _end_call(first, lang, updates)

    # ── GENERIC FALLBACK — stay on script ────────────────────────────────
    appt_status = appt.get("status", patient.get("appointment_status", ""))
    prompt = (
        f"Patient {first} (appointment {appt_status}) said: '{last_human}'. "
        f"Respond in 1-2 sentences. Stay focused on their appointment. "
        f"If unclear, ask: would they like to confirm, cancel, or reschedule?"
        if lang == "en" else
        f"Paciente {first} (cita {appt_status}) dijo: '{last_human}'. "
        f"Responde en 1-2 oraciones. Enfócate en la cita. "
        f"Si no está claro, pregunta: ¿confirmar, cancelar o reprogramar?"
    )
    return _msg(await _gen(prompt, lang), updates)


async def _end_call(first, lang, updates):
    updates["phase"] = "wrapup"
    clinic_phone  = os.getenv("CLINIC_PHONE",  "1-800-555-0200")
    clinic_portal = os.getenv("CLINIC_PORTAL", "portal.riversidemedical.com")
    if lang == "es":
        resp = (f"Perfecto, {first}. Muchas gracias por llamar a Riverside Medical Centre. "
                f"Si necesita algo más puede llamarnos al {clinic_phone} o visitar {clinic_portal}. "
                f"¡Que tenga un excelente día!")
    else:
        resp = (f"Perfect, {first}. Thank you so much for calling Riverside Medical Centre — "
                f"it was a pleasure helping you. "
                f"If you need anything else, reach us at {clinic_phone} or {clinic_portal}. Take care!")
    return _msg(resp, updates)


def _match_slot(text, lang):
    slots = AVAILABLE_SLOTS_ES if lang == "es" else AVAILABLE_SLOTS
    kw = [
        ["tuesday","15","9","9:00","one","first","1","uno","primera"],
        ["wednesday","16","2","2:30","two","second","2","dos","segunda"],
        ["friday","18","11","11:00","three","third","3","tres","tercera"],
    ]
    t = text.lower()
    best, best_i = 0, None
    for i, keys in enumerate(kw):
        s = sum(1 for k in keys if k in t)
        if s > best:
            best, best_i = s, i
    return slots[best_i] if best > 0 and best_i is not None else None


async def _gen(prompt, lang):
    return await llm_chat(system=lang_system(lang), user=prompt, max_tokens=120, temperature=0.65)


def _msg(text, updates):
    updates["messages"] = [AIMessage(content=text)]
    updates["agent_responses"] = (updates.get("agent_responses") or [])[-2:] + [text]
    return updates
