import os
import traceback
import asyncio
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, MessageHandler, CommandHandler, filters,
    ContextTypes, ConversationHandler, PicklePersistence,
)
from sheets import add_booking, find_booking_by_phone, find_any_booking_by_phone, update_booking_schedule, save_event_id, cancel_booking_by_row, get_tomorrows_bookings
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
    ],
    resize_keyboard=True,
)


def t(context, key):
    lang = context.user_data.get("lang", "en")
    return TEXTS[lang][key]


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    context.user_data.clear()
    keyboard = [["🇬🇧 English", "🇰🇭 Khmer"]]
    await update.message.reply_text(
        "Please choose your language / សូមជ្រើសរើសភាសា:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return LANGUAGE


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lang"] = "kh" if "Khmer" in update.message.text else "en"
    await update.message.reply_text(t(context, "welcome"), reply_markup=ReplyKeyboardRemove())
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
    await update.message.reply_text(
        t(context, "ask_service"),
        reply_markup=ReplyKeyboardMarkup(t(context, "services"), resize_keyboard=True, one_time_keyboard=True),
    )
    return SERVICE


async def get_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["service"] = update.message.text
    await update.message.reply_text(t(context, "ask_date"), reply_markup=ReplyKeyboardRemove())
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


async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appt_time = update.message.text.strip()
    if parse_time(appt_time) is None:
        await update.message.reply_text(t(context, "invalid_time"))
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
                f"<b>Name:</b> {name}\n"
                f"<b>Phone:</b> {phone}\n"
                f"<b>Service:</b> {service}\n"
                f"<b>Date:</b> {date}\n"
                f"<b>Time:</b> {appt_time}"
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
    lang = context.user_data.get("lang", "en")
    keyboard = [[name] for name in STORES]
    await update.message.reply_text(
        TEXTS[lang]["choose_store"],
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return STORE_SELECT


async def send_store_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = STORES.get(update.message.text)
    if not store:
        await update.message.reply_text(t(context, "branch_not_found"), reply_markup=MAIN_MENU)
        return ConversationHandler.END
    await update.message.reply_location(latitude=store["lat"], longitude=store["lon"])
    await update.message.reply_text(
        f"📍 {update.message.text}\n{store['address']}",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


# ── Change schedule conversation ──────────────────────────────────────────────

async def change_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                f"<b>Name:</b> {booking['name']}\n"
                f"<b>Phone:</b> {booking['phone']}\n"
                f"<b>Service:</b> {booking['service']}\n"
                f"<b>New Date:</b> {new_date}\n"
                f"<b>New Time:</b> {new_time}"
            ),
        )
    except Exception:
        traceback.print_exc()
        await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Cancel appointment conversation ───────────────────────────────────────────

async def cancel_appt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(
        t(context, "cancel_appt_found").format(
            service=booking["service"], date=booking["date"], time=booking["time"]
        ),
        reply_markup=ReplyKeyboardMarkup(t(context, "yes_no"), resize_keyboard=True, one_time_keyboard=True),
    )
    return CANCEL_CONFIRM


async def cancel_appt_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    booking = context.user_data["booking"]

    if answer.startswith("✅"):
        try:
            cancel_booking_by_row(booking["row"])

            try:
                event_id = booking.get("event_id", "")
                if event_id:
                    delete_calendar_event(event_id)
            except Exception:
                traceback.print_exc()

            await update.message.reply_text(t(context, "appointment_cancelled"), reply_markup=MAIN_MENU)
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                parse_mode="HTML",
                text=(
                    f"❌ <b>Booking Cancelled!</b>\n\n"
                    f"<b>ID:</b> {booking['id']}\n"
                    f"<b>Name:</b> {booking['name']}\n"
                    f"<b>Phone:</b> {booking['phone']}\n"
                    f"<b>Service:</b> {booking['service']}\n"
                    f"<b>Date:</b> {booking['date']}\n"
                    f"<b>Time:</b> {booking['time']}"
                ),
            )
        except Exception:
            traceback.print_exc()
            await update.message.reply_text(t(context, "error"), reply_markup=MAIN_MENU)
    else:
        await update.message.reply_text(t(context, "cancel_aborted"), reply_markup=MAIN_MENU)

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
                    f"<b>Name:</b> {booking['Name']}\n"
                    f"<b>Phone:</b> {booking['Phone']}\n"
                    f"<b>Service:</b> {booking['Service']}\n"
                    f"<b>Time:</b> {booking['Time']}"
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
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_language)],
            NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            SERVICE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_service)],
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
            STORE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_store_location)],
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
            CANCEL_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appt_confirm)],
        },
        fallbacks=shared_fallbacks,
        persistent=True,
        name="cancel_conv",
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(booking_conv)
    app.add_handler(location_conv)
    app.add_handler(change_conv)
    app.add_handler(cancel_conv)

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders_sync, "cron", hour=8, minute=0, args=[TELEGRAM_BOT_TOKEN])
    scheduler.start()

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
