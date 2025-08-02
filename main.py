import os
from dotenv import load_dotenv
load_dotenv()

import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'savings_bot.db')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        join_date TEXT
    )''')
    
    # Таблица копилок (накоплений)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS savings (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        monthly_contribution REAL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица долгов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS debts (
        debt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        due_date TEXT,
        status TEXT DEFAULT 'active',
        creation_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица взносов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contributions (
        contribution_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        month_year TEXT,
        contribution_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')
    
    conn.commit()
    conn.close()

# Добавление пользователя после нажатия /start
def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже пользователь
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, join_date)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        cursor.execute('''
        INSERT INTO savings (user_id, balance, monthly_contribution)
        VALUES (?, 0, 0)
        ''', (user_id,))
        
        conn.commit()
    
    conn.close()

# Команда /start
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [KeyboardButton("👀 Мой баланс"), KeyboardButton("💰 Общий баланс")],
        [KeyboardButton("🎯 Внести в копилку"), KeyboardButton("💸 Мои взносы")],
        [KeyboardButton("🍪 Взять в долг"), KeyboardButton("🔔 Мои долги")],
        [KeyboardButton("💪 Вернуть долг")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}! Я модератор копилки ЧЕЛОВ.\n"
        "📲 Используй кнопки ниже для взаимодействия:",
        reply_markup=reply_markup
    )

# Функции для работы с балансом
def get_user_balance(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM savings WHERE user_id = ?', (user_id,))
    balance = cursor.fetchone()[0]
    conn.close()
    return balance

def get_total_balance():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(balance) FROM savings')
    total = cursor.fetchone()[0] or 0
    conn.close()
    return total

def my_balance(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT balance, monthly_contribution FROM savings WHERE user_id = ?', (user_id,))
    balance, monthly_contribution = cursor.fetchone()
    conn.close()
    
    update.message.reply_text(
        f"Ваш текущий баланс: {balance:.2f}\n"
        f"Ежемесячный взнос: {monthly_contribution:.2f}"
    )

def total_balance(update: Update, context: CallbackContext):
    total = get_total_balance()
    update.message.reply_text(f"Общий баланс всех пользователей: {total:.2f}")

# Функции для работы с копилкой
def add_contribution(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Чтобы внести деньги в копилку, отправьте сообщение в формате:\n"
        "'вношу [сумма] за [мм.гггг]'\n\n"
        "Например: 'вношу 3000 за 07.2023'\n"
        "Или установите ежемесячный взнос:\n"
        "'установить взнос [сумма]'\n"
        "Например: 'установить взнос 3000'"
    )

def my_contributions(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT amount, month_year, contribution_date FROM contributions 
    WHERE user_id = ?
    ORDER BY contribution_date DESC
    LIMIT 10
    ''', (user_id,))
    
    contributions = cursor.fetchall()
    
    cursor.execute('SELECT monthly_contribution FROM savings WHERE user_id = ?', (user_id,))
    monthly_contribution = cursor.fetchone()[0]
    
    conn.close()
    
    message = f"Ваш текущий ежемесячный взнос: {monthly_contribution:.2f}\n\n"
    message += "Последние 10 взносов:\n"
    
    if not contributions:
        message += "У вас пока нет взносов."
    else:
        for amount, month_year, contribution_date in contributions:
            message += (
                f"{amount:.2f} за {month_year} (внесено {contribution_date.split()[0]})\n"
            )
    
    update.message.reply_text(message)

def process_contribution(update: Update, user_id: int, text: str):
    try:
        if text.startswith('установить взнос'):
            amount = float(text.split()[2])
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute('UPDATE savings SET monthly_contribution = ? WHERE user_id = ?', (amount, user_id))
            conn.commit()
            conn.close()
            update.message.reply_text(f"Установлен ежемесячный взнос: {amount:.2f}")
        elif 'за' in text:
            parts = text.split()
            amount = float(parts[1])
            month_year_index = parts.index('за') + 1
            month_year = parts[month_year_index]
            
            month, year = map(int, month_year.split('.'))
            if not (1 <= month <= 12 and year >= 2020):
                raise ValueError("Некорректная дата")
            
            conn = sqlite3.connect('savings_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO contributions (user_id, amount, month_year, contribution_date)
            VALUES (?, ?, ?, ?)
            ''', (user_id, amount, month_year, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            cursor.execute('UPDATE savings SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            
            conn.commit()
            conn.close()
            
            update.message.reply_text(
                f"Вы внесли {amount:.2f} за {month_year}. Ваш текущий баланс: {get_user_balance(user_id):.2f}"
            )
    except (ValueError, IndexError) as e:
        print(f"Ошибка: {e}")
        update.message.reply_text(
            "Некорректный формат сообщения. Примеры:\n"
            "'вношу 3000 за 07.2023'\n"
            "'установить взнос 3000'"
        )

# Функции для работы с долгами
def borrow_money(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Чтобы взять деньги в долг, отправьте сообщение в формате:\n"
        "'беру [сумма] до [дд.мм]'\n\n"
        "Например: 'беру 500 до 15.07'"
    )

def return_debt(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Чтобы вернуть долг, отправьте сообщение в формате:\n"
        "'возвращаю [сумма] за [дд.мм]'\n\n"
        "Например: 'возвращаю 500 за 15.07'"
    )

def my_debts(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = sqlite3.connect('savings_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT amount, due_date, creation_date FROM debts 
    WHERE user_id = ? AND status = 'active'
    ORDER BY due_date
    ''', (user_id,))
    
    debts = cursor.fetchall()
    conn.close()
    
    if not debts:
        update.message.reply_text("У вас нет активных долгов.")
        return
    
    message = "Ваши активные долги:\n\n"
    for amount, due_date, creation_date in debts:
        message += (
            f"Сумма: {amount:.2f}\n"
            f"Дата возврата: {due_date}\n"
            f"Дата взятия: {creation_date}\n\n"
        )
    
    update.message.reply_text(message)

