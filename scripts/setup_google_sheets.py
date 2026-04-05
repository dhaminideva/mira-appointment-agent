"""
setup_google_sheets.py — MIRA
Creates and populates Google Sheets for Riverside Medical Centre:
  - Patients tab (replaces Callers): 8 test patients with appointment data
  - Interactions tab: post-call log with appointment_status column

Run once to set up the sheet, then configure n8n webhooks.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")


def get_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


# ── Test patient data ──────────────────────────────────────────────────────────
PATIENTS = [
    # Headers
    [
        "patient_id", "first_name", "last_name", "phone", "date_of_birth",
        "appointment_date", "appointment_time", "doctor_name", "department",
        "appointment_status", "email",
    ],
    # P001 — Confirmed, English, Cardiology
    ["P001", "Sarah",   "Mitchell", "4045550001", "1985-03-12",
     "April 15, 2026", "10:30 AM", "Dr. Sarah Chen",     "Cardiology",    "confirmed",    ""],
    # P002 — Pending, English, Neurology
    ["P002", "James",   "Thornton", "4045550002", "1972-07-28",
     "April 18, 2026", "2:00 PM",  "Dr. Michael Reyes",  "Neurology",     "pending",      ""],
    # P003 — Rescheduled, English, Dermatology
    ["P003", "Emily",   "Patel",    "4045550003", "1990-11-05",
     "April 16, 2026", "9:00 AM",  "Dr. James Liu",      "Dermatology",   "rescheduled",  ""],
    # P004 — Cancelled, English, Oncology
    ["P004", "Michael", "Walsh",    "4045550004", "1968-02-19",
     "April 14, 2026", "11:15 AM", "Dr. Priya Sharma",   "Oncology",      "cancelled",    ""],
    # P005 — Confirmed, English, Orthopaedics
    ["P005", "Diana",   "Foster",   "8135550005", "1995-06-30",
     "April 17, 2026", "3:30 PM",  "Dr. Robert Kim",     "Orthopaedics",  "confirmed",    ""],
    # P006 — Pending, English, Cardiology
    ["P006", "Robert",  "Nguyen",   "8135550006", "1980-09-14",
     "April 22, 2026", "8:45 AM",  "Dr. Sarah Chen",     "Cardiology",    "pending",      ""],
    # P007 — Spanish speaker, Confirmed
    ["P007", "Maria",   "Gonzalez", "8005550010", "1978-04-22",
     "April 15, 2026", "1:00 PM",  "Dr. Elena Ramirez",  "Ginecología",   "confirmed",    ""],
    # P008 — Spanish speaker, Rescheduled
    ["P008", "Carlos",  "Mendoza",  "8005550011", "1965-12-03",
     "April 18, 2026", "10:00 AM", "Dr. Jorge Castillo", "Cardiología",   "rescheduled",  ""],
]

# ── Interactions tab headers ───────────────────────────────────────────────────
INTERACTIONS_HEADERS = [[
    "timestamp", "patient_name", "phone", "authenticated", "appointment_status",
    "new_slot", "language", "topics", "summary", "sentiment",
    "escalation_requested", "emergency", "routing_path", "turn_count", "call_start",
]]


def setup_sheets():
    gc = get_client()

    if not SPREADSHEET_ID:
        print("[setup] No GOOGLE_SPREADSHEET_ID in .env — creating new spreadsheet...")
        sh = gc.create("MIRA — Riverside Medical Centre")
        print(f"[setup] Created: {sh.url}")
        print(f"[setup] Add this to .env: GOOGLE_SPREADSHEET_ID={sh.id}")
    else:
        sh = gc.open_by_key(SPREADSHEET_ID)
        print(f"[setup] Opened: {sh.url}")

    # ── Patients tab ──────────────────────────────────────────────────────
    try:
        patients_ws = sh.worksheet("Patients")
        patients_ws.clear()
        print("[setup] Cleared existing Patients tab")
    except gspread.exceptions.WorksheetNotFound:
        patients_ws = sh.add_worksheet(title="Patients", rows=100, cols=15)
        print("[setup] Created Patients tab")

    patients_ws.update("A1", PATIENTS)
    # Bold header row
    patients_ws.format("A1:K1", {"textFormat": {"bold": True}})
    print(f"[setup] ✓ Patients tab — {len(PATIENTS)-1} test records written")

    # ── Interactions tab ──────────────────────────────────────────────────
    try:
        interactions_ws = sh.worksheet("Interactions")
        # Only clear if empty
        existing = interactions_ws.get_all_values()
        if not existing or existing == [[]]:
            interactions_ws.update("A1", INTERACTIONS_HEADERS)
            print("[setup] ✓ Interactions tab — headers written")
        else:
            print(f"[setup] ✓ Interactions tab — already has {len(existing)-1} records, leaving intact")
    except gspread.exceptions.WorksheetNotFound:
        interactions_ws = sh.add_worksheet(title="Interactions", rows=1000, cols=20)
        interactions_ws.update("A1", INTERACTIONS_HEADERS)
        interactions_ws.format("A1:O1", {"textFormat": {"bold": True}})
        print("[setup] ✓ Interactions tab — created with headers")

    print("\n[setup] ✅ Google Sheets setup complete")
    print(f"[setup] 🔗 {sh.url}")
    print("\nNext steps:")
    print("  1. Share the sheet with your service account email")
    print("  2. Add GOOGLE_SPREADSHEET_ID to .env")
    print("  3. Configure n8n webhook /lookup-patient → Patients tab (match by phone)")
    print("  4. Configure n8n webhook /log-interaction → Interactions tab (append row)")


if __name__ == "__main__":
    setup_sheets()
