import telebot
from telebot import types
import json
import os
import threading
import time
from datetime import datetime

from config import BOT_TOKEN, ADMIN_ID

bot = telebot.TeleBot(BOT_TOKEN)

REMINDERS_FILE = "reminders.json"
DEBTS_FILE = "debts.json"

DEBT_CONTROL_TIME = "10:00"
DEBT_WARNING_DAYS = 30

user_state = {}


# =========================
# JSON
# =========================

def load_json(file_name, default):
    if not os.path.exists(file_name):
        save_json(file_name, default)
        return default

    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
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
    return f"{int(value):,}".replace(",", " ")


def get_next_reminder_id(reminders):
    if not reminders:
        return 1
    return max(int(r.get("id", 0)) for r in reminders) + 1


def normalize_time(text):
    text = text.strip().replace(" ", "")

    try:
        dt = datetime.strptime(text, "%H:%M")
        return dt.strftime("%H:%M")
    except:
        pass

    try:
        dt = datetime.strptime(text, "%H.%M")
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


# =========================
# КЛАВИАТУРЫ
# =========================

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔔 Добавить напоминание")
    markup.row("📋 Мои напоминания", "💰 Долги")
    markup.row("🆔 Мой ID")
    return markup


def debts_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Список долгов")
    markup.row("📈 Контроль долгов")
    markup.row("➕ Добавить должника", "💵 Добавить оплату")
    markup.row("✏️ Изменить общий долг")
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
    bot.send_message(
        message.chat.id,
        "Ассалому алайкум. Я твой личный бот-напоминатель.\n\n"
        "🔔 Напоминания\n"
        "📋 Дела\n"
        "💰 Долги\n"
        "📈 Контроль должников",
        reply_markup=main_menu()
    )


@bot.message_handler(func=lambda message: message.text == "🆔 Мой ID")
def my_id(message):
    bot.send_message(message.chat.id, f"Твой Telegram ID:\n\n`{message.chat.id}`", parse_mode="Markdown")


# =========================
# НАПОМИНАНИЯ
# =========================

@bot.message_handler(func=lambda message: message.text == "🔔 Добавить напоминание")
def add_reminder_start(message):
    user_state[message.chat.id] = {"step": "choose_reminder_type"}
    bot.send_message(message.chat.id, "Выбери тип напоминания:", reply_markup=reminder_type_menu())


@bot.message_handler(func=lambda message: message.text in [
    "📅 Каждый день",
    "📆 Каждую неделю",
    "🎂 Каждый год",
    "⏰ Один раз"
])
def choose_reminder_type(message):
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
    date_value = normalize_date_day_month(message.text)

    if not date_value:
        bot.send_message(message.chat.id, "Дату нужно написать так: 05.01")
        return

    user_state[message.chat.id]["date"] = date_value
    save_new_reminder(message.chat.id)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "reminder_once_date")
def reminder_once_date(message):
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
    bot.send_message(message.chat.id, "Раздел долгов:", reply_markup=debts_menu())


@bot.message_handler(func=lambda message: message.text == "📊 Список долгов")
def show_debts(message):
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
    user_state[message.chat.id] = {"step": "add_debtor_name"}
    bot.send_message(message.chat.id, "Напиши ФИО или имя должника:")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "add_debtor_name")
def add_debtor_name(message):
    user_state[message.chat.id]["name"] = message.text
    user_state[message.chat.id]["step"] = "add_debtor_total"
    bot.send_message(message.chat.id, "Напиши общий долг цифрами. Например: 1500000")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "add_debtor_total")
def add_debtor_total(message):
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
    debts = load_debts()

    if not debts:
        bot.send_message(message.chat.id, "Пока нет должников.", reply_markup=debts_menu())
        return

    text = "Выбери номер должника:\n\n"
    for i, d in enumerate(debts, start=1):
        text += f"{i}. {d.get('name')}\n"

    user_state[message.chat.id] = {"step": "payment_choose_debtor"}
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_choose_debtor")
def payment_choose_debtor(message):
    debts = load_debts()

    try:
        index = int(message.text) - 1
        debts[index]
    except:
        bot.send_message(message.chat.id, "Напиши правильный номер должника.")
        return

    user_state[message.chat.id]["debtor_index"] = index
    user_state[message.chat.id]["step"] = "payment_amount"

    bot.send_message(message.chat.id, "Сколько он оплатил? Напиши цифрами.")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_amount")
def payment_amount(message):
    try:
        amount = int(message.text.replace(" ", ""))
    except:
        bot.send_message(message.chat.id, "Напиши сумму только цифрами.")
        return

    user_state[message.chat.id]["amount"] = amount
    user_state[message.chat.id]["step"] = "payment_date"

    bot.send_message(message.chat.id, "Напиши дату оплаты: 27.04.2026\nИли напиши: сегодня")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "payment_date")
def payment_date(message):
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
    debts = load_debts()

    try:
        index = int(message.text) - 1
        debts[index]
    except:
        bot.send_message(message.chat.id, "Напиши правильный номер должника.")
        return

    user_state[message.chat.id]["debtor_index"] = index
    user_state[message.chat.id]["step"] = "change_total_amount"

    bot.send_message(message.chat.id, "Напиши новый общий долг цифрами.")


@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "change_total_amount")
def change_total_amount(message):
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
# НАЗАД
# =========================

@bot.message_handler(func=lambda message: message.text == "⬅️ Назад")
def back(message):
    user_state.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())


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
# НЕИЗВЕСТНАЯ КОМАНДА
# =========================

@bot.message_handler(func=lambda message: True)
def unknown(message):
    bot.send_message(message.chat.id, "Я не понял команду. Выбери кнопку из меню.", reply_markup=main_menu())


# =========================
# ЗАПУСК
# =========================

from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "OK"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def run_bot():
    bot.infinity_polling(skip_pending=True)
    
if __name__ == "__main__":
    print("Бот запущен...")

    t1 = threading.Thread(target=reminder_loop)
    t1.daemon = True
    t1.start()

    t2 = threading.Thread(target=debt_auto_control_loop)
    t2.daemon = True
    t2.start()

    # запускаем веб
    threading.Thread(target=run_web).start()

    # запускаем бота
    threading.Thread(target=run_bot).start()
