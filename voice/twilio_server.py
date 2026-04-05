"""
voice/twilio_server.py — MIRA Medical Appointment Voice Assistant
Fixes: auto-hangup after farewell, interaction logging in finally block
"""

import os, json, asyncio, base64, sys, time, threading, io
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from flask import Flask, request, Response
from flask_sock import Sock
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
sock = Sock(app)

from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from voice.pipeline import MIRAVoicePipeline

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOICE_ID           = os.getenv("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9")
CLINIC_NAME        = os.getenv("CLINIC_NAME", "Riverside Medical Centre")

GREETING_TEXT = (
    f"Thank you for calling {CLINIC_NAME}. "
    f"I'm MIRA, your appointment assistant — I'm here to help you today. "
    f"Before we get started, I just need to verify your identity. "
    f"Could you please share the phone number associated with your account?"
)

print(f"[elevenlabs] Key: {ELEVENLABS_API_KEY[:15]}... Voice: {VOICE_ID}")


def text_to_speech_mulaw(text: str) -> bytes:
    import requests
    from pydub import AudioSegment
    if len(text) > 400:
        text = text[:400]
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.75, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": False},
        "output_format": "mp3_44100_64",
    }
    try:
        resp = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
                             headers=headers, json=payload, timeout=25, verify=False)
        resp.raise_for_status()
        mp3_bytes = resp.content
        print(f"[TTS] {len(mp3_bytes)} MP3 bytes | {len(text)} chars")
        audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        import audioop
        mulaw = audioop.lin2ulaw(audio.raw_data, 2)
        print(f"[TTS] -> {len(mulaw)} mulaw bytes")
        return mulaw
    except Exception as e:
        print(f"[TTS error] {e}")
        return b""


def send_audio_threaded(ws, stream_sid, audio_bytes, dg_connection=None):
    def _send():
        chunk_size = 160
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            try:
                ws.send(json.dumps({"event": "media", "streamSid": stream_sid,
                                    "media": {"payload": base64.b64encode(chunk).decode("ascii")}}))
                if dg_connection and i % 3200 == 0:
                    try:
                        dg_connection.send(b"\x7f" * 160)
                    except Exception:
                        pass
                time.sleep(0.02)
            except Exception as e:
                print(f"[send_audio] stopped: {e}")
                break
        print(f"[send_audio] complete: {len(audio_bytes)} bytes")
    t = threading.Thread(target=_send, daemon=True)
    t.start()
    return t


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _log_to_sheets(state, patient, appt, appt_status, lang, new_slot, topics, log_summary, final_sentiment):
    """Log interaction to Google Sheets via n8n webhook."""
    try:
        import aiohttp, asyncio as _asyncio
        from datetime import datetime, timezone
        payload = {
            "patient_name":         f"{patient.get('first_name','')} {patient.get('last_name','')}".strip() or "Unknown",
            "phone":                patient.get("phone", "unknown"),
            "authenticated":        state.get("is_authenticated", False),
            "appointment_status":   appt_status or "N/A",
            "new_slot":             new_slot or "",
            "language":             lang,
            "topics":               ", ".join(topics),
            "summary":              log_summary,
            "sentiment":            final_sentiment,
            "escalation_requested": state.get("escalation_requested", False),
            "emergency":            state.get("emergency_detected", False),
            "routing_path":         " -> ".join((state.get("routing_path") or [])[-10:]),
            "turn_count":           state.get("turn_count", 0),
            "timestamp":            datetime.now(timezone.utc).isoformat() + "Z",
            "call_start":           state.get("call_start_iso", ""),
        }
        n8n_base = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook")

        async def _post():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
                async with session.post(f"{n8n_base}/log-interaction", json=payload) as resp:
                    print(f"[log] Interaction logged -> Sheets: status {resp.status}")

        loop = _asyncio.new_event_loop()
        loop.run_until_complete(_post())
        loop.close()
    except Exception as e:
        print(f"[log] Error logging interaction: {e}")


@app.route("/incoming-call", methods=["POST"])
def incoming_call():
    ngrok_url = os.getenv("NGROK_VOICE_URL", "").rstrip("/")
    ws_url = ngrok_url.replace("https://", "wss://").replace("http://", "ws://") + "/media-stream"
    print(f"[incoming-call] {ws_url}")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}"/>
  </Connect>
