import gspread
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

COL_ID        = 1
COL_NAME      = 2
COL_PHONE     = 3
COL_SERVICE   = 4
COL_DATE      = 5
COL_TIME      = 6
COL_STATUS    = 7
COL_BOOKED_AT = 8
COL_CHAT_ID   = 9
COL_EVENT_ID  = 10

_sheet = None


def get_sheet():
    global _sheet
    if _sheet is None:
        google_creds = os.getenv("GOOGLE_CREDENTIALS")
        if google_creds:
            client = gspread.service_account_from_dict(json.loads(google_creds))
        else:
            client = gspread.service_account(filename="credentials.json")
        _sheet = client.open_by_key(SHEET_ID).sheet1
    return _sheet


def add_booking(name, phone, service, date, appt_time, chat_id, event_id=""):
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    next_row = len(all_rows) + 1
    existing_ids = [int(r[0]) for r in all_rows[1:] if r and r[0].isdigit()]
    new_id = max(existing_ids) + 1 if existing_ids else 1
    booked_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    sheet.update(
        f"A{next_row}:J{next_row}",
        [[new_id, name, phone, service, date, appt_time, "Confirmed", booked_at, str(chat_id), event_id]],
    )
    return new_id


def find_booking_by_phone(phone):
    """Return the most recent Confirmed booking for this phone, or None."""
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    result = None
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 7 and row[COL_PHONE - 1] == phone and row[COL_STATUS - 1] == "Confirmed":
            result = {
                "row": i,
                "id": row[COL_ID - 1],
                "name": row[COL_NAME - 1],
                "phone": row[COL_PHONE - 1],
                "service": row[COL_SERVICE - 1],
                "date": row[COL_DATE - 1],
                "time": row[COL_TIME - 1],
                "event_id": row[COL_EVENT_ID - 1] if len(row) >= COL_EVENT_ID else "",
            }
    return result


def find_any_booking_by_phone(phone):
    """Return the most recent booking (any status) for this phone, or None."""
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    result = None
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 7 and row[COL_PHONE - 1] == phone:
            result = {
                "row": i,
                "id": row[COL_ID - 1],
                "name": row[COL_NAME - 1],
                "phone": row[COL_PHONE - 1],
                "service": row[COL_SERVICE - 1],
                "date": row[COL_DATE - 1],
                "time": row[COL_TIME - 1],
                "status": row[COL_STATUS - 1],
                "event_id": row[COL_EVENT_ID - 1] if len(row) >= COL_EVENT_ID else "",
            }
    return result


def update_booking_schedule(row_num, new_date, new_time):
    sheet = get_sheet()
    # Also resets status to Confirmed so cancelled bookings can be reactivated
    sheet.update(f"E{row_num}:G{row_num}", [[new_date, new_time, "Confirmed"]])


def save_event_id(row_num, event_id):
    sheet = get_sheet()
    sheet.update_cell(row_num, COL_EVENT_ID, event_id)


def get_bookings_by_date(date_str):
    """Return all Confirmed bookings for a given date."""
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    result = []
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 7 and row[COL_DATE - 1] == date_str and row[COL_STATUS - 1] == "Confirmed":
            result.append({"row": i, "time": row[COL_TIME - 1]})
    return result


def cancel_booking_by_row(row_num):
    sheet = get_sheet()
    sheet.update_cell(row_num, COL_STATUS, "Cancelled")


def get_tomorrows_bookings():
    sheet = get_sheet()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    return [
        r for r in records
        if r.get("Date") == tomorrow and r.get("Status") == "Confirmed"
    ]
