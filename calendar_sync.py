import os
import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "visalsen72@gmail.com")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

TIME_SLOTS = {
    # English
    "Morning":   ("09:00", "10:00"),
    "Afternoon": ("14:00", "15:00"),
    # Khmer
    "ព្រឹក":     ("09:00", "10:00"),
    "រសៀល":     ("14:00", "15:00"),
}

_service = None


def _get_service():
    global _service
    if _service is None:
        google_creds = os.getenv("GOOGLE_CREDENTIALS")
        if google_creds:
            creds_info = json.loads(google_creds)
        else:
            with open("credentials.json") as f:
                creds_info = json.load(f)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        _service = build("calendar", "v3", credentials=creds)
    return _service


def _build_event_body(name, phone, service, date_str, appt_time):
    start_time, end_time = TIME_SLOTS.get(appt_time, ("09:00", "10:00"))
    # date_str is DD/MM/YYYY
    date_obj = datetime.strptime(date_str, "%d/%m/%Y")
    timezone = "Asia/Phnom_Penh"

    start_dt = f"{date_obj.strftime('%Y-%m-%d')}T{start_time}:00"
    end_dt   = f"{date_obj.strftime('%Y-%m-%d')}T{end_time}:00"

    return {
        "summary": f"🦷 {service} — {name}",
        "description": f"Patient: {name}\nPhone: {phone}\nService: {service}",
        "start": {"dateTime": start_dt, "timeZone": timezone},
        "end":   {"dateTime": end_dt,   "timeZone": timezone},
    }


def create_calendar_event(name, phone, service, date_str, appt_time):
    body = _build_event_body(name, phone, service, date_str, appt_time)
    event = _get_service().events().insert(calendarId=CALENDAR_ID, body=body).execute()
    return event["id"]


def update_calendar_event(event_id, name, phone, service, new_date, new_time):
    body = _build_event_body(name, phone, service, new_date, new_time)
    _get_service().events().update(calendarId=CALENDAR_ID, eventId=event_id, body=body).execute()


def delete_calendar_event(event_id):
    _get_service().events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
