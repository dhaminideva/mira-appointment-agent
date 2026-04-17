# 🎙️ MIRA — Bilingual Medical Appointment Voice Assistant

> **Live demo — call MIRA right now:** [`+1 (855) 617-7835`](tel:+18556177835)  
> *Real phone call. Real voice. Real integrations. Pick up and say "Hola" to switch languages.*

---


## 📹 Demo

[![Watch MIRA Demo](https://img.shields.io/badge/▶%20Watch%20Full%20Demo-Google%20Drive-0891B2?style=for-the-badge&logo=googledrive&logoColor=white)](https://drive.google.com/file/d/17mi5aqyh7v1lUeXdykkdFmLwN_vGpFag/view?usp=sharing)

> *Full walkthrough — happy path (auth → appointment delivery → email), language switch to Spanish, failed verification error path, and escalation request.*

**What the demo covers:**

| Scenario | What to watch for |
|---|---|
| ✅ Happy path | Patient authenticated → appointment details delivered → confirmation email received |
| 🌐 Language switch | "Hola" mid-call → MIRA switches to Spanish instantly, same voice |
| ❌ Error path | Wrong number × 2 → graceful exit → no email sent |
| 📞 Escalation | "Can I speak to someone?" → MIRA arranges receptionist callback |

---

## What Is This

MIRA is a production-ready bilingual voice AI agent that handles real inbound medical appointment calls end-to-end. A patient dials a real phone number, speaks naturally in English or Spanish, and MIRA authenticates them, retrieves their appointment details from a live database, allows them to confirm, cancel or reschedule — and sends a personalised summary email — all without a human receptionist.

Built entirely from scratch in Python. No no-code platforms. No black-box wrappers. Every routing decision is deterministic and auditable.

```
Patient dials Riverside Medical Centre
       ↓
Twilio receives call → opens WebSocket
       ↓
Deepgram transcribes speech in real time (EN + ES)
       ↓
LangGraph 8-node multi-agent pipeline processes utterance
       ↓
ElevenLabs speaks the response in the patient's language
       ↓
n8n → Google Sheets lookup and interaction logging
       ↓
SendGrid sends post-call appointment summary email
```

---

## Key Features

| Feature | Detail |
|---|---|
| 📞 **Live Phone Number** | Call Riverside Medical Centre right now |
| 🌐 **Real-Time Bilingual** | EN↔ES switching mid-call on a single word trigger |
| 🧠 **LangGraph Multi-Agent** | 8 specialist agents with deterministic supervisor routing |
| 🔐 **Two-Factor Auth** | Phone number + identity confirmation |
| 📋 **4 Appointment Statuses** | Confirmed / Cancelled / Rescheduled / Pending |
| 🔄 **Live Rescheduling** | Patient can reschedule mid-call — MIRA offers available slots |
| 📧 **Auto Email** | Status-specific HTML email fires after every authenticated call |
| 📊 **Live Data** | Google Sheets lookup and post-call logging via n8n webhooks |
| 🎯 **Zero Hallucination on Facts** | All appointment content is hardcoded — LLM never generates clinical data |
| 🔄 **Full Audit Trail** | Every routing decision logged to `routing_path` in state |
| 🚨 **Emergency Handling** | Detects medical emergency keywords → instructs patient to call 911 |
| 📞 **Escalation Path** | Human receptionist transfer on request |
| 😤 **Frustration Detection** | Sentiment watcher triggers de-escalation agent automatically |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TELEPHONY LAYER                              │
│   Patient → Twilio (Riverside Medical) → WebSocket /media-stream│
└─────────────────────┬───────────────────────────────────────────┘
                      │ μ-law audio stream (20ms chunks)
┌─────────────────────▼───────────────────────────────────────────┐
│                     STT LAYER                                    │
│  Deepgram Nova-2 · language=multi · numerals=True · 800ms end  │
└─────────────────────┬───────────────────────────────────────────┘
                      │ transcript
┌─────────────────────▼───────────────────────────────────────────┐
│                  INTELLIGENCE LAYER (LangGraph)                  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Lang Detect  │→ │Intent Classif│→ │  Sentiment   │          │
│  │  EN ↔ ES    │  │  +spoken dig │  │  Watcher     │          │
│  └──────────────┘  └──────────────┘  └──────┬───────┘          │
│                                              │                   │
│                                    ┌─────────▼────────┐         │
│                                    │   SUPERVISOR     │         │
│                                    │  (deterministic) │         │
│                                    │   no LLM · <5ms  │         │
│                                    └──┬───┬───┬───┬───┘         │
│                                       │   │   │   │             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──┘ ┌─┘ ┌─┘  └──┐          │
│  │  Auth  │ │Appoint.│ │Rapport │ │Esc.│FAQ│Wrapup  │          │
│  │ Agent  │ │ Agent  │ │ Agent  │ │    │   │Agent   │          │
│  └────────┘ └────────┘ └────────┘ └────┘   └────────┘          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ response text
┌─────────────────────▼───────────────────────────────────────────┐
│                      TTS LAYER                                   │
│  ElevenLabs eleven_multilingual_v2 · MIRA voice · MP3→μ-law    │
└─────────────────────┬───────────────────────────────────────────┘
                      │ audio back to patient via Twilio WebSocket
┌─────────────────────▼───────────────────────────────────────────┐
│                   INTEGRATIONS (n8n)                             │
│  Google Sheets (lookup) · Google Sheets (log) · SendGrid email  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why Custom Stack — Not Retell or VAPI

Platforms like Retell and VAPI are excellent for standard linear call flows. MIRA required three things they could not provide:

**1. Mid-call language switching without re-initialising TTS**
Retell and VAPI require separate voice configurations per language — different API calls, different voice IDs. MIRA needed to switch languages on a single word trigger ("Hola") while using the same voice. ElevenLabs Multilingual v2 handles this with one API call. A no-code platform would have required rebuilding the entire call flow per language.

**2. Deterministic supervisor with no LLM routing**
Every routing decision in MIRA is pure if/else logic. Emergency always routes to escalation. A frustrated patient always goes to rapport agent before anything else. An LLM router could hallucinate — sending a distressed patient asking about a medical emergency to the FAQ agent. Custom code gave full, auditable control.

**3. Dynamic rescheduling logic with branching mid-call**
When a patient wants to reschedule, MIRA presents available slots, holds the selection in state across multiple turns, and confirms only when the patient has chosen. No-code platforms cannot maintain this kind of multi-turn transactional state without significant workarounds.

The custom stack took significantly more engineering time. Every line is explainable. Every decision is auditable. That was the point.

---

## Project Structure

```
mira-appointment-agent/
│
├── voice/
│   ├── twilio_server.py       # Entry point · 3 routes · WebSocket · post-call logic
│   └── pipeline.py            # Single-turn coordinator · messages[ai_count_before] fix
│
├── graph/
│   ├── graph.py               # StateGraph · all agents → END · no supervisor loops
│   └── state.py               # CallState TypedDict · appointment fields · full audit
│
├── agents/
│   ├── supervisor.py          # Deterministic router · no LLM · <5ms · priority order
│   ├── intent_classifier.py   # Hybrid: keywords first · LLM for ambiguous only
│   ├── language_detector.py   # Sticky EN↔ES · 14 override phrases · digit-safe
│   ├── sentiment_watcher.py   # Bilingual keyword lists · frustration counter
│   ├── auth_agent.py          # Gatekeeper · APPOINTMENT_RESPONSES hardcoded · n8n lookup
│   ├── appointment_agent.py   # Post-auth · rescheduling flow · goodbye detection
│   ├── rapport_agent.py       # De-escalation · fires once per call · frustration≥2
│   ├── escalation_agent.py    # Receptionist transfer · 911 for medical emergencies
│   ├── wrapup_agent.py        # Post-call log · LLM summary · phase=ended
│   ├── lang_prompts.py        # All bilingual prompts · EN + ES per agent
│   └── llm_client.py          # OpenRouter wrapper · Llama 3.1 8B
│
├── tools/
│   ├── patient_tools.py       # n8n webhook caller · mock fallback · list/dict handling
│   └── email_sender.py        # SendGrid · 4 HTML templates · 3-condition guard
│
├── n8n_workflows/
│   ├── lookup_patient_workflow.json
│   └── log_interaction_workflow.json
│
├── .env                       # All secrets (never committed)
├── .env.example               # Template with all variable names
├── requirements.txt
└── LAUNCH_MIRA.bat            # One-command startup
```

---

## Tech Stack

| Layer | Technology | Why This Choice |
|---|---|---|
| **Telephony** | Twilio Media Streams | Real PSTN number · WebSocket audio · call recording API |
| **STT** | Deepgram Nova-2 | Best accuracy on 8kHz phone audio · multilingual · numerals=True |
| **LLM** | Llama 3.1 8B via OpenRouter | Fast · cheap · used for dynamic turns only — never clinical data |
| **Orchestration** | LangGraph StateGraph | Deterministic state machine · full audit trail · persistent CallState |
| **TTS** | ElevenLabs Multilingual v2 | Same voice handles EN + ES · warmer than Polly/WaveNet for healthcare |
| **Voice Server** | Flask + flask-sock | Sync threads avoid SSL conflicts with Twilio WebSocket on Windows |
| **Integrations** | n8n + Google Sheets | Webhook-based · no SDK dependency · independently testable via Postman |
| **Email** | SendGrid REST API | 100/day free · REST avoids SSL threading issues that broke httpx |
| **Tunnel** | Cloudflare Tunnel | Free · no account · native WebSocket support · no ngrok interstitial |

---

## LLM vs Deterministic — Design Principle

> **If it touches patient data, routing, or safety — it is deterministic. If it is conversational, contextual, or post-call — it can be LLM.**

| Component | Type | Reason |
|---|---|---|
| Supervisor routing | **Deterministic** | Safety — no hallucination on routing decisions |
| Appointment detail delivery | **Deterministic** | Patient data must be exact — directly from the database |
| Greeting | **Deterministic** | Speed — <200ms, no LLM lag on first response |
| Emergency handling | **Deterministic** | Always routes to escalation, no exceptions |
| Email trigger | **Deterministic** | Boolean business rule — three conditions all must be True |
| Language detection | **Deterministic** | Speed + reliability — keyword lists are unambiguous |
| Rescheduling slot offer | **Deterministic** | Hardcoded available slots for demo — database query in production |
| Intent (ambiguous) | **LLM** | Multi-word unclear utterances need reasoning |
| Empathy responses | **LLM** | Context-dependent tone — different situations need different warmth |
| Post-call summary | **LLM** | Unique per call · post-call so no latency impact on patient |

---

## Conversation Flows

### Happy Path — Appointment Confirmation
```
Patient: "Hi I need to check my appointment"
MIRA:    "Could you share the phone number on your account?"
Patient: "8 1 3 5 5 5 0 0 0 5"
MIRA:    "Just to confirm — am I speaking with Diana Walsh?"
Patient: "Yes that's me"
MIRA:    "Thank you Diana! Your appointment with Dr Sarah Chen
          in Cardiology is confirmed for Tuesday April 15th
          at 10:30 AM. Is there anything else I can help you with?"
Patient: "No thank you"
MIRA:    "Perfect Diana. I'll send you a confirmation email shortly.
          Please arrive 10 minutes early. Have a great day!"

→ Sheets log written ✓
→ SendGrid confirmation email fired ✓
→ Call recording saved ✓
```

### Rescheduling Path
```
Patient: "Actually I need to change that appointment"
MIRA:    "Of course — I have the following slots available
          with Dr Chen: Tuesday April 15th at 9AM,
          Wednesday April 16th at 2:30PM,
          or Friday April 18th at 11AM.
          Which would you prefer?"
Patient: "Wednesday at 2:30 works"
MIRA:    "Perfect — I've rescheduled your appointment to
          Wednesday April 16th at 2:30 PM with Dr Sarah Chen.
          Is there anything else I can help you with?"
```

### Error Path
```
Patient gives wrong number × 2
MIRA:   "No worries at all — one of our receptionists will
         reach out to you personally within one business day.
         Thank you for calling Riverside Medical Centre — 
         have a wonderful day!"

→ phase = ended immediately
→ No email sent (unauthenticated guard)
→ Sheets log: authenticated=FALSE
```

### Language Switch (mid-call)
```
Patient: "Hola, necesito ayuda con mi cita"
          ↓ language_detector → language='es', switched=True
          ↓ supervisor routes to auth_agent
MIRA:    "¡Hola! Con gusto le ayudo. ¿Podría compartir el número
          de teléfono asociado con su cuenta?"
```

---

## Notable Engineering Decisions

### The messages[ai\_count\_before] Fix
The most subtle bug in the project. LangGraph loops agents back to supervisor. Auth_agent would generate the full appointment delivery message → supervisor would re-route to appointment_agent → appointment_agent would append a shorter message → `pipeline.py` was returning `messages[-1]` (the last message). The fix: count AI messages before `graph.ainvoke()`, then return `messages[ai_count_before]` — the first new message this turn. Combined with setting all agents → END in the graph.

### SSL Threading on Windows
ElevenLabs returned HTTP 401 inside Flask threads — not an auth error. Windows Flask threads have a different SSL event loop context than the main process. httpx fails SSL certificate chain validation in that context. Fix: switched to `requests` library with `verify=False`. Confirmed by running the identical POST from `threading.Thread()` which returned 200.

### Why Appointment Data is Never LLM-Generated
If MIRA told a patient "your appointment with Dr Chen is at 3pm" and the real time was 10:30am, the patient would miss their appointment. All four APPOINTMENT_RESPONSES are hardcoded Python strings populated from the database record. The LLM generates conversational framing only — never dates, times, doctor names, or department names.

### Asymmetric Language Switching
Switching TO Spanish triggers on one word ("Hola"). Switching BACK to English requires 3+ strong signals. This is intentional — phone numbers spoken as digits ("8 1 3 5 5 5") would otherwise trigger an English switch mid-Spanish call. The asymmetry protects the language state during number input.

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js (for n8n)
- ffmpeg (for audio conversion)
- Cloudflare cloudflared CLI
- Active accounts: Twilio · Deepgram · ElevenLabs · OpenRouter · SendGrid

### Environment Setup

```bash
git clone https://github.com/yourusername/mira-appointment-agent.git
cd mira-appointment-agent
pip install -r requirements.txt
cp .env.example .env
# Fill in all API keys — see .env.example for all variables
```

### Start (3 windows, this exact order)

**Window 1 — n8n**
```bash
n8n start
# Wait for: Activated workflow "Riverside Medical - Lookup Patient"
# Wait for: Activated workflow "Riverside Medical - Log Interaction"
```

**Window 2 — Cloudflare**
```bash
cloudflared tunnel --url http://localhost:5050
# Copy the URL → update .env NGROK_VOICE_URL → update Twilio Console webhook
# URL: https://[tunnel-url].trycloudflare.com/incoming-call
```

**Window 3 — MIRA**
```bash
python voice/twilio_server.py
# Wait for: Running on http://0.0.0.0:5050
```

### Test Patients

| Phone | Name | Appointment | Status |
|---|---|---|---|
| 8135550005 | Diana Walsh | Dr Chen · Cardiology · Apr 15 10:30AM | ✅ Confirmed |
| 8135550006 | Robert Patel | Dr James · Neurology · Apr 16 2:00PM | ⏳ Pending |
| 4045550001 | Sarah Mitchell | Dr Brown · General · Apr 17 9:00AM | ✅ Confirmed |
| 4045550002 | James Thornton | Dr Lee · Orthopaedics · Apr 18 3:30PM | 🔄 Rescheduled |
| 4045550003 | Emily Reyes | Dr Chen · Cardiology · Apr 15 11:00AM | 📄 Pending docs |
| 4045550004 | Michael Chen | Dr Smith · Dermatology · Apr 19 1:00PM | ❌ Cancelled |
| 8005550010 | Maria Gonzalez | Dr Martinez · General · Apr 15 9:30AM | ✅ Confirmed (ES) |
| 8005550011 | Carlos Mendoza | Dr Lopez · Cardiology · Apr 16 10:00AM | ⏳ Pending (ES) |

---

## Post-Call Email Examples

Each authenticated call triggers a status-specific HTML email:

| Status | Subject | Colour |
|---|---|---|
| Confirmed | Your Appointment is Confirmed — Riverside Medical 📅 | Green |
| Rescheduled | Your Appointment Has Been Rescheduled | Teal |
| Cancelled | Your Appointment Cancellation — Riverside Medical | Neutral |
| Pending | Your Appointment Request is Being Processed | Amber |

All emails include: doctor name, department, date and time, clinic address, parking instructions, and a reminder to arrive 10 minutes early. Spanish-speaking patients receive an English email with a bilingual footer offering specialist support.

---

## What I Would Build Next

**If I had one more week:**
- TTS streaming — pipe audio chunks as they generate so the patient hears MIRA in <200ms
- Real appointment slot availability — query a calendar API (Google Calendar or Calendly) instead of hardcoded slots
- Appointment reminder outbound calls — MIRA proactively calls patients 24 hours before their appointment
- SMS confirmation alongside email — Twilio SMS after rescheduling
- Twilio `track='inbound_track'` — eliminate the speaking flag by separating audio channels at source

**Production path:**
- Containerise with Docker · deploy on AWS ECS or GCP Cloud Run
- Replace Google Sheets with PostgreSQL + Redis cache for <10ms lookups
- OpenTelemetry traces per call · Datadog dashboards for no-show rate, reschedule rate, containment
- A/B prompt testing framework using routing_path analytics
- HIPAA compliance review — encrypted storage, access logging, BAA with all vendors
- Gunicorn WSGI + FastAPI on Linux (SSL threading issues are Windows-specific)

---

## Adapting This Project

MIRA is built on the same architecture as ARIA (Observe Insurance claims agent). The conversation intelligence layer — LangGraph state machine, deterministic supervisor, bilingual detection, sentiment tracking — is domain-agnostic. Adapting to a new use case means updating:

- The Google Sheet schema
- The n8n webhook payloads  
- The hardcoded response strings
- The email templates
- The agent names in prompts

The core pipeline, WebSocket handling, TTS/STT integration, and post-call logic remain identical.

---

## Built With AI Assistance

Claude (Anthropic) was used extensively throughout development — for debugging, architectural advice, code review, and iterating on fixes. Every suggestion was understood, tested, and validated before being applied. The architectural decisions — deterministic supervisor, hardcoded appointment responses, messages[ai_count_before] fix, SSL threading diagnosis — emerged from real debugging sessions, not theoretical planning.

The codebase reflects how I actually work: AI as a capable collaborator, not a replacement for engineering judgement.

---

<div align="center">

**Built for the Hiya AI Engineer Assessment**

*Custom architecture · Live telephony · Real integrations · Zero no-code black boxes*

[📞 Call MIRA: Riverside Medical Centre](tel:+18556177835) · [📧 dhaminidevaraj@gmail.com](mailto:dhaminidevaraj@gmail.com)

</div>
