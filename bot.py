# =========================
# PRO NAVIGATION FIX
# =========================

def reset_state(chat_id):
    user_state.pop(chat_id, None)


# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

@bot.message_handler(func=lambda message: message.text == "🏠 Старт")
def go_home(message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())


@bot.message_handler(func=lambda message: message.text == "⬅️ Назад")
def go_back(message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=main_menu())


# =========================
# ДОЛГИ (исправлено)
# =========================

@bot.message_handler(func=lambda message: message.text == "💰 Долги")
def debts_start(message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Раздел долгов:", reply_markup=debts_menu())


# =========================
# ДОБАВИТЬ ДОЛЖНИКА (исправлено)
# =========================

@bot.message_handler(func=lambda message: message.text == "➕ Добавить должника")
def add_debtor_start(message):
    reset_state(message.chat.id)
    user_state[message.chat.id] = {"step": "add_debtor_name"}
    bot.send_message(message.chat.id, "Напиши ФИО должника:", reply_markup=debts_menu())


# =========================
# ДОБАВИТЬ ОПЛАТУ (исправлено)
# =========================

@bot.message_handler(func=lambda message: message.text == "💵 Добавить оплату")
def add_payment_start(message):
    reset_state(message.chat.id)

    debts = load_debts()
    if not debts:
        bot.send_message(message.chat.id, "Нет должников.", reply_markup=debts_menu())
        return

    text = "Выбери номер должника:\n\n"
    for i, d in enumerate(debts, start=1):
        text += f"{i}. {d.get('name')}\n"

    user_state[message.chat.id] = {"step": "payment_choose_debtor"}
    bot.send_message(message.chat.id, text, reply_markup=debts_menu())


# =========================
# ИЗМЕНИТЬ ДОЛГ (исправлено)
# =========================

@bot.message_handler(func=lambda message: message.text == "✏️ Изменить общий долг")
def change_total_start(message):
    reset_state(message.chat.id)

    debts = load_debts()
    if not debts:
        bot.send_message(message.chat.id, "Нет должников.", reply_markup=debts_menu())
        return

    text = "Выбери номер должника:\n\n"
    for i, d in enumerate(debts, start=1):
        text += f"{i}. {d.get('name')}\n"

    user_state[message.chat.id] = {"step": "change_total_choose"}
    bot.send_message(message.chat.id, text, reply_markup=debts_menu())