</Response>"""
    return Response(twiml, mimetype="text/xml")


@sock.route("/media-stream")
def media_stream(ws):
    pipeline = MIRAVoicePipeline()
    stream_sid = None
    dg_connection = None
    speaking = False

    def on_transcript(self, result, **kwargs):
        nonlocal speaking, stream_sid
        if speaking:
            return
        sentence = result.channel.alternatives[0].transcript
        if not sentence or not result.is_final:
            return
        detected_lang = None
        try:
            detected_lang = getattr(result.channel, "detected_language", None)
            print(f"[STT/{detected_lang or 'en'}] {sentence}")
        except Exception:
            print(f"[STT] {sentence}")

        response_text = run_async(pipeline.on_utterance(sentence, detected_lang))
        if response_text and stream_sid:
            speaking = True
            audio = text_to_speech_mulaw(response_text)
            if audio:
                t = send_audio_threaded(ws, stream_sid, audio, dg_connection)
                t.join()
                # Wait for room echo to clear before accepting new speech
                time.sleep(0.4)
            speaking = False

            # Auto-hangup after farewell finishes playing
            if pipeline.is_ended:
                print("[stream] Call ended — hanging up after farewell")
                time.sleep(0.8)
                try:
                    ws.send(json.dumps({"event": "clear", "streamSid": stream_sid}))
                except Exception:
                    pass

    try:
        dg_client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        dg_connection = dg_client.listen.websocket.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        options = LiveOptions(model="nova-2", language="multi", smart_format=True,
                              numerals=True, interim_results=False, endpointing=1200,
                              encoding="mulaw", sample_rate=8000)
        dg_connection.start(options)
        print("[Deepgram] Connected — multilingual mode")

        # Keepalive thread — sends silent audio every 8s to prevent Deepgram timeout
        def _keepalive():
            while True:
                time.sleep(8)
                try:
                    if dg_connection:
                        dg_connection.send(b"\x7f" * 160)
                except Exception:
                    break
        threading.Thread(target=_keepalive, daemon=True).start()

    except Exception as e:
        print(f"[Deepgram error] {e}")
        return

    print("[Greeting] Generating...")
    greeting_audio = text_to_speech_mulaw(GREETING_TEXT)
    # Initialise pipeline state without calling LLM — greeting is hardcoded above
    # pipeline.greet() would call the LLM and generate a different greeting text
    run_async(pipeline.init_state())

    try:
        while True:
            message = ws.receive()
            if not message:
                break
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                print(f"[stream] started: {stream_sid}")
                time.sleep(0.3)
                if greeting_audio:
                    t = send_audio_threaded(ws, stream_sid, greeting_audio, dg_connection)
                    t.join()
                    print("[Greeting] Sent")
            elif event == "media":
                if dg_connection and not speaking:
                    try:
                        dg_connection.send(base64.b64decode(data["media"]["payload"]))
                    except Exception:
                        pass
            elif event == "stop":
                print("[stream] stopped")
                break

            if pipeline.is_ended:
                break

    except Exception as e:
        print(f"[stream error] {e}")
    finally:
        if dg_connection:
            dg_connection.finish()
        print("[stream] closed")

        state = pipeline.state
        is_auth           = state.get("is_authenticated", False)
        appt_communicated = state.get("appointment_communicated", False)

        patient = state.get("patient_record") or {}
        if isinstance(patient, str):
            try:
                import json as _j; patient = _j.loads(patient)
            except:
                patient = {}

        appt        = state.get("appointment_details") or {}
        appt_status = (appt.get("status") or patient.get("appointment_status") or "").lower().strip()
        first_name  = patient.get("first_name", "")
        lang        = state.get("preferred_language", "en")
        new_slot    = state.get("new_appointment_slot", "")
        topics      = state.get("call_topics") or []

        reschedule_note = f" Rescheduled to: {new_slot}." if new_slot else ""
        log_summary = (
            f"{first_name} {patient.get('last_name','')} called regarding their "
            f"appointment with {appt.get('doctor', patient.get('doctor_name','their doctor'))}. "
            f"Status: {appt_status or 'N/A'}.{reschedule_note}"
        ).strip()

        history = state.get("sentiment_history") or []
        if history:
            counts: dict = {}
            for s in history:
                counts[s] = counts.get(s, 0) + 1
            raw = max(counts, key=counts.get)
            final_sentiment = "negative" if raw in ("frustrated","angry") else ("positive" if raw == "positive" else "neutral")
        else:
            final_sentiment = "neutral"

        # Always log the interaction if call connected
        threading.Thread(
            target=_log_to_sheets,
            args=(state, patient, appt, appt_status, lang, new_slot, topics, log_summary, final_sentiment),
            daemon=True
        ).start()

        # Fire email only if appointment was communicated
        VALID_STATUSES = {"confirmed", "cancelled", "rescheduled", "pending"}
        if is_auth and appt_communicated and appt_status in VALID_STATUSES:
            to_email = patient.get("email", "") or os.getenv("DEMO_EMAIL", "")
            if to_email:
                def _send_email():
                    try:
                        from tools.email_sender import send_appointment_email_sync
                        email_appt = dict(appt)
                        if new_slot:
                            email_appt["date"] = new_slot
                            email_appt["time"] = ""
                        send_appointment_email_sync(
                            to_email=to_email, first_name=first_name,
                            appointment_status=appt_status, summary=log_summary,
                            appointment_details=email_appt, lang=lang,
                        )
                    except Exception as e:
                        print(f"[email] Error: {e}")
                threading.Thread(target=_send_email, daemon=True).start()
            else:
                print("[email] No DEMO_EMAIL — skipping")
        else:
            print(f"[email] Skipped — auth={is_auth} communicated={appt_communicated} status={appt_status!r}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    print(f"\n{'='*60}")
    print(f"  MIRA — Riverside Medical Centre  |  Voice Server :{port}")
    print(f"  Webhook: https://YOUR_CLOUDFLARE_URL/incoming-call")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
