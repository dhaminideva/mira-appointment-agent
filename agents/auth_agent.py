"""
agents/auth_agent.py — MIRA streamlined flow
- 2 failed lookups → new patient path → ask best callback time → log → goodbye
- On auth success: read appointment details, ask "would you like to confirm?"
- No DOB verification
"""
import os, re, json
from langchain_core.messages import AIMessage, HumanMessage
from graph.state import CallState
from tools.patient_tools import lookup_patient_tool
from agents.lang_prompts import format_prompt, lang_system
from agents.llm_client import llm_chat

CLINIC_PHONE = os.getenv("CLINIC_PHONE", "1-800-555-0200")

def _safe_path(state, node):
    return list(state.get("routing_path") or []) + [node]

def _safe_record(record):
    if isinstance(record, dict): return record
    if isinstance(record, str):
        try: return json.loads(record)
        except: return None
    return None

# Hardcoded appointment delivery — never LLM
APPOINTMENT_RESPONSES = {
    "en": {
        "confirmed":    "Thank you for confirming, {first}! Your appointment with {doctor} in {department} is confirmed for {date} at {time}. Would you like to keep this appointment?",
        "cancelled":    "Thank you for confirming, {first}. I can see your appointment with {doctor} on {date} was previously cancelled. Would you like to rebook?",
        "rescheduled":  "Thank you for confirming, {first}. Your appointment has been rescheduled to {date} at {time} with {doctor}. Would you like to confirm this new time?",
        "pending":      "Thank you for confirming, {first}. Your appointment with {doctor} in {department} on {date} at {time} is currently pending confirmation. Would you like me to confirm it?",
    },
    "es": {
        "confirmed":    "Gracias por confirmar, {first}. Su cita con {doctor} en {department} está confirmada para el {date} a las {time}. ¿Desea mantener esta cita?",
        "cancelled":    "Gracias por confirmar, {first}. Veo que su cita con {doctor} el {date} fue cancelada anteriormente. ¿Le gustaría reprogramarla?",
        "rescheduled":  "Gracias por confirmar, {first}. Su cita ha sido reprogramada para el {date} a las {time} con {doctor}. ¿Desea confirmar este nuevo horario?",
        "pending":      "Gracias por confirmar, {first}. Su cita con {doctor} en {department} el {date} a las {time} está pendiente de confirmación. ¿Desea confirmarla?",
    },
}

def _appointment_message(lang, record, first):
    status = (record.get("appointment_status") or "pending").lower().strip()
    lang_map = APPOINTMENT_RESPONSES.get(lang, APPOINTMENT_RESPONSES["en"])
    template = lang_map.get(status, lang_map["pending"])
    return template.format(
        first=first,
        doctor=record.get("doctor_name", "your doctor"),
        department=record.get("department", "the clinic"),
        date=record.get("appointment_date", "your scheduled date"),
        time=record.get("appointment_time", "your scheduled time"),
    )


