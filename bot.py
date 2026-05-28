import os
import re
import traceback
import asyncio
import html as html_lib
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, MessageHandler, CommandHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler, PicklePersistence,
)
from sheets import add_booking, find_booking_by_phone, find_any_booking_by_phone, update_booking_schedule, save_event_id, cancel_booking_by_row, get_bookings_by_date, get_tomorrows_bookings, get_report_range
from calendar_sync import create_calendar_event, update_calendar_event, delete_calendar_event, parse_time
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

assert TELEGRAM_BOT_TOKEN, "TELEGRAM_BOT_TOKEN is not set in .env"
assert OWNER_CHAT_ID, "OWNER_CHAT_ID is not set in .env"

# Booking states
LANGUAGE, NAME, PHONE, SERVICE, DATE, TIME = range(6)
# Location state
STORE_SELECT = 6
# Change schedule states
CHANGE_PHONE, CHANGE_DATE, CHANGE_TIME = range(7, 10)
# Cancel appointment states
CANCEL_PHONE, CANCEL_CONFIRM = range(10, 12)
# Report states
REPORT_DATE, REPORT_INPUT = 12, 13

TEXTS = {
    "en": {
        "welcome": "Great! What is your full name?",
        "ask_phone": "What is your phone number?",
        "invalid_phone": "Please enter a valid phone number (digits only).",
        "ask_service": "What service do you need?",
        "ask_date": "What date do you prefer?\nFormat: 25/05/2026",
        "invalid_date": "Invalid date. Please use the format: 25/05/2026",
        "past_date": "You cannot book a past date. Please choose a future date.",
        "ask_time": "What time do you prefer?\nFormat: 9:30 AM or 14:00",
        "invalid_time": "Invalid time. Please use a format like 9:30 AM or 14:00",
        "time_conflict": "⚠️ Sorry, our dentist is already booked at that hour. Please choose a different time.",
        "confirmed": (
            "✅ Your appointment is confirmed!\n\n"
            "Name: {name}\nPhone: {phone}\nService: {service}\n"
            "Date: {date}\nTime: {time}\n\n"
            "We will remind you the day before. See you soon!"
        ),
        "error": "Sorry, something went wrong. Please try again.",
        "cancelled": "Booking cancelled.",
        "choose_store": "Please choose a branch:",
        "services": [["Checkup", "Cleaning"], ["Toothache", "Filling"], ["Whitening", "Other"]],
        "times": [["Morning", "Afternoon"]],
        "ask_phone_lookup": "Please enter your registered phone number:",
        "booking_not_found": "❌ No confirmed booking found for that phone number.",
        "change_not_found": "❌ We couldn't find an appointment for that number. Please use 📅 Book Appointment to make a new booking.",
        "change_found": (
            "Found your booking:\n\n"
            "Service: {service}\nDate: {date}\nTime: {time}\n\n"
            "What new date would you like? (e.g. 25/05/2026)"
        ),
        "schedule_updated": (
            "✅ Your appointment has been rescheduled!\n\n"
            "Service: {service}\nNew Date: {date}\nNew Time: {time}"
        ),
        "cancel_appt_found": (
            "Found your booking:\n\n"
            "Service: {service}\nDate: {date}\nTime: {time}\n\n"
            "Are you sure you want to cancel?"
        ),
        "yes_no": [["✅ Yes, cancel it", "❌ No, keep it"]],
        "appointment_cancelled": "✅ Your appointment has been cancelled. We hope to see you another time!",
        "cancel_aborted": "Your appointment is kept. See you soon! 😊",
        "phone_already_booked": (
            "⚠️ This phone number already has a confirmed booking:\n\n"
            "Service: {service}\nDate: {date}\nTime: {time}\n\n"
            "Please use 🔄 Change Schedule to modify it."
        ),
        "reminder": (
            "⏰ Reminder: You have an appointment tomorrow!\n\n"
            "Service: {service}\nTime: {time}\n\n"
            "See you soon! 🦷"
        ),
        "branch_not_found": "Branch not found.",
        "already_cancelled": "❌ This appointment is already cancelled. Please use 📅 Book Appointment to make a new booking.",
        "owner_blocked": "⛔ Owner accounts cannot make bookings. You receive patient notifications automatically.",
    },
    "kh": {
        "welcome": "អស្ចារ្យណាស់! តើឈ្មោះពេញរបស់អ្នកជាអ្វី?",
        "ask_phone": "តើលេខទូរស័ព្ទរបស់អ្នកជាអ្វី?",
        "invalid_phone": "សូមបញ្ចូលលេខទូរស័ព្ទត្រឹមត្រូវ (លេខគ្រាន់តែប៉ុណ្ណោះ)។",
        "ask_service": "តើអ្នកត្រូវការសេវាអ្វី?",
        "ask_date": "តើអ្នកចង់ណាត់ជួបថ្ងៃណា?\nទម្រង់: 25/05/2026",
        "invalid_date": "កាលបរិច្ឆេទមិនត្រឹមត្រូវ។ សូមប្រើទម្រង់: 25/05/2026",
        "past_date": "អ្នកមិនអាចណាត់ជួបកាលបរិច្ឆេទដែលបានកន្លងផុតទេ។ សូមជ្រើសរើសថ្ងៃអនាគត។",
        "ask_time": "តើអ្នកចង់ណាត់ម៉ោងណា?\nទម្រង់: 9:30 AM ឬ 14:00",
        "invalid_time": "ម៉ោងមិនត្រឹមត្រូវ។ សូមប្រើទម្រង់ដូចជា 9:30 AM ឬ 14:00",
        "time_conflict": "⚠️ សូមអភ័យទោស! គ្រូពេទ្យធ្មេញរបស់យើងត្រូវបានកក់ហើយក្នុងម៉ោងនោះ។ សូមជ្រើសរើសម៉ោងផ្សេង។",
        "confirmed": (
            "✅ ការណាត់ជួបរបស់អ្នកត្រូវបានបញ្ជាក់!\n\n"
            "ឈ្មោះ: {name}\nទូរស័ព្ទ: {phone}\nសេវា: {service}\n"
            "កាលបរិច្ឆេទ: {date}\nម៉ោង: {time}\n\n"
            "យើងនឹងរំលឹកអ្នកមួយថ្ងៃមុន។ ជួបគ្នាឆាប់ៗ!"
        ),
        "error": "សូមអភ័យទោស! មានបញ្ហាកើតឡើង។ សូមព្យាយាមម្តងទៀត។",
        "cancelled": "ការកក់ត្រូវបានបោះបង់។",
        "choose_store": "សូមជ្រើសរើសសាខា:",
        "services": [["ពិនិត្យធ្មេញ", "សម្អាតធ្មេញ"], ["ឈឺធ្មេញ", "បំពេញធ្មេញ"], ["ធ្វើឱ្យធ្មេញស", "ផ្សេងៗ"]],
        "times": [["ព្រឹក", "រសៀល"]],
        "ask_phone_lookup": "សូមបញ្ចូលលេខទូរស័ព្ទដែលបានចុះឈ្មោះ:",
        "booking_not_found": "❌ រកមិនឃើញការណាត់ជួបសម្រាប់លេខទូរស័ព្ទនេះ។",
        "change_not_found": "❌ រកមិនឃើញការណាត់ជួបសម្រាប់លេខទូរស័ព្ទនេះ។ សូមប្រើ 📅 ធ្វើការកក់ ដើម្បីណាត់ជួបថ្មី។",
        "change_found": (
            "យើងបានរកឃើញការណាត់ជួបរបស់អ្នក:\n\n"
            "សេវា: {service}\nកាលបរិច្ឆេទ: {date}\nម៉ោង: {time}\n\n"
            "តើអ្នកចង់ប្ដូរទៅថ្ងៃណា? (ឧទាហរណ៍: 25/05/2026)"
        ),
        "schedule_updated": (
            "✅ ការណាត់ជួបរបស់អ្នកត្រូវបានផ្លាស់ប្ដូររួចរាល់!\n\n"
            "សេវា: {service}\nកាលបរិច្ឆេទថ្មី: {date}\nម៉ោងថ្មី: {time}"
        ),
        "cancel_appt_found": (
            "យើងបានរកឃើញការណាត់ជួបរបស់អ្នក:\n\n"
            "សេវា: {service}\nកាលបរិច្ឆេទ: {date}\nម៉ោង: {time}\n\n"
            "តើអ្នកប្រាកដចង់លប់បង់ការណាត់ជួបនេះ?"
        ),
        "yes_no": [["✅ បាទ លប់ចោល", "❌ ទេ រក្សាទុក"]],
        "appointment_cancelled": "✅ ការណាត់ជួបរបស់អ្នកត្រូវបានលប់ចោល។ យើងសង្ឃឹមថានឹងបានជួបអ្នកនៅពេលក្រោយ!",
        "cancel_aborted": "ការណាត់ជួបរបស់អ្នកត្រូវបានរក្សាទុក។ ជួបគ្នាឆាប់ៗ! 😊",
        "phone_already_booked": (
            "⚠️ លេខទូរស័ព្ទនេះមានការណាត់ជួបដែលបានបញ្ជាក់រួចហើយ:\n\n"
            "សេវា: {service}\nកាលបរិច្ឆេទ: {date}\nម៉ោង: {time}\n\n"
            "សូមប្រើ 🔄 ប្ដូរកាលវិភាគ ដើម្បីកែប្រែ។"
        ),
        "reminder": (
            "⏰ រំលឹក: អ្នកមានការណាត់ជួបស្អែក!\n\n"
            "សេវា: {service}\nម៉ោង: {time}\n\n"
            "ជួបគ្នាឆាប់ៗ! 🦷"
        ),
        "branch_not_found": "រកមិនឃើញសាខា។",
        "already_cancelled": "❌ ការណាត់ជួបនេះត្រូវបានលប់ចោលរួចហើយ។ សូមប្រើ 📅 ធ្វើការកក់ ដើម្បីណាត់ជួបថ្មី។",
        "owner_blocked": "⛔ គណនីម្ចាស់មិនអាចធ្វើការកក់បានទេ។ អ្នកទទួលការជូនដំណឹងពីអ្នកជំងឺដោយស្វ័យប្រវត្តិ។",
    },
}

