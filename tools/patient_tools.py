"""
tools/patient_tools.py
Lookup patient via n8n → Google Sheets, with safe mock fallback.

Mock data covers 8 test scenarios:
  - Confirmed appointment (EN)
  - Pending appointment (EN)
  - Rescheduled appointment (EN)
  - Cancelled appointment (EN)
  - Wrong number / not found path
  - 2 Spanish-speaking patients (confirmed, pending)
  - Cardiology, Neurology, Dermatology, Oncology, Orthopaedics departments
"""

import os
import json
import aiohttp

N8N_BASE = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook")

# ── Mock patient data — used when n8n is unreachable ─────────────────────────
MOCK_PATIENTS = {
    # P001 — Confirmed appointment, English
    "4045550001": {
        "found": True,
        "patient_id": "P001",
        "phone": "4045550001",
        "first_name": "Sarah",
        "last_name": "Mitchell",
        "date_of_birth": "1985-03-12",
        "appointment_date": "April 15, 2026",
        "appointment_time": "10:30 AM",
        "doctor_name": "Dr. Sarah Chen",
        "department": "Cardiology",
        "appointment_status": "confirmed",
        "email": "",
    },
    # P002 — Pending appointment, English
    "4045550002": {
        "found": True,
        "patient_id": "P002",
        "phone": "4045550002",
        "first_name": "James",
        "last_name": "Thornton",
        "date_of_birth": "1972-07-28",
        "appointment_date": "April 18, 2026",
        "appointment_time": "2:00 PM",
        "doctor_name": "Dr. Michael Reyes",
        "department": "Neurology",
        "appointment_status": "pending",
        "email": "",
    },
    # P003 — Rescheduled appointment, English
    "4045550003": {
        "found": True,
        "patient_id": "P003",
        "phone": "4045550003",
        "first_name": "Emily",
        "last_name": "Patel",
        "date_of_birth": "1990-11-05",
        "appointment_date": "April 16, 2026",
        "appointment_time": "9:00 AM",
        "doctor_name": "Dr. James Liu",
        "department": "Dermatology",
        "appointment_status": "rescheduled",
        "email": "",
    },
    # P004 — Cancelled appointment, English
    "4045550004": {
        "found": True,
        "patient_id": "P004",
        "phone": "4045550004",
        "first_name": "Michael",
        "last_name": "Walsh",
        "date_of_birth": "1968-02-19",
        "appointment_date": "April 14, 2026",
        "appointment_time": "11:15 AM",
        "doctor_name": "Dr. Priya Sharma",
        "department": "Oncology",
        "appointment_status": "cancelled",
        "email": "",
    },
    # P005 — Confirmed appointment, English (Tampa area number)
    "8135550005": {
        "found": True,
        "patient_id": "P005",
        "phone": "8135550005",
        "first_name": "Diana",
        "last_name": "Foster",
        "date_of_birth": "1995-06-30",
        "appointment_date": "April 17, 2026",
        "appointment_time": "3:30 PM",
        "doctor_name": "Dr. Robert Kim",
        "department": "Orthopaedics",
        "appointment_status": "confirmed",
        "email": "",
    },
    # P006 — Pending appointment, English
    "8135550006": {
        "found": True,
        "patient_id": "P006",
        "phone": "8135550006",
        "first_name": "Robert",
        "last_name": "Nguyen",
        "date_of_birth": "1980-09-14",
        "appointment_date": "April 22, 2026",
        "appointment_time": "8:45 AM",
        "doctor_name": "Dr. Sarah Chen",
        "department": "Cardiology",
        "appointment_status": "pending",
        "email": "",
    },
    # P007 — Spanish speaker, confirmed appointment
    "8005550010": {
        "found": True,
        "patient_id": "P007",
        "phone": "8005550010",
        "first_name": "Maria",
        "last_name": "Gonzalez",
        "date_of_birth": "1978-04-22",
        "appointment_date": "April 15, 2026",
        "appointment_time": "1:00 PM",
        "doctor_name": "Dr. Elena Ramirez",
        "department": "Ginecología",
        "appointment_status": "confirmed",
        "email": "",
    },
    # P008 — Spanish speaker, rescheduled appointment
    "8005550011": {
        "found": True,
        "patient_id": "P008",
        "phone": "8005550011",
        "first_name": "Carlos",
        "last_name": "Mendoza",
        "date_of_birth": "1965-12-03",
        "appointment_date": "April 18, 2026",
        "appointment_time": "10:00 AM",
        "doctor_name": "Dr. Jorge Castillo",
        "department": "Cardiología",
        "appointment_status": "rescheduled",
        "email": "",
    },
}


async def lookup_patient_tool(phone: str) -> dict | None:
    """
    Looks up patient by phone number via n8n → Google Sheets.
    Falls back to mock data if n8n is unreachable.
    Always returns dict or None — never crashes.
    """
    clean = "".join(c for c in str(phone) if c.isdigit())
    if not clean:
        return None

    # Try n8n first
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=4)
        ) as session:
            async with session.post(
                f"{N8N_BASE}/lookup-patient",
                json={"phone": clean}
            ) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        # Handle both dict and list responses from n8n
                        if isinstance(data, list):
                            data = data[0] if data else {}
                        if isinstance(data, dict) and data.get("found"):
                            print(f"[tool] n8n lookup: found {data.get('first_name')}")
                            return data
                        else:
                            print(f"[tool] n8n lookup: not found for {clean}")
                            return None
                    except Exception as parse_err:
                        print(f"[tool] n8n response parse error: {parse_err}")
                        return None
                else:
                    print(f"[tool] n8n returned status {resp.status}, using mock")
    except Exception as e:
        print(f"[tool] n8n lookup failed ({type(e).__name__}), using mock")

    # Fallback to mock
    result = MOCK_PATIENTS.get(clean)
    if result:
        print(f"[tool] mock lookup: found {result.get('first_name')} ({result.get('appointment_status')})")
    else:
        print(f"[tool] mock lookup: not found for {clean}")
    return result


async def log_interaction_tool(payload: dict) -> bool:
    """
    Writes post-call record to Google Sheets via n8n.
    Never blocks — returns False on any error.
    """
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=6)
        ) as session:
            async with session.post(
                f"{N8N_BASE}/log-interaction",
                json=payload
            ) as resp:
                success = resp.status == 200
                print(f"[tool] interaction log: {'✓' if success else f'✗ status={resp.status}'}")
                return success
    except Exception as e:
        print(f"[tool] log_interaction failed: {e}")
        return False


# ── FAQ TOOL ──────────────────────────────────────────────────────────────────

_FAQ_CACHE: list[dict] | None = None


def _load_faq() -> list[dict]:
    global _FAQ_CACHE
    if _FAQ_CACHE is None:
        faq_path = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "faq.json")
        try:
            with open(faq_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _FAQ_CACHE = data.get("faqs", data) if isinstance(data, dict) else data
        except Exception:
            _FAQ_CACHE = []
    return _FAQ_CACHE


async def search_faq_tool(query: str) -> str | None:
    faqs = _load_faq()
    if not faqs or not query:
        return None
    q = query.lower()
    best_score = 0.0
    best_answer = None
    for item in faqs:
        keywords = item.get("keywords", [])
        question = item.get("question", "").lower()
        score = sum(1 for kw in keywords if kw.lower() in q)
        score += sum(1 for word in q.split() if word in question)
        if score > best_score:
            best_score = score
            best_answer = item.get("answer")
    return best_answer if best_score > 0.08 else None