async def auth_agent_node(state: CallState) -> dict:
    lang = state.get("preferred_language", "en")
    phase = state.get("phase", "greeting")
    intent = state.get("current_intent", "unclear")
    auth_attempts = state.get("auth_attempts", 0)
    confirm_attempts = state.get("confirm_attempts", 0)
    patient = _safe_record(state.get("patient_record"))
    updates: dict = {"routing_path": _safe_path(state, "auth_agent")}

    last_human = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break
    low = last_human.lower().strip()

    # ── GREETING ──────────────────────────────────────────────────────────
    if phase == "greeting" or last_human == "[CALL_CONNECTED]":
        response = await llm_chat(system=lang_system(lang),
                                   user=format_prompt("greeting", lang), max_tokens=80)
        updates["phase"] = "auth_phone"
        return _msg(response, updates)

    # ── NEW PATIENT CALLBACK FLOW ─────────────────────────────────────────
    # After 2 failed lookups we set phase="new_patient" — collect best callback time
    if phase == "new_patient":
        # Any response here = they've given their preferred time
        if len(low) > 2:
            # Log the callback request and say goodbye
            topics = list(state.get("call_topics") or [])
            topics.append("new_patient_callback")
            updates["call_topics"] = topics
            updates["phase"] = "ended"
            # Store callback time in routing path for the interaction log
            updates["routing_path"] = _safe_path(state, f"callback_time:{last_human[:40]}")
            if lang == "es":
                response = (
                    f"Perfecto. Tomaré nota de que prefiere que le llamemos {last_human}. "
                    f"Uno de nuestros recepcionistas se pondrá en contacto con usted. "
                    f"Muchas gracias por llamar a Riverside Medical Centre — ¡que tenga un excelente día!"
                )
            else:
                response = (
                    f"Perfect. I'll make a note that the best time to reach you is {last_human}. "
                    f"One of our receptionists will give you a call to get your appointment set up. "
                    f"Thank you so much for calling Riverside Medical Centre — have a wonderful day!"
                )
            return _msg(response, updates)
        # Still waiting for time
        if lang == "es":
            response = "¿Cuál sería el mejor horario para que le llamemos? Estamos disponibles de lunes a viernes, de 8 AM a 5 PM."
        else:
            response = "What would be the best time for us to call you back? We're available Monday to Friday, 8 AM to 5 PM."
        return _msg(response, updates)

    # ── PHONE PROVIDED ────────────────────────────────────────────────────
    if phase in ("auth_phone", "greeting") and intent == "provide_phone":
        phone = state.get("phone_provided", "")
        if not phone or len(phone) < 7:
            prompt = ("Number was incomplete. Ask warmly for the full 10-digit number. 1 sentence."
                      if lang == "en" else
                      "El número no fue completo. Pide los 10 dígitos. 1 oración.")
            response = await llm_chat(system=lang_system(lang), user=prompt, max_tokens=60)
            return _msg(response, updates)

        record = _safe_record(await lookup_patient_tool(phone))
        updates["auth_attempts"] = auth_attempts + 1

        if record:
            updates["patient_record"] = record
            updates["phase"] = "auth_confirm"
            updates["appointment_details"] = {
                "date":       record.get("appointment_date", ""),
                "time":       record.get("appointment_time", ""),
                "doctor":     record.get("doctor_name", ""),
                "department": record.get("department", ""),
                "status":     record.get("appointment_status", "pending"),
            }
            response = await llm_chat(system=lang_system(lang),
                                       user=format_prompt("auth_confirm", lang,
                                           first_name=record["first_name"],
                                           last_name=record["last_name"]),
                                       max_tokens=80)
        elif auth_attempts + 1 >= 2:
            # Two failed attempts — new patient path
            updates["phase"] = "new_patient"
            topics = list(state.get("call_topics") or [])
            topics.append("lookup_failed")
            updates["call_topics"] = topics
            if lang == "es":
                response = (
                    "No se preocupe — es posible que no tenga una cuenta registrada con nosotros todavía. "
                    "Con mucho gusto le conectamos con nuestra recepción para programar su primera cita. "
                    "¿Cuál sería el mejor horario para llamarle? Estamos disponibles de lunes a viernes, de 8 AM a 5 PM."
                )
            else:
                response = (
                    "No worries — it looks like you may not have an account with us just yet. "
                    "I'd be happy to have one of our receptionists call you to book your first appointment. "
                    "What would be the best time to reach you? We're available Monday to Friday, 8 AM to 5 PM."
                )
        else:
            response = await llm_chat(system=lang_system(lang),
                                       user=format_prompt("auth_not_found_soft", lang), max_tokens=80)
        return _msg(response, updates)

    # ── IDENTITY CONFIRM ──────────────────────────────────────────────────
    if phase == "auth_confirm":
        positive = {"yeah","yep","yes","correct","right","sure","okay","ok","mhmm",
                    "uh huh","that's me","speaking","sí","si","claro","that is me","it's me"}
        negative = {"no","nope","not me","wrong","incorrect","no soy","that's not"}
        words = set(low.replace(".", " ").replace(",", " ").split())
        is_positive = (intent == "confirm_identity" or bool(words & positive) or len(low) <= 8)
        is_negative = (intent == "deny_identity" or bool(words & negative))
        patient = _safe_record(state.get("patient_record"))

        if is_negative:
            updates["confirm_attempts"] = confirm_attempts + 1
            if confirm_attempts + 1 >= 2:
                updates["phase"] = "wrapup"
                response = await llm_chat(system=lang_system(lang),
                                           user=format_prompt("auth_not_found_final", lang), max_tokens=80)
            else:
                updates["patient_record"] = None
                updates["appointment_details"] = None
                updates["phase"] = "auth_phone"
                fn = patient.get("first_name","") if patient else ""
                ln = patient.get("last_name","") if patient else ""
                response = await llm_chat(system=lang_system(lang),
                                           user=format_prompt("identity_denied", lang,
                                               first_name=fn, last_name=ln), max_tokens=80)
        elif is_positive:
            updates["is_authenticated"] = True
            updates["phase"] = "main"
            if patient:
                updates["patient_record"] = patient
            first = patient["first_name"] if patient else "there"
            print(f"[auth] Confirmed: {first} | status: {(patient or {}).get('appointment_status','?')}")
            # Hardcoded — read appointment and ask to confirm
            response = _appointment_message(lang, patient or {}, first)
            updates["appointment_communicated"] = True
            topics = list(state.get("call_topics") or [])
            status = (patient or {}).get("appointment_status", "pending")
            if f"appointment_{status}" not in topics:
                topics.append(f"appointment_{status}")
            updates["call_topics"] = topics
        else:
            first = patient.get("first_name", "you") if patient else "you"
            re_ask = (f"Caller said '{last_human}'. Re-ask yes/no: am I speaking with {first}? 1 sentence."
                      if lang == "en" else
                      f"El paciente dijo '{last_human}'. Vuelve a preguntar sí/no. 1 oración.")
            response = await llm_chat(system=lang_system(lang), user=re_ask, max_tokens=60)
        return _msg(response, updates)

    # ── AUTH_PHONE FALLBACK ───────────────────────────────────────────────
    if phase == "auth_phone":
        words = set(re.sub(r"[^\w\s]", "", low).split()) if low else set()
        ready = {"ready","go","ahead","fine","alright","listo","ya"}
        if words & ready or low in {"i'm ready","im ready","okay","ok","sure","yep","yeah"}:
            return _msg("Perfect, go ahead — I'm listening!" if lang == "en" else "¡Perfecto! Adelante.", updates)
        wait = {"wait","hold","second","minute","moment","sec","espera","momento"}
        if words & wait or any(w in low for w in ["give me","one sec","just a","hang on"]):
            return _msg("Of course, take your time!" if lang == "en" else "¡Por supuesto, tómese su tiempo!", updates)
        if state.get("language_switched"):
            return _msg("Of course! Could you share the phone number on your account?" if lang == "en"
                        else "¡Por supuesto! ¿Podría darme su número de teléfono de cuenta?", updates)
        contextual = (f"Caller said: '{last_human}'. Answer briefly then ask for account phone number. 2 sentences max."
                      if lang == "en" else
                      f"Dijo: '{last_human}'. Responde brevemente y pide número de teléfono. 2 oraciones.")
        response = await llm_chat(system=lang_system(lang), user=contextual, max_tokens=100)
        return _msg(response, updates)

    # Final fallback
    prompt = ("Could you share the phone number on your account?" if lang == "en"
              else "¿Podría compartir su número de teléfono de cuenta?")
    return _msg(await llm_chat(system=lang_system(lang), user=prompt, max_tokens=60), updates)


def _msg(text, updates):
    updates["messages"] = [AIMessage(content=text)]
    updates["agent_responses"] = (updates.get("agent_responses") or [])[-2:] + [text]
    return updates