STORES = {
    "🏥 Branch 1 - Main": {
        "lat": 11.5564,
        "lon": 104.9282,
        "address": "123 Main Street, Phnom Penh",
    },
    "🏥 Branch 2 - North": {
        "lat": 11.5800,
        "lon": 104.9100,
        "address": "456 North Avenue, Phnom Penh",
    },
}

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📅 Book Appointment", "📍 Location"],
        ["🔄 Change Schedule", "❌ Cancel Appointment"],
        ["📊 Daily Report"],
    ],
    resize_keyboard=True,
)

OWNER_MENU = ReplyKeyboardMarkup(
    [["📊 Daily Report"]],
    resize_keyboard=True,
)


def t(context, key):
    lang = context.user_data.get("lang", "en")
    return TEXTS[lang][key]


def _is_owner(update: Update) -> bool:
    return str(update.effective_chat.id) == str(OWNER_CHAT_ID)


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_owner(update):
        await update.message.reply_text("👨‍⚕️ Owner panel. You will receive all booking notifications.", reply_markup=OWNER_MENU)
        return ConversationHandler.END
    lang = context.user_data.get("lang", "en")
    greeting = (
        "Welcome to our dental clinic! 🦷\nHow can I help you?"
        if lang == "en"
        else "សូមស្វាគមន៍មកកាន់គ្លីនិកធ្មេញរបស់យើង! 🦷\nតើខ្ញុំអាចជួយអ្នកដោយរបៀបណា?"
    )
    await update.message.reply_text(greeting, reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Booking conversation ──────────────────────────────────────────────────────

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_owner(update):
        lang = context.user_data.get("lang", "en")
        await update.message.reply_text(TEXTS[lang]["owner_blocked"], reply_markup=OWNER_MENU)
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "Please choose your language / សូមជ្រើសរើសភាសា:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton("🇰🇭 Khmer",   callback_data="lang:kh"),
        ]]),
    )
    return LANGUAGE


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["lang"] = query.data.split(":")[1]
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(t(context, "welcome"), reply_markup=ReplyKeyboardRemove())
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(t(context, "ask_phone"), reply_markup=ReplyKeyboardRemove())
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.lstrip("+").isdigit():
        await update.message.reply_text(t(context, "invalid_phone"))
        return PHONE

    existing = find_booking_by_phone(phone)
    if existing:
        await update.message.reply_text(
            t(context, "phone_already_booked").format(
                service=existing["service"], date=existing["date"], time=existing["time"]
            ),
            reply_markup=MAIN_MENU,
        )
        return ConversationHandler.END

    context.user_data["phone"] = phone
    lang = context.user_data.get("lang", "en")
    en_services = ["Checkup", "Cleaning", "Toothache", "Filling", "Whitening", "Other"]
    display = [item for row in TEXTS[lang]["services"] for item in row]
    rows = [
        [InlineKeyboardButton(display[i], callback_data=f"svc:{en_services[i]}"),
         InlineKeyboardButton(display[i+1], callback_data=f"svc:{en_services[i+1]}")]
        for i in range(0, len(display), 2)
    ]
    await update.message.reply_text(
        t(context, "ask_service"),
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return SERVICE


async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["service"] = query.data.split(":", 1)[1]
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(t(context, "ask_date"), reply_markup=ReplyKeyboardRemove())
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        parsed = datetime.strptime(date_text, "%d/%m/%Y").date()
    except ValueError:
        await update.message.reply_text(t(context, "invalid_date"))
        return DATE

    if parsed < datetime.now().date():
        await update.message.reply_text(t(context, "past_date"))
        return DATE

    context.user_data["date"] = date_text
    await update.message.reply_text(
        t(context, "ask_time"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return TIME


def _slot_conflicts(new_time_str, existing_bookings, exclude_row=None):
    """Return True if new_time_str overlaps any confirmed booking (1-hour slots)."""
    new = parse_time(new_time_str)
    if not new:
        return False
    new_start = new[0] * 60 + new[1]
    new_end   = new_start + 60
    for b in existing_bookings:
        if exclude_row and b["row"] == exclude_row:
            continue
        existing = parse_time(b["time"])
        if not existing:
            continue
        ex_start = existing[0] * 60 + existing[1]
        ex_end   = ex_start + 60
        if new_start < ex_end and new_end > ex_start:
            return True
    return False


async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appt_time = update.message.text.strip()
    if parse_time(appt_time) is None:
        await update.message.reply_text(t(context, "invalid_time"))
        return TIME
    date = context.user_data["date"]
    if _slot_conflicts(appt_time, get_bookings_by_date(date)):
        await update.message.reply_text(t(context, "time_conflict"))
        return TIME
    name = context.user_data["name"]
    phone = context.user_data["phone"]
    service = context.user_data["service"]
    date = context.user_data["date"]
    chat_id = update.effective_chat.id

    try:
        try:
            event_id = create_calendar_event(name, phone, service, date, appt_time)
        except Exception:
            traceback.print_exc()
            event_id = ""

        booking_id = add_booking(name, phone, service, date, appt_time, chat_id, event_id)
        await update.message.reply_text(
            t(context, "confirmed").format(name=name, phone=phone, service=service, date=date, time=appt_time),
            reply_markup=MAIN_MENU,
        )
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            parse_mode="HTML",
            text=(
                f"🔔 <b>New Booking!</b>\n\n"
                f"<b>ID:</b> {booking_id}\n"
                f"<b>Name:</b> {html_lib.escape(name)}\n"
                f"<b>Phone:</b> {html_lib.escape(phone)}\n"
                f"<b>Service:</b> {html_lib.escape(service)}\n"
                f"<b>Date:</b> {html_lib.escape(date)}\n"
                f"<b>Time:</b> {html_lib.escape(appt_time)}"
            ),
        )
    except Exception:
        traceback.print_exc()
        await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def exit_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "en")
    await update.message.reply_text(TEXTS[lang]["cancelled"], reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Location conversation ─────────────────────────────────────────────────────

async def location_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_owner(update):
        lang = context.user_data.get("lang", "en")
        await update.message.reply_text(TEXTS[lang]["owner_blocked"], reply_markup=OWNER_MENU)
        return ConversationHandler.END
    lang = context.user_data.get("lang", "en")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(name, callback_data=f"branch:{name}")]
        for name in STORES
    ])
    await update.message.reply_text(TEXTS[lang]["choose_store"], reply_markup=keyboard)
    return STORE_SELECT


