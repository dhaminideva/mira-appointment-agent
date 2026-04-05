from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(".env")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
gc = gspread.authorize(creds)

spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
sh = gc.open_by_key(spreadsheet_id)
print("Opened:", sh.title)

# Patients tab
try:
    ws = sh.worksheet("Patients")
    ws.clear()
except:
    ws = sh.add_worksheet(title="Patients", rows=100, cols=15)

ws.update("A1", [[
    "patient_id","first_name","last_name","phone","date_of_birth",
    "appointment_date","appointment_time","doctor_name","department",
    "appointment_status","email"
],[
    "P001","Sarah","Mitchell","4045550001","1985-03-12","April 15, 2026","10:30 AM","Dr. Sarah Chen","Cardiology","confirmed",""
],[
    "P002","James","Thornton","4045550002","1972-07-28","April 18, 2026","2:00 PM","Dr. Michael Reyes","Neurology","pending",""
],[
    "P003","Emily","Patel","4045550003","1990-11-05","April 16, 2026","9:00 AM","Dr. James Liu","Dermatology","rescheduled",""
],[
    "P004","Michael","Walsh","4045550004","1968-02-19","April 14, 2026","11:15 AM","Dr. Priya Sharma","Oncology","cancelled",""
],[
    "P005","Diana","Foster","8135550005","1995-06-30","April 17, 2026","3:30 PM","Dr. Robert Kim","Orthopaedics","confirmed",""
],[
    "P006","Robert","Nguyen","8135550006","1980-09-14","April 22, 2026","8:45 AM","Dr. Sarah Chen","Cardiology","pending",""
],[
    "P007","Maria","Gonzalez","8005550010","1978-04-22","April 15, 2026","1:00 PM","Dr. Elena Ramirez","Ginecologia","confirmed",""
],[
    "P008","Carlos","Mendoza","8005550011","1965-12-03","April 18, 2026","10:00 AM","Dr. Jorge Castillo","Cardiologia","rescheduled",""
]])
print("Patients tab done - 8 records")

# Interactions tab
try:
    wi = sh.worksheet("Interactions")
except:
    wi = sh.add_worksheet(title="Interactions", rows=1000, cols=20)

wi.update("A1", [[
    "timestamp","patient_name","phone","authenticated","appointment_status",
    "new_slot","language","topics","summary","sentiment",
    "escalation_requested","emergency","routing_path","turn_count","call_start"
]])
print("Interactions tab done")
print("Setup complete:", sh.url)