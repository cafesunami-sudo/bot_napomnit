import telebot
from telebot import types
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request

try:
    from config import BOT_TOKEN as CONFIG_BOT_TOKEN, ADMIN_ID as CONFIG_ADMIN_ID
except Exception:
    CONFIG_BOT_TOKEN = ""
    CONFIG_ADMIN_ID = 0

BOT_TOKEN = os.environ.get("BOT_TOKEN", CONFIG_BOT_TOKEN)
ADMIN_ID = int(os.environ.get("ADMIN_ID", CONFIG_ADMIN_ID))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не указан. Добавь BOT_TOKEN в Render Environment или в config.py")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

REMINDERS_FILE = "reminders.json"
DEBTS_FILE = "debts.json"
CREDITS_FILE = "credits.json"
CREDIT_SENT_FILE = "credit_reminders_sent.json"

DEBT_CONTROL_TIME = "10:00"
DEBT_WARNING_DAYS = 30

CREDIT_REMIND_TIME = "10:00"
CREDIT_WARNING_DAYS_BEFORE = 2

user_state = {}


# =========================
# ДОСТУП
# =========================

def is_allowed_user(chat_id):
    return int(chat_id) == int(ADMIN_ID)


def reset_state(chat_id):
    user_state.pop(chat_id, None)


def guard(message):
    if not is_allowed_user(message.chat.id):
        bot.send_message(message.chat.id, "⛔ Доступ запрещен")
        return False
    return True


# =========================
# JSON
# =========================