def process_borrow(update: Update, user_id: int, text: str):
    try:
        parts = text.split()
        amount = float(parts[1])
        due_date_index = parts.index('до') + 1
        due_date = parts[due_date_index]
        
        day, month = map(int, due_date.split('.'))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError("Некорректная дата")
        
        total_balance = get_total_balance()
        if amount > total_balance:
            update.message.reply_text(
                f"Недостаточно средств в общем балансе. Максимальная сумма для займа: {total_balance:.2f}"
            )
            return
        
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO debts (user_id, amount, due_date, creation_date)
        VALUES (?, ?, ?, ?)
        ''', (user_id, amount, due_date, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        cursor.execute('UPDATE savings SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
        
        conn.commit()
        conn.close()
        
        update.message.reply_text(
            f"Вы взяли в долг {amount:.2f} до {due_date}. Ваш текущий баланс: {get_user_balance(user_id):.2f}"
        )
    except (ValueError, IndexError) as e:
        print(f"Ошибка: {e}")
        update.message.reply_text("Некорректный формат сообщения. Пример: 'беру 500 до 15.07'")

def process_return(update: Update, user_id: int, text: str):
    try:
        parts = text.split()
        amount = float(parts[1])
        due_date_index = parts.index('за') + 1
        due_date = parts[due_date_index]
        
        day, month = map(int, due_date.split('.'))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError("Некорректная дата")
        
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT debt_id, amount FROM debts 
        WHERE user_id = ? AND due_date = ? AND status = 'active'
        ''', (user_id, due_date))
        
        debt = cursor.fetchone()
        
        if not debt:
            update.message.reply_text("Не найден активный долг с указанной датой возврата.")
            conn.close()
            return
            
        debt_id, debt_amount = debt
        
        if amount > debt_amount:
            update.message.reply_text(f"Сумма возврата превышает сумму долга ({debt_amount:.2f})")
            conn.close()
            return
        
        if amount == debt_amount:
            cursor.execute('UPDATE debts SET status = "returned" WHERE debt_id = ?', (debt_id,))
        else:
            cursor.execute('UPDATE debts SET amount = amount - ? WHERE debt_id = ?', (amount, debt_id))
        
        cursor.execute('UPDATE savings SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        
        conn.commit()
        conn.close()
        
        update.message.reply_text(
            f"Вы вернули {amount:.2f} за {due_date}. Ваш текущий баланс: {get_user_balance(user_id):.2f}"
        )
    except (ValueError, IndexError) as e:
        print(f"Ошибка: {e}")
        update.message.reply_text("Некорректный формат сообщения. Пример: 'возвращаю 500 за 15.07'")

# Обработка текстовых сообщений
def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    if text.startswith('беру') and 'до' in text:
        process_borrow(update, user_id, text)
    elif text.startswith('возвращаю') and 'за' in text:
        process_return(update, user_id, text)
    elif text.startswith('вношу') or text.startswith('установить взнос'):
        process_contribution(update, user_id, text)

def main():
    init_db()
    
    # Укажите ваш токен бота
    TOKEN = os.environ.get('BOT_TOKEN')
    updater = Updater(TOKEN, use_context=True)
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.regex('^👀 Мой баланс$'), my_balance))
    dp.add_handler(MessageHandler(Filters.regex('^💰 Общий баланс$'), total_balance))
    dp.add_handler(MessageHandler(Filters.regex('^🎯 Внести в копилку$'), add_contribution))
    dp.add_handler(MessageHandler(Filters.regex('^💸 Мои взносы$'), my_contributions))
    dp.add_handler(MessageHandler(Filters.regex('^🍪 Взять в долг$'), borrow_money))
    dp.add_handler(MessageHandler(Filters.regex('^💪 Вернуть долг$'), return_debt))
    dp.add_handler(MessageHandler(Filters.regex('^🔔 Мои долги$'), my_debts))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()