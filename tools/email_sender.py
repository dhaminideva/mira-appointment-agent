"""
tools/email_sender.py
Sends post-call appointment summary email via SendGrid.
Uses requests (not httpx) to avoid SSL threading issues on Windows.

Templates:
  confirmed   — green header, appointment details, arrive 10 min early
  cancelled   — neutral header, offer to rebook, contact number
  rescheduled — teal header, new appointment details
  pending     — amber header, confirmation pending, what to expect
"""

import os
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("SENDGRID_FROM_EMAIL", "")
FROM_NAME        = os.getenv("SENDGRID_FROM_NAME", "MIRA - Riverside Medical Centre")
CLINIC_NAME      = os.getenv("CLINIC_NAME", "Riverside Medical Centre")
CLINIC_PHONE     = os.getenv("CLINIC_PHONE", "1-800-555-0200")
CLINIC_PORTAL    = os.getenv("CLINIC_PORTAL", "portal.riversidemedical.com")


STATUS_CONTENT = {
    "confirmed": {
        "subject": "Your Appointment is Confirmed — Riverside Medical Centre",
        "headline": "Appointment Confirmed",
        "color": "#2d6a4f",        # green
        "icon": "✅",
        "body": (
            "Your appointment has been <strong>confirmed</strong>. "
            "We look forward to seeing you. "
            "Please remember to <strong>arrive 10 minutes early</strong> to allow time for check-in."
        ),
        "next_steps": [
            "Arrive 10 minutes before your scheduled time",
            "Bring a valid photo ID and your insurance card",
            "If you need to reschedule, please call us at least 24 hours in advance",
            f"Contact us at <strong>{CLINIC_PHONE}</strong> with any questions",
        ],
    },
    "cancelled": {
        "subject": "Your Appointment Has Been Cancelled — Riverside Medical Centre",
        "headline": "Appointment Cancelled",
        "color": "#6c757d",        # neutral grey
        "icon": "📋",
        "body": (
            "Your appointment has been <strong>cancelled</strong> as requested. "
            "We hope to see you again soon. "
            "If you would like to rebook, our team is happy to find a time that works for you."
        ),
        "next_steps": [
            f"Call us at <strong>{CLINIC_PHONE}</strong> to rebook at any time",
            f"Book online at <a href='https://{CLINIC_PORTAL}' style='color:#1a73e8;'>{CLINIC_PORTAL}</a>",
            "Mon–Fri 8:00 AM – 6:00 PM",
        ],
    },
    "rescheduled": {
        "subject": "Your Appointment Has Been Rescheduled — Riverside Medical Centre",
        "headline": "Appointment Rescheduled",
        "color": "#0d7377",        # teal
        "icon": "🗓️",
        "body": (
            "Your appointment has been <strong>rescheduled</strong> to your new preferred time. "
            "Your updated appointment details are shown below. "
            "Please remember to <strong>arrive 10 minutes early</strong> for check-in."
        ),
        "next_steps": [
            "Arrive 10 minutes before your new appointment time",
            "Bring a valid photo ID and your insurance card",
            f"Need to change again? Call us at <strong>{CLINIC_PHONE}</strong>",
            f"Manage your appointments at <a href='https://{CLINIC_PORTAL}' style='color:#1a73e8;'>{CLINIC_PORTAL}</a>",
        ],
    },
    "pending": {
        "subject": "Your Appointment Request Is Pending — Riverside Medical Centre",
        "headline": "Appointment Pending Confirmation",
        "color": "#e9a825",        # amber
        "icon": "⏳",
        "body": (
            "Your appointment request is currently <strong>pending confirmation</strong>. "
            "Our scheduling team is reviewing availability and will confirm your slot shortly. "
            "You will receive a text message as soon as your appointment is confirmed."
        ),
        "next_steps": [
            "Watch for a confirmation text message from us",
            "No action is required from you at this time",
            f"Questions? Call us at <strong>{CLINIC_PHONE}</strong>",
            f"Check your appointment status at <a href='https://{CLINIC_PORTAL}' style='color:#1a73e8;'>{CLINIC_PORTAL}</a>",
        ],
    },
}