def load_json(file_name, default):
    if not os.path.exists(file_name):
        save_json(file_name, default)
        return default

    try:
        with open(file_name, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data is None:
                return default
            return data
    except:
        save_json(file_name, default)
        return default


def save_json(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_reminders():
    return load_json(REMINDERS_FILE, [])


def save_reminders(data):
    save_json(REMINDERS_FILE, data)


def load_debts():
    return load_json(DEBTS_FILE, [])


def save_debts(data):
    save_json(DEBTS_FILE, data)


def format_sum(value):
    try:
        value = float(value)
    except:
        value = 0

    if value.is_integer():
        return f"{int(value):,}".replace(",", " ")

    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def get_next_reminder_id(reminders):
    if not reminders:
        return 1
    return max(int(r.get("id", 0)) for r in reminders) + 1


def normalize_time(text):
    text = text.strip().replace(" ", "")

    for fmt in ["%H:%M", "%H.%M"]:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%H:%M")
        except:
            pass

    return None


def normalize_date_full(text):
    text = text.strip().replace(" ", "")

    for fmt in ["%d.%m.%Y", "%d.%m.%y"]:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%d.%m.%Y")
        except:
            pass

    return None


def normalize_date_day_month(text):
    text = text.strip().replace(" ", "")

    try:
        dt = datetime.strptime(text, "%d.%m")
        return dt.strftime("%d.%m")
    except:
        pass

    return None


def parse_money(text):
    text = str(text).replace("\u00a0", " ")
    match = re.search(r"(\d[\d\s]*[.,]?\d*)", text)
    if not match:
        return None

    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except:
        return None


# =========================
# КРЕДИТЫ
# =========================

DEFAULT_CREDITS = [
    {
        "name": "ТБС банк",
        "total": 14209240.81,
        "paid": 7557562.12,
        "left": 6651642.69,
        "monthly": 1209240.81,
        "payment_day": 12
    },
    {
        "name": "Узум банк",
        "total": 6804000.0,
        "paid": 3402000.0,
        "left": 3402000.0,
        "monthly": 567000.0,
        "payment_day": 25
    },
    {
        "name": "Миллий банк",
        "total": 72000000.0,
        "paid": 18690649.0,
        "left": 53309351.0,
        "monthly": 2324838.79,
        "payment_day": 5
    }
]


def load_credits():
    credits = load_json(CREDITS_FILE, DEFAULT_CREDITS)

    if not isinstance(credits, list) or not credits:
        credits = DEFAULT_CREDITS
        save_credits(credits)

    names = {c.get("name") for c in credits if isinstance(c, dict)}
    changed = False

    for default_credit in DEFAULT_CREDITS:
        if default_credit["name"] not in names:
            credits.append(default_credit)
            changed = True

    if changed:
        save_credits(credits)

    return credits


def save_credits(data):
    save_json(CREDITS_FILE, data)


def load_credit_sent():
    return load_json(CREDIT_SENT_FILE, [])


def save_credit_sent(data):
    save_json(CREDIT_SENT_FILE, data)


def normalize_credit_name(text):
    text = str(text).lower()

    if "тбс" in text or "tbc" in text or "tbs" in text:
        return "ТБС банк"
    if "узум" in text or "uzum" in text:
        return "Узум банк"
    if "миллий" in text or "milliy" in text:
        return "Миллий банк"

    return ""


def update_credit_left(credit_name, new_left):
    credits = load_credits()
    updated_credit = None

    for c in credits:
        if c.get("name") == credit_name:
            c["left"] = max(float(new_left), 0)
            c["paid"] = max(float(c.get("total", 0)) - float(c.get("left", 0)), 0)
            c["last_update"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            updated_credit = c
            break

    if updated_credit:
        save_credits(credits)

    return updated_credit


def get_credit_text(c):
    return (
        f"🏦 {c.get('name')}\n"
        f"💳 Ежемесячный платёж: {format_sum(c.get('monthly', 0))} сум\n"
        f"📉 Остаток: {format_sum(c.get('left', 0))} сум\n"
        f"📅 Дата платежа: {c.get('payment_day')} число каждого месяца"
    )


def get_credits_list_text():
    credits = load_credits()
    text = "💳 Кредиты\n\n"

    for c in credits:
        text += get_credit_text(c)
        if c.get("last_update"):
            text += f"\n🕒 Обновлено: {c.get('last_update')}"
        text += "\n\n"

    text += (
        "Чтобы обновить остаток из финанс-бота, отправь сюда строку вида:\n\n"
        "Кредит ТБС банк | остаток 6 151 642,69 | платеж 1 209 240,81 | дата 12"
    )

    return text


def parse_credit_update_text(text):
    credit_name = normalize_credit_name(text)
    if not credit_name:
        return None

    left_match = re.search(r"остаток\s+([\d\s.,]+)", text, re.IGNORECASE)
    if not left_match:
        return None

    left = parse_money(left_match.group(1))
    if left is None:
        return None

    return credit_name, left


def get_month_payment_date(year, month, day):
    if month == 12:
        next_month = datetime(year + 1, 1, 1).date()
    else:
        next_month = datetime(year, month + 1, 1).date()

    last_day = (next_month - timedelta(days=1)).day
    safe_day = min(int(day), last_day)
    return datetime(year, month, safe_day).date()


def get_credit_reminder_message(c, days_left):
    if days_left == 0:
        title = "🔴 Сегодня день платежа по кредиту"
    elif days_left == 1:
        title = "🟡 Завтра платеж по кредиту"
    else:
        title = f"🔔 Через {days_left} дня платеж по кредиту"

    return (
        f"{title}\n\n"
        f"{get_credit_text(c)}\n\n"
        f"Не забудь оплатить вовремя."
    )


# =========================
# КЛАВИАТУРЫ
# =========================

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔔 Добавить напоминание")
    markup.row("📋 Мои напоминания", "💰 Долги")
    markup.row("💳 Кредиты", "🆔 Мой ID")
    return markup


def debts_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Список долгов", "📈 Контроль долгов")
    markup.row("➕ Добавить должника", "💵 Добавить оплату")
    markup.row("✏️ Изменить общий долг")
    markup.row("⬅️ Назад")
    return markup


def credits_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Список кредитов")
    markup.row("⬅️ Назад")
    return markup


def reminder_type_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📅 Каждый день")
    markup.row("📆 Каждую неделю")
    markup.row("🎂 Каждый год")
    markup.row("⏰ Один раз")
    markup.row("⬅️ Назад")
    return markup


def weekdays_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Понедельник", "Вторник")
    markup.row("Среда", "Четверг")
    markup.row("Пятница", "Суббота")
    markup.row("Воскресенье")
    markup.row("⬅️ Назад")
    return markup


# =========================
# START
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    bot.send_message(
        message.chat.id,
        "Ассалому алайкум. Я твой личный бот-напоминатель.\n\n"
        "🔔 Напоминания\n"
        "📋 Дела\n"
        "💰 Долги\n"
        "💳 Кредиты и остатки\n"
        "📈 Контроль должников",
        reply_markup=main_menu()
    )


@bot.message_handler(func=lambda message: message.text == "🆔 Мой ID")
def my_id(message):
    if not guard(message):
        return
    bot.send_message(message.chat.id, f"Твой Telegram ID:\n\n`{message.chat.id}`", parse_mode="Markdown")


# =========================
# НАВИГАЦИЯ
# =========================

@bot.message_handler(func=lambda message: message.text in ["⬅️ Назад", "🏠 Старт"])
def navigation_back_or_home(message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())


# =========================
# НАПОМИНАНИЯ
# =========================

@bot.message_handler(func=lambda message: message.text == "🔔 Добавить напоминание")
def add_reminder_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    user_state[message.chat.id] = {"step": "choose_reminder_type"}
    bot.send_message(message.chat.id, "Выбери тип напоминания:", reply_markup=reminder_type_menu())


@bot.message_handler(func=lambda message: message.text in [
    "📅 Каждый день",
    "📆 Каждую неделю",
    "🎂 Каждый год",
    "⏰ Один раз"
])
def choose_reminder_type(message):
    if not guard(message):
        return
    reminder_type_map = {
        "📅 Каждый день": "daily",
        "📆 Каждую неделю": "weekly",
        "🎂 Каждый год": "yearly",
        "⏰ Один раз": "once"
    }

    user_state[message.chat.id] = {
        "step": "reminder_text",
        "type": reminder_type_map[message.text]
    }

    bot.send_message(message.chat.id, "Напиши текст напоминания:")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_text")
def reminder_text(message):
    if not guard(message):
        return
    user_state[message.chat.id]["text"] = message.text
    user_state[message.chat.id]["step"] = "reminder_time"

    bot.send_message(
        message.chat.id,
        "Во сколько напоминать?\n\n"
        "Напиши время в формате:\n"
        "09:30\n"
        "17:00\n"
        "21:15"
    )


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_time")
def reminder_time(message):
    if not guard(message):
        return
    time_value = normalize_time(message.text)

    if not time_value:
        bot.send_message(message.chat.id, "Время нужно написать так: 09:30")
        return

    user_state[message.chat.id]["time"] = time_value
    r_type = user_state[message.chat.id]["type"]

    if r_type == "weekly":
        user_state[message.chat.id]["step"] = "reminder_weekday"
        bot.send_message(message.chat.id, "В какой день недели напоминать?", reply_markup=weekdays_menu())
        return

    if r_type == "yearly":
        user_state[message.chat.id]["step"] = "reminder_yearly_date"
        bot.send_message(
            message.chat.id,
            "Напиши дату для ежегодного напоминания:\n\n"
            "05.01\n"
            "Можно и так: 5.1"
        )
        return

    if r_type == "once":
        user_state[message.chat.id]["step"] = "reminder_once_date"
        bot.send_message(
            message.chat.id,
            "Напиши дату разового напоминания:\n\n"
            "03.05.2026\n"
            "Можно и так: 3.5.2026"
        )
        return

    save_new_reminder(message.chat.id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_weekday")
def reminder_weekday(message):
    if not guard(message):
        return
    weekdays = {
        "Понедельник": 0,
        "Вторник": 1,
        "Среда": 2,
        "Четверг": 3,
        "Пятница": 4,
        "Суббота": 5,
        "Воскресенье": 6
    }

    if message.text not in weekdays:
        bot.send_message(message.chat.id, "Выбери день недели кнопкой.")
        return

    user_state[message.chat.id]["weekday"] = weekdays[message.text]
    save_new_reminder(message.chat.id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_yearly_date")
def reminder_yearly_date(message):
    if not guard(message):
        return
    date_value = normalize_date_day_month(message.text)

    if not date_value:
        bot.send_message(message.chat.id, "Дату нужно написать так: 05.01")
        return

    user_state[message.chat.id]["date"] = date_value
    save_new_reminder(message.chat.id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_once_date")
def reminder_once_date(message):
    if not guard(message):
        return
    date_value = normalize_date_full(message.text)

    if not date_value:
        bot.send_message(message.chat.id, "Дату нужно написать так: 03.05.2026")
        return

    user_state[message.chat.id]["date"] = date_value
    save_new_reminder(message.chat.id)


def save_new_reminder(chat_id):
    data = user_state[chat_id]
    reminders = load_reminders()

    reminder = {
        "id": get_next_reminder_id(reminders),
        "chat_id": chat_id,
        "type": data["type"],
        "text": data["text"],
        "time": data["time"],
        "active": True,
        "last_sent": ""
    }

    if data["type"] == "weekly":
        reminder["weekday"] = data["weekday"]

    if data["type"] in ["yearly", "once"]:
        reminder["date"] = data["date"]

    reminders.append(reminder)
    save_reminders(reminders)

    user_state.pop(chat_id, None)

    bot.send_message(chat_id, "✅ Напоминание сохранено.", reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text == "📋 Мои напоминания")
def show_reminders(message):
    if not guard(message):
        return
    reminders = load_reminders()
    my_reminders = [r for r in reminders if r.get("chat_id") == message.chat.id and r.get("active")]

    if not my_reminders:
        bot.send_message(message.chat.id, "У тебя пока нет активных напоминаний.", reply_markup=main_menu())
        return

    text = "📋 Твои напоминания:\n\n"

    for r in my_reminders:
        r_type = r.get("type")

        if r_type == "daily":
            type_text = "Каждый день"
        elif r_type == "weekly":
            days = {
                0: "Понедельник",
                1: "Вторник",
                2: "Среда",
                3: "Четверг",
                4: "Пятница",
                5: "Суббота",
                6: "Воскресенье"
            }
            type_text = f"Каждую неделю: {days.get(r.get('weekday'))}"
        elif r_type == "yearly":
            type_text = f"Каждый год: {r.get('date')}"
        elif r_type == "once":
            type_text = f"Один раз: {r.get('date')}"
        else:
            type_text = "Неизвестно"

        text += (
            f"ID: {r['id']}\n"
            f"🔔 {r['text']}\n"
            f"⏰ {r['time']}\n"
            f"📌 {type_text}\n\n"
        )

    text += "Чтобы удалить напоминание, напиши:\nудалить 1"

    bot.send_message(message.chat.id, text, reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text.lower().startswith("удалить "))
def delete_reminder(message):
    if not guard(message):
        return
    try:
        reminder_id = int(message.text.split()[1])
    except:
        bot.send_message(message.chat.id, "Напиши так: удалить 1")
        return

    reminders = load_reminders()
    found = False

    for r in reminders:
        if r.get("id") == reminder_id and r.get("chat_id") == message.chat.id:
            r["active"] = False
            found = True

    save_reminders(reminders)

    if found:
        bot.send_message(message.chat.id, "✅ Напоминание удалено.", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "Такое напоминание не найдено.", reply_markup=main_menu())


# =========================
# ДОЛГИ
# =========================

@bot.message_handler(func=lambda message: message.text == "💰 Долги")
def debts_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Раздел долгов:", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: message.text == "📊 Список долгов")
def show_debts(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    debts = load_debts()

    if not debts:
        bot.send_message(message.chat.id, "Пока нет должников.", reply_markup=debts_menu())
        return

    text = "💰 Список долгов:\n\n"

    for i, d in enumerate(debts, start=1):
        total = int(d.get("total_debt", 0))
        paid = sum(int(p.get("amount", 0)) for p in d.get("payments", []))
        left = total - paid

        text += (
            f"{i}. {d.get('name')}\n"
            f"Общий долг: {format_sum(total)} сум\n"
            f"Оплачено: {format_sum(paid)} сум\n"
            f"Осталось: {format_sum(left)} сум\n"
        )

        if d.get("payments"):
            text += "Платежи:\n"
            for p in d["payments"]:
                text += f"— {p.get('date')}: {format_sum(p.get('amount', 0))} сум\n"

        text += "\n"

    bot.send_message(message.chat.id, text, reply_markup=debts_menu())


@bot.message_handler(func=lambda message: message.text == "📈 Контроль долгов")
def debt_control(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    text = get_debt_control_text()
    bot.send_message(message.chat.id, text, reply_markup=debts_menu())


def get_debt_control_text():
    debts = load_debts()

    if not debts:
        return "Пока нет должников."

    today = datetime.now().date()

    text = "📈 Контроль долгов\n\n"
    problem_count = 0

    for d in debts:
        name = d.get("name", "Без имени")
        total = int(d.get("total_debt", 0))
        payments = d.get("payments", [])
        paid = sum(int(p.get("amount", 0)) for p in payments)
        left = total - paid

        if left <= 0:
            status = "✅ Долг закрыт"
            last_info = "Оплата завершена"
        else:
            if payments:
                last_payment = payments[-1]
                last_date_text = last_payment.get("date")
                try:
                    last_date = datetime.strptime(last_date_text, "%d.%m.%Y").date()
                    days_passed = (today - last_date).days
                    last_info = f"Последняя оплата: {last_date_text}, прошло {days_passed} дн."

                    if days_passed >= DEBT_WARNING_DAYS:
                        status = "🔴 Проблемный долг"
                        problem_count += 1
                    elif days_passed >= 15:
                        status = "🟡 Нужно контролировать"
                    else:
                        status = "🟢 Нормально"
                except:
                    status = "⚠️ Ошибка даты"
                    last_info = "Дата оплаты указана неправильно"
            else:
                status = "🔴 Нет оплат"
                last_info = "По этому долгу еще не было оплат"
                problem_count += 1

        text += (
            f"👤 {name}\n"
            f"{status}\n"
            f"Общий долг: {format_sum(total)} сум\n"
            f"Оплачено: {format_sum(paid)} сум\n"
            f"Осталось: {format_sum(left)} сум\n"
            f"{last_info}\n\n"
        )

    text += f"Итого проблемных долгов: {problem_count}"

    return text


@bot.message_handler(func=lambda message: message.text == "➕ Добавить должника")
def add_debtor_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    user_state[message.chat.id] = {"step": "add_debtor_name"}
    bot.send_message(message.chat.id, "Напиши ФИО или имя должника:", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "add_debtor_name")
def add_debtor_name(message):
    if not guard(message):
        return
    user_state[message.chat.id]["name"] = message.text
    user_state[message.chat.id]["step"] = "add_debtor_total"
    bot.send_message(message.chat.id, "Напиши общий долг цифрами. Например: 1500000", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "add_debtor_total")
def add_debtor_total(message):
    if not guard(message):
        return
    try:
        total = int(message.text.replace(" ", ""))
    except:
        bot.send_message(message.chat.id, "Напиши только цифрами.")
        return

    debts = load_debts()

    debts.append({
        "name": user_state[message.chat.id]["name"],
        "total_debt": total,
        "payments": []
    })

    save_debts(debts)
    user_state.pop(message.chat.id, None)

    bot.send_message(message.chat.id, "✅ Должник добавлен.", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: message.text == "💵 Добавить оплату")
def add_payment_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    debts = load_debts()

    if not debts:
        bot.send_message(message.chat.id, "Пока нет должников.", reply_markup=debts_menu())
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    names = [d.get("name", "Без имени") for d in debts]

    for i in range(0, len(names), 2):
        markup.row(*names[i:i+2])

    markup.row("⬅️ Назад")

    user_state[message.chat.id] = {
        "step": "payment_choose_debtor",
        "debts": debts
    }

    bot.send_message(message.chat.id, "Выбери должника:", reply_markup=markup)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_choose_debtor")
def payment_choose_debtor(message):
    if not guard(message):
        return

    debts = user_state.get(message.chat.id, {}).get("debts", load_debts())

    for i, d in enumerate(debts):
        if message.text == d.get("name", "Без имени"):
            user_state[message.chat.id]["debtor_index"] = i
            user_state[message.chat.id]["step"] = "payment_amount"
            bot.send_message(
                message.chat.id,
                f"Выбран должник: {d.get('name')}\n\nСколько он оплатил? Напиши цифрами.",
                reply_markup=debts_menu()
            )
            return

    bot.send_message(message.chat.id, "Выбери должника кнопкой.")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_amount")
def payment_amount(message):
    if not guard(message):
        return
    try:
        amount = int(message.text.replace(" ", ""))
    except:
        bot.send_message(message.chat.id, "Напиши сумму только цифрами.")
        return

    user_state[message.chat.id]["amount"] = amount
    user_state[message.chat.id]["step"] = "payment_date"

    bot.send_message(message.chat.id, "Напиши дату оплаты: 27.04.2026\nИли напиши: сегодня", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_date")
def payment_date(message):
    if not guard(message):
        return
    if message.text.lower() == "сегодня":
        pay_date = datetime.now().strftime("%d.%m.%Y")
    else:
        pay_date = normalize_date_full(message.text)
        if not pay_date:
            bot.send_message(message.chat.id, "Дату нужно написать так: 27.04.2026")
            return

    debts = load_debts()
    index = user_state[message.chat.id]["debtor_index"]
    amount = user_state[message.chat.id]["amount"]

    debts[index]["payments"].append({
        "date": pay_date,
        "amount": amount
    })

    save_debts(debts)
    user_state.pop(message.chat.id, None)

    bot.send_message(message.chat.id, "✅ Оплата добавлена.", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: message.text == "✏️ Изменить общий долг")
def change_total_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    debts = load_debts()

    if not debts:
        bot.send_message(message.chat.id, "Пока нет должников.", reply_markup=debts_menu())
        return

    text = "Выбери номер должника:\n\n"
    for i, d in enumerate(debts, start=1):
        text += f"{i}. {d.get('name')}\n"

    user_state[message.chat.id] = {"step": "change_total_choose"}
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "change_total_choose")
def change_total_choose(message):
    if not guard(message):
        return
    debts = load_debts()

    try:
        index = int(message.text) - 1
        debts[index]
    except:
        bot.send_message(message.chat.id, "Напиши правильный номер должника.")
        return

    user_state[message.chat.id]["debtor_index"] = index
    user_state[message.chat.id]["step"] = "change_total_amount"

    bot.send_message(message.chat.id, "Напиши новый общий долг цифрами.", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "change_total_amount")
def change_total_amount(message):
    if not guard(message):
        return
    try:
        total = int(message.text.replace(" ", ""))
    except:
        bot.send_message(message.chat.id, "Напиши сумму только цифрами.")
        return

    debts = load_debts()
    index = user_state[message.chat.id]["debtor_index"]

    debts[index]["total_debt"] = total

    save_debts(debts)
    user_state.pop(message.chat.id, None)

    bot.send_message(message.chat.id, "✅ Общий долг изменен.", reply_markup=debts_menu())


# =========================
# КРЕДИТЫ
# =========================

@bot.message_handler(func=lambda message: message.text == "💳 Кредиты")
def credits_start(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, get_credits_list_text(), reply_markup=credits_menu())


@bot.message_handler(func=lambda message: message.text == "📊 Список кредитов")
def show_credits(message):
    if not guard(message):
        return
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, get_credits_list_text(), reply_markup=credits_menu())


@bot.message_handler(func=lambda message: isinstance(message.text, str) and "кредит" in message.text.lower() and "остаток" in message.text.lower())
def credit_update_from_finance_bot(message):
    if not guard(message):
        return

    parsed = parse_credit_update_text(message.text)
    if not parsed:
        bot.send_message(
            message.chat.id,
            "Не смог понять строку кредита.\n\n"
            "Отправь так:\n"
            "Кредит ТБС банк | остаток 6 151 642,69 | платеж 1 209 240,81 | дата 12",
            reply_markup=main_menu()
        )
        return

    credit_name, new_left = parsed
    updated = update_credit_left(credit_name, new_left)

    if not updated:
        bot.send_message(message.chat.id, "Кредит не найден.", reply_markup=main_menu())
        return

    bot.send_message(
        message.chat.id,
        "✅ Остаток кредита обновлён\n\n" + get_credit_text(updated),
        reply_markup=main_menu()
    )


# =========================
# АВТОПРОВЕРКА НАПОМИНАНИЙ
# =========================

def reminder_loop():
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today = now.strftime("%d.%m.%Y")
            today_day_month = now.strftime("%d.%m")
            weekday = now.weekday()

            reminders = load_reminders()
            changed = False

            for r in reminders:
                if not r.get("active"):
                    continue

                if r.get("time") != current_time:
                    continue

                if r.get("last_sent") == today:
                    continue

                send = False

                if r.get("type") == "daily":
                    send = True

                elif r.get("type") == "weekly":
                    if r.get("weekday") == weekday:
                        send = True

                elif r.get("type") == "yearly":
                    if r.get("date") == today_day_month:
                        send = True

                elif r.get("type") == "once":
                    if r.get("date") == today:
                        send = True
                        r["active"] = False

                if send:
                    bot.send_message(r["chat_id"], f"🔔 Напоминание:\n\n{r['text']}")
                    r["last_sent"] = today
                    changed = True

            if changed:
                save_reminders(reminders)

        except Exception as e:
            print("Ошибка в reminder_loop:", e)

        time.sleep(30)


# =========================
# АВТОКОНТРОЛЬ ДОЛГОВ
# =========================

def debt_auto_control_loop():
    last_sent_date = ""

    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today = now.strftime("%d.%m.%Y")

            if current_time == DEBT_CONTROL_TIME and last_sent_date != today:
                text = get_debt_control_text()

                if "🔴" in text:
                    bot.send_message(
                        ADMIN_ID,
                        "🔔 Ежедневный контроль долгов\n\n" + text
                    )

                last_sent_date = today

        except Exception as e:
            print("Ошибка в debt_auto_control_loop:", e)

        time.sleep(30)


# =========================
# АВТОНАПОМИНАНИЯ ПО КРЕДИТАМ
# =========================

def credit_auto_reminder_loop():
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today = now.date()
            today_text = now.strftime("%d.%m.%Y")

            if current_time != CREDIT_REMIND_TIME:
                time.sleep(30)
                continue

            credits = load_credits()
            sent = load_credit_sent()
            changed = False

            for c in credits:
                if float(c.get("left", 0)) <= 0:
                    continue

                payment_day = int(c.get("payment_day", 1))
                payment_date = get_month_payment_date(today.year, today.month, payment_day)
                days_left = (payment_date - today).days

                if days_left < 0:
                    next_month = today.month + 1
                    next_year = today.year

                    if next_month == 13:
                        next_month = 1
                        next_year += 1

                    payment_date = get_month_payment_date(next_year, next_month, payment_day)
                    days_left = (payment_date - today).days

                if 0 <= days_left <= CREDIT_WARNING_DAYS_BEFORE:
                    key = f"{c.get('name')}_{today_text}_{days_left}"

                    if key in sent:
                        continue

                    bot.send_message(ADMIN_ID, get_credit_reminder_message(c, days_left))
                    sent.append(key)
                    changed = True

            if changed:
                save_credit_sent(sent)

        except Exception as e:
            print("Ошибка в credit_auto_reminder_loop:", e)

        time.sleep(30)


# =========================
# НЕИЗВЕСТНАЯ КОМАНДА
# =========================

@bot.message_handler(func=lambda message: True)
def unknown(message):
    if not guard(message):
        return
    bot.send_message(message.chat.id, "Я не понял команду. Выбери кнопку из меню.", reply_markup=main_menu())


# =========================
# ЗАПУСК ЧЕРЕЗ WEBHOOK ДЛЯ RENDER
# =========================

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "bot_napomnit_secret")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://bot-napomnit.onrender.com").rstrip("/") + WEBHOOK_PATH


@app.route("/")
def home():
    return "OK"


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    try:
        if request.headers.get("content-type") == "application/json":
            json_string = request.get_data().decode("utf-8")
            update = types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return "OK", 200
        return "Unsupported Media Type", 415
    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return "OK", 200


def start_background_threads():
    t1 = threading.Thread(target=reminder_loop, daemon=True)
    t1.start()

    t2 = threading.Thread(target=debt_auto_control_loop, daemon=True)
    t2.start()

    t3 = threading.Thread(target=credit_auto_reminder_loop, daemon=True)
    t3.start()


def setup_webhook():
    print("Настраиваем webhook...")
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        print("WEBHOOK SET:", WEBHOOK_URL)
    except Exception as e:
        print("WEBHOOK SET ERROR:", e)


if __name__ == "__main__":
    print("Бот запускается через WEBHOOK...")
    setup_webhook()
    start_background_threads()

    port = int(os.environ.get("PORT", 10000))
    print("WEB SERVER STARTING ON PORT", port)
    app.run(host="0.0.0.0", port=port)
