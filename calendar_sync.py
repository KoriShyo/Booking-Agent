import os
import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "visalsen72@gmail.com")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

_TIME_FORMATS = ["%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"]


def parse_time(time_str):
    """Parse a user-typed time string. Returns (hour, minute) or None if unparseable."""
    cleaned = time_str.strip().upper()
    for fmt in _TIME_FORMATS:
        try:
            t = datetime.strptime(cleaned, fmt)
            return t.hour, t.minute
        except ValueError:
            continue
    return None

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
    parsed = parse_time(appt_time)
    hour, minute = parsed if parsed else (9, 0)
    date_obj = datetime.strptime(date_str, "%d/%m/%Y")
    timezone = "Asia/Phnom_Penh"

    start = date_obj.replace(hour=hour, minute=minute)
    end   = start + timedelta(hours=1)

    return {
        "summary": f"🦷 {service} — {name}",
        "description": f"Patient: {name}\nPhone: {phone}\nService: {service}",
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": timezone},
        "end":   {"dateTime": end.strftime("%Y-%m-%dT%H:%M:00"),   "timeZone": timezone},
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
