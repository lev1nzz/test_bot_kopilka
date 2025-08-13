import os
from dotenv import load_dotenv
load_dotenv()

import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext


ADMINS = [1079919031]


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'savings_bot.db')


def is_admin(user_id):
    return user_id in ADMINS


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
        username TEXT,
        balance REAL DEFAULT 0,
        monthly_contribution REAL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица долгов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS debts (
        debt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
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
        username TEXT,
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
        INSERT INTO savings (user_id, username, balance, monthly_contribution)
        VALUES (?, ?, 0, 0)
        ''', (user_id, username))
        
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
        [KeyboardButton("💪 Вернуть долг"), KeyboardButton(" 🔐 Админка")]
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        
         # Получаем username из таблицы users
        cursor.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        username = user_data[0] if user_data else None
        
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
            INSERT INTO contributions (user_id, username, amount, month_year, contribution_date)
            VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, amount, month_year, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
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
        
        # Получаем username из таблицы users
        cursor.execute('SELECT username FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        username = user_data[0] if user_data else None
        
        
        cursor.execute('''
        INSERT INTO debts (user_id, username, amount, due_date, creation_date)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, amount, due_date, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
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


def admin_panel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        update.message.reply_text("🚫 У вас нет прав доступа к админ-панели")
        return
    
    keyboard = [
        [KeyboardButton("👥 Список пользователей")],
        [KeyboardButton("📊 Изменить баланс"), KeyboardButton("📝 Изменить взнос")],
        [KeyboardButton("📋 Список долгов"), KeyboardButton("✏️ Редактировать долг")],
        [KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    update.message.reply_text(
        "👮‍♂️ Админ-панель:\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

def list_users(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, last_name, join_date FROM users')
    users = cursor.fetchall()
    conn.close()
    
    message = "👥 Список пользователей:\n\n"
    for user_id, username, first_name, last_name, join_date in users:
        balance = get_user_balance(user_id)
        message += (
            f"ID: {user_id}\n"
            f"Имя: {first_name} {last_name}\n"
            f"Юзернейм: @{username}\n"
            f"Баланс: {balance:.2f}\n"
            f"Дата регистрации: {join_date}\n\n"
        )
    
    update.message.reply_text(message)

def change_balance(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    update.message.reply_text(
        "Чтобы изменить баланс пользователя, отправьте сообщение в формате:\n"
        "'баланс [ID пользователя] [новая сумма]'\n\n"
        "Например: 'баланс 123456789 5000'"
    )

def process_balance_change(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    try:
        parts = update.message.text.split()
        user_id = int(parts[1])
        new_balance = float(parts[2])
        
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('UPDATE savings SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
        conn.close()
        
        update.message.reply_text(f"✅ Баланс пользователя {user_id} изменен на {new_balance:.2f}")
    except (IndexError, ValueError) as e:
        update.message.reply_text("❌ Ошибка формата. Пример: 'баланс 123456789 5000'")

def change_contribution(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    update.message.reply_text(
        "Чтобы изменить ежемесячный взнос пользователя, отправьте сообщение в формате:\n"
        "'взнос [ID пользователя] [новая сумма]'\n\n"
        "Например: 'взнос 123456789 3000'"
    )

def process_contribution_change(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    try:
        parts = update.message.text.split()
        user_id = int(parts[1])
        new_contribution = float(parts[2])
        
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('UPDATE savings SET monthly_contribution = ? WHERE user_id = ?', (new_contribution, user_id))
        conn.commit()
        conn.close()
        
        update.message.reply_text(f"✅ Взнос пользователя {user_id} изменен на {new_contribution:.2f}")
    except (IndexError, ValueError) as e:
        update.message.reply_text("❌ Ошибка формата. Пример: 'взнос 123456789 3000'")

def list_debts(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT d.debt_id, d.user_id, u.first_name, u.last_name, d.amount, d.due_date, d.status 
    FROM debts d
    JOIN users u ON d.user_id = u.user_id
    ORDER BY d.status, d.due_date
    ''')
    
    debts = cursor.fetchall()
    conn.close()
    
    if not debts:
        update.message.reply_text("Нет активных долгов.")
        return
    
    message = "📋 Список всех долгов:\n\n"
    for debt_id, user_id, first_name, last_name, amount, due_date, status in debts:
        message += (
            f"ID долга: {debt_id}\n"
            f"Пользователь: {first_name} {last_name} (ID: {user_id})\n"
            f"Сумма: {amount:.2f}\n"
            f"Дата возврата: {due_date}\n"
            f"Статус: {'✅ Погашен' if status == 'returned' else '⚠️ Активен'}\n\n"
        )
    
    update.message.reply_text(message)

def edit_debt(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    update.message.reply_text(
        "Редактирование долга:\n"
        "1. Чтобы закрыть долг, отправьте 'закрыть [ID долга]'\n"
        "2. Чтобы изменить сумму, отправьте 'долг [ID долга] [новая сумма]'\n"
        "3. Чтобы изменить дату, отправьте 'дата [ID долга] [новая дата в формате дд.мм]'\n\n"
        "Примеры:\n"
        "'закрыть 1'\n"
        "'долг 1 1500'\n"
        "'дата 1 30.12'"
    )

def process_debt_edit(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    try:
        text = update.message.text.lower().strip()
        parts = text.split()
        if len(parts) < 2:
            raise ValueError("Недостаточно аргументов")
            
        action = parts[0]
        debt_id = int(parts[1])
        
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cursor = conn.cursor()
            
            # Проверка существования долга
            cursor.execute('SELECT 1 FROM debts WHERE debt_id = ?', (debt_id,))
            if not cursor.fetchone():
                update.message.reply_text(f"❌ Долг с ID {debt_id} не найден")
                return

            if action == 'закрыть':
                cursor.execute('UPDATE debts SET status = "returned" WHERE debt_id = ?', (debt_id,))
                conn.commit()
                update.message.reply_text(f"✅ Долг {debt_id} помечен как погашенный")
                
            elif action == 'долг':
                if len(parts) < 3:
                    raise ValueError("Не указана сумма")
                new_amount = float(parts[2])
                cursor.execute('UPDATE debts SET amount = ? WHERE debt_id = ?', (new_amount, debt_id))
                conn.commit()
                update.message.reply_text(f"✅ Сумма долга {debt_id} изменена на {new_amount:.2f}")
                
            elif action == 'дата':
                if len(parts) < 3:
                    raise ValueError("Не указана дата")
                new_date = parts[2]
                try:
                    day, month = map(int, new_date.split('.'))
                    if not (1 <= day <= 31 and 1 <= month <= 12):
                        raise ValueError("Некорректная дата")
                except:
                    raise ValueError("Формат даты должен быть ДД.ММ (например 30.12)")
                
                cursor.execute('UPDATE debts SET due_date = ? WHERE debt_id = ?', (new_date, debt_id))
                conn.commit()
                update.message.reply_text(f"✅ Дата долга {debt_id} изменена на {new_date}")
                
            else:
                update.message.reply_text("❌ Неизвестная команда. Используйте: закрыть, долг или дата")
                
        except sqlite3.Error as e:
            update.message.reply_text(f"❌ Ошибка базы данных: {str(e)}")
        finally:
            if conn:
                conn.close()
                
    except (IndexError, ValueError) as e:
        update.message.reply_text(f"❌ Ошибка: {str(e)}\nПримеры:\n'закрыть 1'\n'долг 1 1500'\n'дата 1 30.12'")

def back_to_main(update: Update, context: CallbackContext):
    user = update.effective_user
    keyboard = [
        [KeyboardButton("👀 Мой баланс"), KeyboardButton("💰 Общий баланс")],
        [KeyboardButton("🎯 Внести в копилку"), KeyboardButton("💸 Мои взносы")],
        [KeyboardButton("🍪 Взять в долг"), KeyboardButton("🔔 Мои долги")],
        [KeyboardButton("💪 Вернуть долг"), KeyboardButton("🔐 Админка")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    update.message.reply_text(
        f"Главное меню, {user.first_name}!",
        reply_markup=reply_markup
    )


# Обработка текстовых сообщений
def handle_text(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        if text.startswith(('закрыть ', 'долг ', 'дата ')):
            process_debt_edit(update, context)
            return
        
        
    if is_admin(user_id):
        if text.startswith(('баланс')):
            process_balance_change(update, context)
            return
    
    
    if is_admin(user_id):
        if text.startswith(('взнос')):
            process_contribution_change(update, context)
            return
    
    
    if text.startswith('беру') and 'до' in text:
        process_borrow(update, user_id, text)
    elif text.startswith('возвращаю') and 'за' in text:
        process_return(update, user_id, text)
    elif text.startswith('вношу') or text.startswith('установить взнос'):
        process_contribution(update, user_id, text)
    elif is_admin(user_id):
        if text == '👥 список пользователей':
            list_users(update, context)
        elif text == '📊 изменить баланс':
            change_balance(update, context)
        elif text == '📝 изменить взнос':
            change_contribution(update, context)
        elif text == '📋 список долгов':
            list_debts(update, context)
        elif text == '✏️ редактировать долг':
            edit_debt(update, context)
        elif text == '🔙 назад':
            back_to_main(update, context)
    else:
        update.message.reply_text("❌ Неизвестная команда")
            
            
def main():
    init_db()

    
    TOKEN = os.environ.get('BOT_TOKEN')
    if not TOKEN:
        print("Ошибка: не указан токен бота в переменных окружения")
        return
    
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Основные команды
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Обработчики кнопок
    dispatcher.add_handler(MessageHandler(Filters.regex('^👀 Мой баланс$'), my_balance))
    dispatcher.add_handler(MessageHandler(Filters.regex('^💰 Общий баланс$'), total_balance))
    dispatcher.add_handler(MessageHandler(Filters.regex('^🎯 Внести в копилку$'), add_contribution))
    dispatcher.add_handler(MessageHandler(Filters.regex('^💸 Мои взносы$'), my_contributions))
    dispatcher.add_handler(MessageHandler(Filters.regex('^🍪 Взять в долг$'), borrow_money))
    dispatcher.add_handler(MessageHandler(Filters.regex('^💪 Вернуть долг$'), return_debt))
    dispatcher.add_handler(MessageHandler(Filters.regex('^🔔 Мои долги$'), my_debts))
    dispatcher.add_handler(MessageHandler(Filters.regex('^🔐 Админка$'), admin_panel))
    dispatcher.add_handler(MessageHandler(Filters.regex('^👥 Список пользователей$'), list_users))
    dispatcher.add_handler(MessageHandler(Filters.regex('^📊 Изменить баланс$'), change_balance))
    dispatcher.add_handler(MessageHandler(Filters.regex('^📝 Изменить взнос$'), change_contribution))
    dispatcher.add_handler(MessageHandler(Filters.regex('^📋 Список долгов$'), list_debts))
    dispatcher.add_handler(MessageHandler(Filters.regex('^✏️ Редактировать долг$'), edit_debt))
    dispatcher.add_handler(MessageHandler(Filters.regex('^🔙 Назад$'), back_to_main))
    
    # Обработчики команд админ-панели
    dispatcher.add_handler(CommandHandler("balance", process_balance_change))
    dispatcher.add_handler(CommandHandler("vznos", process_contribution_change))
    dispatcher.add_handler(CommandHandler("zakrit", process_debt_edit))
    dispatcher.add_handler(CommandHandler("dolg", process_debt_edit))
    dispatcher.add_handler(CommandHandler("data", process_debt_edit))
    
    # Обработчик текстовых сообщений
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()           