async def send_store_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    branch_name = query.data.split(":", 1)[1]
    store = STORES.get(branch_name)
    await query.edit_message_reply_markup(reply_markup=None)
    if not store:
        await query.message.reply_text(t(context, "branch_not_found"), reply_markup=MAIN_MENU)
        return ConversationHandler.END
    await query.message.reply_location(latitude=store["lat"], longitude=store["lon"])
    await query.message.reply_text(
        f"📍 {branch_name}\n{store['address']}",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


# ── Change schedule conversation ──────────────────────────────────────────────

async def change_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_owner(update):
        lang = context.user_data.get("lang", "en")
        await update.message.reply_text(TEXTS[lang]["owner_blocked"], reply_markup=OWNER_MENU)
        return ConversationHandler.END
    lang = context.user_data.get("lang", "en")
    await update.message.reply_text(TEXTS[lang]["ask_phone_lookup"], reply_markup=ReplyKeyboardRemove())
    return CHANGE_PHONE


async def change_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    try:
        booking = find_any_booking_by_phone(phone)
    except Exception:
        traceback.print_exc()
        await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if not booking:
        await update.message.reply_text(t(context, "change_not_found"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if booking["status"] == "Cancelled":
        await update.message.reply_text(t(context, "already_cancelled"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    context.user_data["booking"] = booking
    await update.message.reply_text(
        t(context, "change_found").format(
            service=booking["service"], date=booking["date"], time=booking["time"]
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHANGE_DATE


async def change_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        parsed = datetime.strptime(date_text, "%d/%m/%Y").date()
    except ValueError:
        await update.message.reply_text(t(context, "invalid_date"))
        return CHANGE_DATE

    if parsed < datetime.now().date():
        await update.message.reply_text(t(context, "past_date"))
        return CHANGE_DATE

    context.user_data["new_date"] = date_text
    await update.message.reply_text(
        t(context, "ask_time"),
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHANGE_TIME


async def change_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_time = update.message.text.strip()
    if parse_time(new_time) is None:
        await update.message.reply_text(t(context, "invalid_time"))
        return CHANGE_TIME
    new_date = context.user_data["new_date"]
    booking = context.user_data["booking"]
    if _slot_conflicts(new_time, get_bookings_by_date(new_date), exclude_row=booking["row"]):
        await update.message.reply_text(t(context, "time_conflict"))
        return CHANGE_TIME

    try:
        update_booking_schedule(booking["row"], new_date, new_time)

        try:
            event_id = booking.get("event_id", "")
            if event_id:
                update_calendar_event(event_id, booking["name"], booking["phone"], booking["service"], new_date, new_time)
            else:
                new_event_id = create_calendar_event(booking["name"], booking["phone"], booking["service"], new_date, new_time)
                save_event_id(booking["row"], new_event_id)
        except Exception:
            traceback.print_exc()

        await update.message.reply_text(
            t(context, "schedule_updated").format(
                service=booking["service"], date=new_date, time=new_time
            ),
            reply_markup=MAIN_MENU,
        )
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            parse_mode="HTML",
            text=(
                f"🔄 <b>Booking Rescheduled!</b>\n\n"
                f"<b>ID:</b> {booking['id']}\n"
                f"<b>Name:</b> {html_lib.escape(booking['name'])}\n"
                f"<b>Phone:</b> {html_lib.escape(booking['phone'])}\n"
                f"<b>Service:</b> {html_lib.escape(booking['service'])}\n"
                f"<b>New Date:</b> {html_lib.escape(new_date)}\n"
                f"<b>New Time:</b> {html_lib.escape(new_time)}"
            ),
        )
    except Exception:
        traceback.print_exc()
        await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Cancel appointment conversation ───────────────────────────────────────────

async def cancel_appt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_owner(update):
        lang = context.user_data.get("lang", "en")
        await update.message.reply_text(TEXTS[lang]["owner_blocked"], reply_markup=OWNER_MENU)
        return ConversationHandler.END
    lang = context.user_data.get("lang", "en")
    await update.message.reply_text(TEXTS[lang]["ask_phone_lookup"], reply_markup=ReplyKeyboardRemove())
    return CANCEL_PHONE


async def cancel_appt_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    try:
        booking = find_any_booking_by_phone(phone)
    except Exception:
        traceback.print_exc()
        await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if not booking:
        await update.message.reply_text(t(context, "booking_not_found"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    if booking["status"] == "Cancelled":
        await update.message.reply_text(t(context, "already_cancelled"), reply_markup=MAIN_MENU)
        return ConversationHandler.END

    context.user_data["booking"] = booking
    yes_label, no_label = t(context, "yes_no")[0]
    await update.message.reply_text(
        t(context, "cancel_appt_found").format(
            service=booking["service"], date=booking["date"], time=booking["time"]
        ),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(yes_label, callback_data="cancel:yes"),
            InlineKeyboardButton(no_label,  callback_data="cancel:no"),
        ]]),
    )
    return CANCEL_CONFIRM


async def cancel_appt_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking = context.user_data["booking"]
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "cancel:yes":
        try:
            cancel_booking_by_row(booking["row"])

            try:
                event_id = booking.get("event_id", "")
                if event_id:
                    delete_calendar_event(event_id)
            except Exception:
                traceback.print_exc()

            await query.message.reply_text(t(context, "appointment_cancelled"), reply_markup=MAIN_MENU)
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                parse_mode="HTML",
                text=(
                    f"❌ <b>Booking Cancelled!</b>\n\n"
                    f"<b>ID:</b> {booking['id']}\n"
                    f"<b>Name:</b> {html_lib.escape(booking['name'])}\n"
                    f"<b>Phone:</b> {html_lib.escape(booking['phone'])}\n"
                    f"<b>Service:</b> {html_lib.escape(booking['service'])}\n"
                    f"<b>Date:</b> {html_lib.escape(booking['date'])}\n"
                    f"<b>Time:</b> {html_lib.escape(booking['time'])}"
                ),
            )
        except Exception:
            traceback.print_exc()
            await query.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
    else:
        await query.message.reply_text(t(context, "cancel_aborted"), reply_markup=MAIN_MENU)

    return ConversationHandler.END


# ── Daily report ─────────────────────────────────────────────────────────────

async def _delete_after(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def _format_report(report, title):
    return (
        f"📊 <b>{title}</b>\n\n"
        f"📋 Total Bookings: <b>{report['total']}</b>\n"
        f"⏳ Not Yet (upcoming): <b>{report['not_yet']}</b>\n"
        f"✅ Completed: <b>{report['completed']}</b>\n"
        f"❌ Cancelled: <b>{report['cancelled']}</b>\n\n"
        f"<i>⏳ This message disappears in 3 minutes.</i>"
    )


async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📊 Choose report period:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📅 Today", callback_data="rep:today"),
            InlineKeyboardButton("📆 Custom Range", callback_data="rep:custom"),
        ]]),
    )
    return REPORT_DATE


async def report_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "rep:today":
        today = datetime.now().strftime("%d/%m/%Y")
        report = get_report_range(today, today)
        if not report:
            await query.message.reply_text("❌ Could not load report.", reply_markup=OWNER_MENU)
            return ConversationHandler.END
        msg = await query.message.reply_text(
            _format_report(report, f"Report — {today}"),
            parse_mode="HTML",
            reply_markup=OWNER_MENU,
        )
        asyncio.create_task(_delete_after(context.bot, msg.chat_id, msg.message_id, 180))
        return ConversationHandler.END

    await query.message.reply_text(
        "📅 Enter a date or range:\n\n"
        "Single day: <code>25/05/2026</code>\n"
        "Range: <code>01/05/2026 - 31/05/2026</code>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REPORT_INPUT


async def report_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    m = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})$', text)
    if m:
        start_str, end_str = m.group(1), m.group(2)
    else:
        start_str = end_str = text

    report = get_report_range(start_str, end_str)
    if not report:
        await update.message.reply_text(
            "❌ Invalid format. Use <code>DD/MM/YYYY</code> or <code>DD/MM/YYYY - DD/MM/YYYY</code>",
            parse_mode="HTML",
        )
        return REPORT_INPUT

    title = f"Report — {start_str}" if start_str == end_str else f"Report — {start_str} to {end_str}"
    msg = await update.message.reply_text(
        _format_report(report, title),
        parse_mode="HTML",
        reply_markup=OWNER_MENU,
    )
    asyncio.create_task(_delete_after(context.bot, msg.chat_id, msg.message_id, 180))
    return ConversationHandler.END


# ── Reminder scheduler ────────────────────────────────────────────────────────

def send_reminders_sync(bot_token):
    async def _send():
        from telegram import Bot
        bot = Bot(token=bot_token)
        bookings = get_tomorrows_bookings()
        for booking in bookings:
            patient_chat_id = booking.get("Chat_ID")
            if patient_chat_id:
                lang = "en"
                msg = TEXTS[lang]["reminder"].format(
                    service=booking["Service"], time=booking["Time"]
                )
                try:
                    await bot.send_message(chat_id=int(patient_chat_id), text=msg)
                except Exception:
                    traceback.print_exc()

            await bot.send_message(
                chat_id=OWNER_CHAT_ID,
                parse_mode="HTML",
                text=(
                    f"⏰ <b>Tomorrow's Appointment</b>\n\n"
                    f"<b>Name:</b> {html_lib.escape(booking['Name'])}\n"
                    f"<b>Phone:</b> {html_lib.escape(booking['Phone'])}\n"
                    f"<b>Service:</b> {html_lib.escape(booking['Service'])}\n"
                    f"<b>Time:</b> {html_lib.escape(booking['Time'])}"
                ),
            )
    asyncio.run(_send())


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    persistence = PicklePersistence(filepath="bot_data.pkl")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    shared_fallbacks = [
        CommandHandler("cancel", exit_conv),
        CommandHandler("start", start),
    ]

    booking_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📅 Book Appointment$"), book_start)],
        states={
            LANGUAGE: [CallbackQueryHandler(choose_language, pattern="^lang:")],
            NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            SERVICE:  [CallbackQueryHandler(get_service, pattern="^svc:")],
            DATE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            TIME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="booking_conv",
    )

    location_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📍 Location$"), location_menu)],
        states={
            STORE_SELECT: [CallbackQueryHandler(send_store_location, pattern="^branch:")],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="location_conv",
    )

    change_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔄 Change Schedule$"), change_start)],
        states={
            CHANGE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_lookup)],
            CHANGE_DATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, change_new_date)],
            CHANGE_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, change_new_time)],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="change_conv",
    )

    cancel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^❌ Cancel Appointment$"), cancel_appt_start)],
        states={
            CANCEL_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appt_lookup)],
            CANCEL_CONFIRM: [CallbackQueryHandler(cancel_appt_confirm, pattern="^cancel:")],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="cancel_conv",
    )

    report_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📊 Daily Report$"), report_handler)],
        states={
            REPORT_DATE:  [CallbackQueryHandler(report_choose, pattern="^rep:")],
            REPORT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_date_input)],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="report_conv",
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(booking_conv)
    app.add_handler(location_conv)
    app.add_handler(change_conv)
    app.add_handler(cancel_conv)
    app.add_handler(report_conv)

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders_sync, "cron", hour=8, minute=0, args=[TELEGRAM_BOT_TOKEN])
    scheduler.start()

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
