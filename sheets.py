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

_DATE_FORMATS = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y"]


def _parse_date(cell_value):
    """Parse a date string from Google Sheets regardless of how it was stored."""
    s = str(cell_value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _dates_equal(cell_value, date_str):
    """Return True if cell_value represents the same date as date_str (DD/MM/YYYY)."""
    target = _parse_date(date_str)
    if target is None:
        return cell_value == date_str
    row_date = _parse_date(cell_value)
    if row_date is None:
        return False
    return row_date == target


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
        value_input_option="RAW",
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
    sheet.update(f"E{row_num}:G{row_num}", [[new_date, new_time, "Confirmed"]], value_input_option="RAW")


def save_event_id(row_num, event_id):
    sheet = get_sheet()
    sheet.update_cell(row_num, COL_EVENT_ID, event_id)


def get_bookings_by_date(date_str):
    """Return all Confirmed bookings for a given date."""
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    result = []
    for i, row in enumerate(all_rows[1:], start=2):
        if len(row) >= 7 and _dates_equal(row[COL_DATE - 1], date_str) and row[COL_STATUS - 1] == "Confirmed":
            result.append({"row": i, "time": row[COL_TIME - 1]})
    return result


def cancel_booking_by_row(row_num):
    sheet = get_sheet()
    sheet.update_cell(row_num, COL_STATUS, "Cancelled")


def get_tomorrows_bookings():
    sheet = get_sheet()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    all_rows = sheet.get_all_values()
    result = []
    for row in all_rows[1:]:
        if len(row) >= 9 and _dates_equal(row[COL_DATE - 1], tomorrow) and row[COL_STATUS - 1] == "Confirmed":
            result.append({
                "Name": row[COL_NAME - 1],
                "Phone": row[COL_PHONE - 1],
                "Service": row[COL_SERVICE - 1],
                "Date": row[COL_DATE - 1],
                "Time": row[COL_TIME - 1],
                "Chat_ID": row[COL_CHAT_ID - 1],
            })
    return result


def get_daily_report(date_str):
    """Return booking stats for a given date (DD/MM/YYYY)."""
    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    report_day = _parse_date(date_str)
    if report_day is None:
        return None
    today = datetime.now().date()
    total = confirmed = cancelled = 0
    for row in all_rows[1:]:
        if len(row) < 7 or not _dates_equal(row[COL_DATE - 1], date_str):
            continue
        total += 1
        status = row[COL_STATUS - 1]
        if status == "Confirmed":
            confirmed += 1
        elif status == "Cancelled":
            cancelled += 1
    completed = confirmed if report_day < today else 0
    not_yet = confirmed if report_day >= today else 0
    return {
        "date": date_str,
        "total": total,
        "cancelled": cancelled,
        "completed": completed,
        "not_yet": not_yet,
    }