def build_email_html(
    first_name: str,
    appointment_status: str,
    summary: str,
    appointment_details: dict | None = None,
    lang: str = "en",
) -> str:
    status_key = appointment_status.lower().strip()
    content = STATUS_CONTENT.get(status_key, STATUS_CONTENT["pending"])
    appt = appointment_details or {}

    next_steps_html = "".join(
        f"<li style='margin-bottom:8px;color:#444;'>{step}</li>"
        for step in content["next_steps"]
    )

    # Appointment detail block (if we have data)
    appt_block = ""
    if appt.get("date") or appt.get("doctor"):
        rows = []
        if appt.get("doctor"):
            rows.append(f"<tr><td style='color:#666;padding:4px 0;width:120px;'>Doctor</td><td style='color:#222;font-weight:600;'>{appt['doctor']}</td></tr>")
        if appt.get("department"):
            rows.append(f"<tr><td style='color:#666;padding:4px 0;'>Department</td><td style='color:#222;font-weight:600;'>{appt['department']}</td></tr>")
        if appt.get("date"):
            rows.append(f"<tr><td style='color:#666;padding:4px 0;'>Date</td><td style='color:#222;font-weight:600;'>{appt['date']}</td></tr>")
        if appt.get("time"):
            rows.append(f"<tr><td style='color:#666;padding:4px 0;'>Time</td><td style='color:#222;font-weight:600;'>{appt['time']}</td></tr>")
        if rows:
            appt_block = f"""
            <p style='margin:0 0 12px;font-size:14px;font-weight:600;color:#222;'>Appointment Details</p>
            <div style='background:#f8f9fa;border-radius:6px;padding:16px 20px;margin-bottom:28px;border-left:4px solid {content["color"]};'>
              <table style='border-collapse:collapse;width:100%;font-size:14px;'>
                {''.join(rows)}
              </table>
            </div>"""

    bilingual_note = ""
    if lang == "es":
        bilingual_note = f"""
        <p style='font-size:13px;color:#666;border-left:3px solid #ddd;padding-left:12px;margin-top:16px;'>
        <em>Este correo está en inglés. Para asistencia en español, llame al {CLINIC_PHONE}.</em>
        </p>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#1a3c5e;padding:28px 40px;">
            <p style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:0.5px;">{CLINIC_NAME}</p>
            <p style="margin:4px 0 0;color:#a0c4e0;font-size:13px;">Appointment Summary — Sent by MIRA, your AI Appointment Assistant</p>
          </td>
        </tr>
        <tr>
          <td style="background:{content['color']};padding:16px 40px;">
            <p style="margin:0;color:#ffffff;font-size:16px;font-weight:600;">{content['icon']} &nbsp; {content['headline']}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px 24px;">
            <p style="margin:0 0 20px;font-size:16px;color:#222;">Hi {first_name},</p>
            <p style="margin:0 0 24px;font-size:15px;color:#444;line-height:1.6;">
              Thank you for speaking with MIRA today. Here's a summary of your call and your appointment details.
            </p>
            <div style="background:#f8f9fa;border-radius:6px;padding:20px 24px;margin-bottom:28px;border-left:4px solid {content['color']};">
              <p style="margin:0;font-size:14px;color:#555;line-height:1.7;">{content['body']}</p>
            </div>
            {appt_block}
            <p style="margin:0 0 12px;font-size:14px;font-weight:600;color:#222;">Call Summary</p>
            <div style="background:#f0f4ff;border-radius:6px;padding:16px 20px;margin-bottom:28px;">
              <p style="margin:0;font-size:13px;color:#555;line-height:1.6;font-style:italic;">{summary}</p>
            </div>
            <p style="margin:0 0 12px;font-size:14px;font-weight:600;color:#222;">Next Steps</p>
            <ul style="margin:0 0 28px;padding-left:20px;line-height:1.8;font-size:14px;">{next_steps_html}</ul>
            {bilingual_note}
            <hr style="border:none;border-top:1px solid #eee;margin:28px 0;">
            <p style="margin:0;font-size:13px;color:#666;line-height:1.6;">
              Questions? Our team is here to help.<br>
              📞 <strong>{CLINIC_PHONE}</strong> &nbsp;|&nbsp; Mon–Fri 8:00 AM – 6:00 PM<br>
              🌐 <a href="https://{CLINIC_PORTAL}" style="color:#1a73e8;">{CLINIC_PORTAL}</a>
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#eef3f8;padding:20px 40px;">
            <p style="margin:0;font-size:12px;color:#888;line-height:1.5;">
              This email was sent automatically following your call with MIRA, the AI Appointment Assistant for {CLINIC_NAME}.<br>
              © 2026 {CLINIC_NAME}. All rights reserved.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_appointment_email_sync(
    to_email: str,
    first_name: str,
    appointment_status: str,
    summary: str,
    appointment_details: dict | None = None,
    lang: str = "en",
) -> bool:
    """
    Synchronous version using requests — safe for Flask threads on Windows.
    Called from a background thread in twilio_server.py finally block.
    """
    if not SENDGRID_API_KEY or not FROM_EMAIL:
        print("[email] SendGrid not configured — check .env")
        return False

    if not to_email or "@" not in to_email:
        print(f"[email] Invalid email: {to_email}")
        return False

    status_key = appointment_status.lower().strip()
    if status_key not in STATUS_CONTENT:
        print(f"[email] Unknown appointment status: {status_key!r} — skipping email")
        return False

    content = STATUS_CONTENT[status_key]
    html_body = build_email_html(first_name, appointment_status, summary, appointment_details, lang)

    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": first_name}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": content["subject"],
        "content": [{"type": "text/html", "value": html_body}],
    }

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
            verify=False,   # Required for Windows SSL threading
        )
        if resp.status_code == 202:
            print(f"[email] ✓ Sent to {to_email} | {content['subject'][:50]}")
            return True
        else:
            print(f"[email] ✗ Failed {resp.status_code}: {resp.text[:150]}")
            return False
    except Exception as e:
        print(f"[email] ✗ Error: {e}")
        return False


# Async wrapper for compatibility
async def send_appointment_email(
    to_email: str,
    first_name: str,
    appointment_status: str,
    summary: str,
    appointment_details: dict | None = None,
    lang: str = "en",
) -> bool:
    return send_appointment_email_sync(
        to_email, first_name, appointment_status, summary, appointment_details, lang
    )
