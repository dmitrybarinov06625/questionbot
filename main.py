import time
import re
import requests
import threading
import sqlite3
import shutil
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler


# --- КОНФИГИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@trassa993"
SUGGESTION_LINK = "https://t.me/trassa993?direct"
QUIZZES_DB = 'quizzes.db'
BASE_QUIZZES_DB = 'basequizzes.db'
# --- ID ПОЛЬЗОВАТЕЛЯ ДЛЯ НАПОМИНАНИЙ ---
MEME_ADMIN_ID = "5206039766"  # ЗАМЕНИ НА РЕАЛЬНЫЙ CHAT_ID

HASHTAGS = [
    "#Новое_поколение", "#Игра_бога", "#Идеальный_мир", "#Голос_времени",
    "#Тринадцать_огней", "#Последняя_реальность", "#Сердце_вселенной",
    "#Точка_невозврата", "#Мастерская_47", "#внесезонов"
]

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    # История викторин
    c.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            correct_option_id INTEGER,
            hashtag TEXT,
            date TEXT
        )
    ''')
    # Запланированные викторины
    c.execute('''
        CREATE TABLE IF NOT EXISTS scheduled (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            username TEXT,
            question TEXT,
            options TEXT,
            correct_option_id INTEGER,
            hashtag TEXT,
            file_id TEXT,
            publish_time TEXT
        )
    ''')
    # Мемы
    c.execute('''
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            username TEXT,
            file_id TEXT,
            file_type TEXT,
            hashtag TEXT,
            publish_time TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

# --- ФУНКЦИИ ДЛЯ ВИКТОРИН ---
def save_scheduled(chat_id, username, question, options, correct_option_id, hashtag, file_id, publish_time):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO scheduled (chat_id, username, question, options, correct_option_id, hashtag, file_id, publish_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, username, question, options, correct_option_id, hashtag, file_id, publish_time.isoformat()))
    conn.commit()
    conn.close()

def get_due_quizzes():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        SELECT id, chat_id, question, options, correct_option_id, hashtag, file_id, publish_time
        FROM scheduled WHERE publish_time <= ?
    ''', (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_scheduled(quiz_id):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('DELETE FROM scheduled WHERE id = ?', (quiz_id,))
    conn.commit()
    conn.close()

def get_user_scheduled(chat_id):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        SELECT id, question, publish_time FROM scheduled WHERE chat_id = ? ORDER BY publish_time
    ''', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_scheduled_by_chat_id(chat_id):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        SELECT id, username, question, publish_time FROM scheduled WHERE chat_id = ? ORDER BY publish_time
    ''', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_scheduled_by_username(username):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        SELECT id, chat_id, username, question, publish_time FROM scheduled WHERE username = ? ORDER BY publish_time
    ''', (username,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_user_scheduled(chat_id, quiz_id=None):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    if quiz_id:
        c.execute('DELETE FROM scheduled WHERE chat_id = ? AND id = ?', (chat_id, quiz_id))
    else:
        c.execute('DELETE FROM scheduled WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

# --- ФУНКЦИИ ДЛЯ МЕМОВ ---
def save_meme(chat_id, username, file_id, file_type, hashtag, publish_time):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO memes (chat_id, username, file_id, file_type, hashtag, publish_time)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (chat_id, username, file_id, file_type, hashtag, publish_time.isoformat()))
    conn.commit()
    conn.close()

def get_due_memes():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        SELECT id, chat_id, file_id, file_type, hashtag, publish_time
        FROM memes WHERE publish_time <= ?
    ''', (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_meme(meme_id):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('DELETE FROM memes WHERE id = ?', (meme_id,))
    conn.commit()
    conn.close()

def get_user_memes(chat_id):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        SELECT id, file_type, hashtag, publish_time FROM memes WHERE chat_id = ? ORDER BY publish_time
    ''', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_user_memes(chat_id, meme_id=None):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    if meme_id:
        c.execute('DELETE FROM memes WHERE chat_id = ? AND id = ?', (chat_id, meme_id))
    else:
        c.execute('DELETE FROM memes WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

# --- НАПОМИНАЛКА ---
def get_today_memes_by_time(chat_id, target_hour, target_minute):
    """Проверяет, запланирован ли мем на конкретное время сегодня (МСК)"""
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    
    # Получаем сегодняшнюю дату в UTC (для поиска в БД)
    now_utc = datetime.now() - timedelta(hours=3)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    # Целевое время в UTC (МСК - 3 часа)
    target_utc_hour = target_hour - 3
    if target_utc_hour < 0:
        target_utc_hour += 24
    
    c.execute('''
        SELECT id FROM memes 
        WHERE chat_id = ? 
        AND publish_time >= ? 
        AND publish_time <= ?
        AND publish_time LIKE ?
    ''', (chat_id, today_start, today_end, f'%{target_utc_hour:02d}:{target_minute:02d}%'))
    rows = c.fetchall()
    conn.close()
    return rows

def send_reminder(bot_token, chat_id, time_str):
    """Отправляет напоминание пользователю"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        text = f"⚠️ **Напоминание!**\n\nТы ещё не запланировал мем!\n\n🖼️ Используй `/meme` чтобы создать и запланировать мем."
        requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })
        print(f"✅ Напоминание отправлено на {time_str}")
    except Exception as e:
        print(f"❌ Ошибка отправки напоминания: {e}")
# --- ОТДЕЛЬНЫЙ ПОТОК ДЛЯ НАПОМИНАНИЙ ---
def reminder_loop():
    """Отдельный поток для напоминаний о мемах (по времени админа UTC+5)"""
    while True:
        try:
            now_utc = datetime.now()
            
            # --- ВРЕМЯ ДЛЯ АДМИНА (UTC+5) ---
            now_admin = now_utc + timedelta(hours=5)
            current_hour = now_admin.hour
            current_minute = now_admin.minute
            today_str = now_admin.strftime('%Y-%m-%d')
            
            # --- ВРЕМЯ ДЛЯ ПОИСКА В БД (UTC) ---
            # Админское время (UTC+5) → UTC (вычитаем 5 часов)
            # Например: 12:30 по админу → 07:30 UTC
            # Но в БД хранится UTC, поэтому ищем по UTC
            reminder_times = [
                {"hour": 14, "minute": 30, "start_remind": 10, "start_minute": 5},
                {"hour": 15, "minute": 30, "start_remind": 13, "start_minute": 5},
                {"hour": 16, "minute": 30, "start_remind": 14, "start_minute": 5},
            ]
            
            for rt in reminder_times:
                # Проверяем, что сейчас время для напоминания (по админу)
                if current_hour == rt["start_remind"] and rt["start_minute"] <= current_minute <= rt["start_minute"] + 20:
                    
                    # --- ПЕРЕВОДИМ ВРЕМЯ АДМИНА В UTC (ДЛЯ ПОИСКА В БД) ---
                    # Админ 12:30 → UTC 07:30 (вычитаем 5 часов)
                    utc_hour = (rt["hour"] - 5) % 24
                    utc_minute = rt["minute"]
                    
                    # Проверяем, есть ли уже мем на это время сегодня (в БД время в UTC)
                    existing = get_today_memes_by_time(MEME_ADMIN_ID, utc_hour, utc_minute)
                    
                    if not existing:
                        if current_minute % 5 == 0:
                            send_reminder(
                                BOT_TOKEN, 
                                MEME_ADMIN_ID, 
                                f"{rt['hour']:02d}:{rt['minute']:02d} (по твоему времени)"
                            )
                            print(f"⏰ Напоминание отправлено на {rt['hour']:02d}:{rt['minute']:02d}")
            
        except Exception as e:
            print(f"❌ Ошибка в напоминалке: {e}")
        
        time.sleep(60)

# --- ФОНОВЫЙ ПОТОК ---
def scheduler_loop():
    while True:
        try:
            # --- ПРОВЕРКА ВИКТОРИН ---
            due = get_due_quizzes()
            for row in due:
                quiz_id, chat_id, question, options, correct_option_id, hashtag, file_id, publish_time = row
                options_list = options.split('|||') if options else []
                
                try:
                    caption = f"Викторина\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
                    
                    url_photo = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                    requests.post(url_photo, data={
                        "chat_id": CHANNEL_ID,
                        "photo": file_id,
                        "caption": caption,
                        "parse_mode": "HTML"
                    })
                    
                    url_poll = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPoll"
                    resp = requests.post(url_poll, json={
                        "chat_id": CHANNEL_ID,
                        "question": question,
                        "options": options_list,
                        "type": "quiz",
                        "correct_option_id": correct_option_id,
                        "is_anonymous": True
                    })
                    
                    if resp.json().get('ok'):
                        print(f"✅ Опубликовано: {question[:30]}...")
                    else:
                        print(f"❌ Ошибка: {resp.json()}")
                    
                    delete_scheduled(quiz_id)
                    
                except Exception as e:
                    print(f"❌ Ошибка публикации: {e}")
            
            # --- ПРОВЕРКА МЕМОВ ---
            due_memes = get_due_memes()
            for row in due_memes:
                meme_id, chat_id, file_id, file_type, hashtag, publish_time = row
                try:
                    caption = f"Мем\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
                    
                    if file_type == 'photo':
                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                        requests.post(url, data={
                            "chat_id": CHANNEL_ID,
                            "photo": file_id,
                            "caption": caption,
                            "parse_mode": "HTML"
                        })
                    else:
                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
                        requests.post(url, data={
                            "chat_id": CHANNEL_ID,
                            "video": file_id,
                            "caption": caption,
                            "parse_mode": "HTML"
                        })
                    
                    print(f"✅ Мем опубликован: {hashtag}")
                    delete_meme(meme_id)
                    
                except Exception as e:
                    print(f"❌ Ошибка публикации мема: {e}")
                    
        except Exception as e:
            print(f"❌ Ошибка в планировщике: {e}")
        
        time.sleep(10)

# --- ПАРСИНГИ ---
def parse_datetime(text):
    now = datetime.now()
    
    # --- ТОЛЬКО ВРЕМЯ (20:33) ---
    match = re.search(r'(\d{1,2}):(\d{2})', text)
    if match and not re.search(r'\d{1,2}\.\d{1,2}', text):
        hour, minute = int(match.group(1)), int(match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now:
            dt = dt + timedelta(days=1)
        dt = dt - timedelta(hours=3)
        return dt
    
    # --- ДАТА + ВРЕМЯ (08.07 20:33) ---
    match = re.search(r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if match:
        day, month, hour, minute = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        dt = datetime(now.year, month, day, hour, minute)
        # Если дата уже прошла в этом году — добавляем год
        if dt < now:
            # Проверяем, не сегодня ли это (тогда добавляем день)
            if dt.date() == now.date():
                dt = dt + timedelta(days=1)
            else:
                dt = dt.replace(year=now.year + 1)
        dt = dt - timedelta(hours=3)
        return dt
    
    # --- ДАТА + ВРЕМЯ С ГОДОМ (08.07.2026 20:33) ---
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})', text)
    if match:
        day, month, year, hour, minute = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5))
        dt = datetime(year, month, day, hour, minute)
        dt = dt - timedelta(hours=3)
        return dt
    
    return None

def parse_quiz(text):
    match = re.match(r'^(.+?)\s*\((.+)\)\s*$', text.strip())
    if not match:
        return None
    question = match.group(1).strip()
    options = [opt.strip() for opt in match.group(2).split(';') if opt.strip()]
    if len(options) < 2:
        return None
    correct_option_id = None
    cleaned = []
    for i, opt in enumerate(options):
        if opt.endswith('*'):
            correct_option_id = i
            cleaned.append(opt[:-1].strip())
        else:
            cleaned.append(opt)
    if correct_option_id is None:
        correct_option_id = 0
    return {"question": question, "options": cleaned, "correct_option_id": correct_option_id}

def init_base_db():
    conn = sqlite3.connect(BASE_QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS base_quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            correct_option_id INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База базовых вопросов готова")

def save_base_quiz(question, options, correct_option_id):
    conn = sqlite3.connect(BASE_QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO base_quizzes (question, options, correct_option_id, date)
        VALUES (?, ?, ?, ?)
    ''', (question, options, correct_option_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def backup_base_quizzes():
    if os.path.exists(BASE_QUIZZES_DB):
        backup_name = f"base_quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(BASE_QUIZZES_DB, backup_name)
        return backup_name
    return None

def backup_quizzes():
    if os.path.exists(QUIZZES_DB):
        backup_name = f"quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(QUIZZES_DB, backup_name)
        return backup_name
    return None

# --- ОБРАБОТЧИКИ ВИКТОРИН ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот для викторин и мемов\n\n"
        "📝 /quiz — создать викторину\n"
        "🖼️ /meme — создать мем\n"
        "📋 /my — мои запланированные викторины\n"
        "📋 /mymemes — мои запланированные мемы\n"
        "🗑️ /cancel_all — отменить все викторины\n"
        "🗑️ /cancelallmemes — отменить все мемы\n"
        "🔍 /view @username — посмотреть викторины другого пользователя\n"
        "🆔 /id — показать свой ID"
    )

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    scheduled = get_user_scheduled(chat_id)
    if not scheduled:
        await update.message.reply_text("📭 У тебя нет запланированных викторин.")
        return
    reply = "📋 **Твои запланированные викторины:**\n\n"
    for idx, (quiz_id, question, publish_time) in enumerate(scheduled, 1):
        dt = datetime.fromisoformat(publish_time) + timedelta(hours=3)
        reply += f"{idx}. {question[:40]}... → {dt.strftime('%d.%m %H:%M')}\n"
        reply += f"   🆔 {quiz_id} | /cancel_{quiz_id}\n\n"
    await update.message.reply_text(reply)

async def cancel_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("❌ Укажи ID: `/cancel 123`")
        return
    try:
        quiz_id = int(context.args[0])
        delete_user_scheduled(chat_id, quiz_id)
        await update.message.reply_text(f"✅ Викторина #{quiz_id} отменена.")
    except:
        await update.message.reply_text("❌ Ошибка. ID должен быть числом.")

async def cancel_quiz_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    try:
        number = int(update.message.text.split('_')[1])
    except:
        await update.message.reply_text("❌ Использование: `/cancel_1`, `/cancel_2`...")
        return
    scheduled = get_user_scheduled(chat_id)
    if not scheduled:
        await update.message.reply_text("📭 Нет викторин.")
        return
    if number < 1 or number > len(scheduled):
        await update.message.reply_text(f"❌ Викторины #{number} нет. Всего {len(scheduled)}.")
        return
    quiz_id = scheduled[number - 1][0]
    delete_user_scheduled(chat_id, quiz_id)
    await update.message.reply_text(f"✅ Викторина #{number} отменена.")

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    delete_user_scheduled(chat_id)
    await update.message.reply_text("✅ Все викторины отменены.")

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_quiz_text'
    await update.message.reply_text(
        "📝 Отправь в формате:\n"
        "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n"
        "Где * — правильный ответ"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "без юзернейма"
    await update.message.reply_text(f"🆔 **Твой ID:** `{user_id}`\n👤 **Юзернейм:** @{username}")

async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи: `/view @username` или `/view 123456789`")
        return
    target = context.args[0]
    if target.startswith('@'):
        username = target[1:]
        scheduled = get_user_scheduled_by_username(username)
        if not scheduled:
            await update.message.reply_text(f"📭 У @{username} нет викторин.")
            return
        chat_id = scheduled[0][1]
        reply = f"📋 **Викторины @{username}** (`{chat_id}`):\n\n"
        for idx, (quiz_id, _, question, publish_time) in enumerate(scheduled, 1):
            dt = datetime.fromisoformat(publish_time) + timedelta(hours=3)
            reply += f"{idx}. {question[:50]}... → {dt.strftime('%d.%m %H:%M')}\n"
            reply += f"   🆔 {quiz_id}\n\n"
        await update.message.reply_text(reply)
        return
    if target.isdigit():
        scheduled = get_user_scheduled_by_chat_id(target)
        if not scheduled:
            await update.message.reply_text(f"📭 У `{target}` нет викторин.")
            return
        username = scheduled[0][1] if scheduled else "без_юзернейма"
        reply = f"📋 **Викторины @{username}** (`{target}`):\n\n"
        for idx, (quiz_id, _, question, publish_time) in enumerate(scheduled, 1):
            dt = datetime.fromisoformat(publish_time) + timedelta(hours=3)
            reply += f"{idx}. {question[:50]}... → {dt.strftime('%d.%m %H:%M')}\n"
            reply += f"   🆔 {quiz_id}\n\n"
        await update.message.reply_text(reply)
        return
    await update.message.reply_text("❌ Неправильный формат.")

# --- ОБРАБОТЧИКИ МЕМОВ ---
async def start_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_meme_media'
    await update.message.reply_text(
        "🖼️ Отправь картинку или видео для мема.\n\n"
        "После загрузки выбери действие."
    )

async def handle_meme_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'waiting_for_meme_media':
        return
    file_id = None
    file_type = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = 'video'
    else:
        await update.message.reply_text("❌ Отправь картинку или видео.")
        return
    context.user_data['meme_file_id'] = file_id
    context.user_data['meme_file_type'] = file_type
    context.user_data['step'] = 'waiting_for_meme_hashtag'
    keyboard = [
        [InlineKeyboardButton("✅ Добавить #ФлудНаПМ", callback_data="meme_hashtag_add")],
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="meme_hashtag_skip")]
    ]
    await update.message.reply_text(
        "📝 Добавить хэштег #ФлудНаПМ к мему?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def meme_hashtag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "meme_hashtag_add":
        context.user_data['meme_hashtag'] = "#ФлудНаПМ"
        await query.edit_message_text("✅ Хэштег добавлен!")
    else:
        context.user_data['meme_hashtag'] = "#мемло"
        await query.edit_message_text("⏭️ Хэштег пропущен, будет только #мемло")
    context.user_data['step'] = 'waiting_for_meme_action'
    keyboard = [
        [InlineKeyboardButton("✅ Опубликовать сейчас", callback_data="meme_publish_now")],
        [InlineKeyboardButton("⏰ Запланировать на время", callback_data="meme_schedule")],
        [InlineKeyboardButton("❌ Отмена", callback_data="meme_cancel")]
    ]
    await query.message.reply_text(
        "Что делаем с мемом?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def meme_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "meme_publish_now":
        file_id = context.user_data.get('meme_file_id')
        file_type = context.user_data.get('meme_file_type')
        hashtag = context.user_data.get('meme_hashtag', '#мемло')
        if not file_id:
            await query.edit_message_text("❌ Ошибка. Начни заново через /meme")
            context.user_data.clear()
            return
        await query.edit_message_text("📤 Публикую мем сейчас...")
        try:
            caption = f"Мем\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
            if file_type == 'photo':
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                requests.post(url, data={"chat_id": CHANNEL_ID, "photo": file_id, "caption": caption, "parse_mode": "HTML"})
            else:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
                requests.post(url, data={"chat_id": CHANNEL_ID, "video": file_id, "caption": caption, "parse_mode": "HTML"})
            await query.edit_message_text(f"✅ Мем ОПУБЛИКОВАН!\n🏷️ {hashtag}")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")
        context.user_data.clear()
        return
    if data == "meme_schedule":
        context.user_data['step'] = 'waiting_for_meme_time'
        await query.edit_message_text("📅 **Укажи время публикации** (МСК):\nНапример: `20:33`")
        return
    if data == "meme_cancel":
        await query.edit_message_text("❌ Отменено.")
        context.user_data.clear()
        return

async def handle_meme_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'waiting_for_meme_time':
        return
    dt = parse_datetime(update.message.text)
    if dt is None:
        await update.message.reply_text("❌ Не понял формат. Пример: `20:33`")
        return
    now = datetime.now()
    if dt < now:
        await update.message.reply_text("❌ Время уже прошло!")
        return
    chat_id = str(update.effective_user.id)
    username = update.effective_user.username or "без_юзернейма"
    file_id = context.user_data.get('meme_file_id')
    file_type = context.user_data.get('meme_file_type')
    hashtag = context.user_data.get('meme_hashtag', '#мемло')
    save_meme(chat_id, username, file_id, file_type, hashtag, dt)
    msk_time = (dt + timedelta(hours=3)).strftime('%d.%m.%Y в %H:%M')
    delay = int((dt - now).total_seconds())
    await update.message.reply_text(f"✅ Мем запланирован на **{msk_time}** МСК!\n⏳ Осталось: {delay} сек\n🏷️ {hashtag}")
    context.user_data.clear()

async def my_memes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    memes = get_user_memes(chat_id)
    if not memes:
        await update.message.reply_text("📭 У тебя нет запланированных мемов.")
        return
    reply = "📋 **Твои запланированные мемы:**\n\n"
    for idx, (meme_id, file_type, hashtag, publish_time) in enumerate(memes, 1):
        dt = datetime.fromisoformat(publish_time) + timedelta(hours=3)
        reply += f"{idx}. {file_type} | {hashtag} → {dt.strftime('%d.%m %H:%M')}\n"
        reply += f"   🆔 {meme_id} | /cancelmeme_{meme_id}\n\n"
    await update.message.reply_text(reply)

async def cancel_meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("❌ Укажи ID: `/cancelmeme 123`")
        return
    try:
        meme_id = int(context.args[0])
        delete_user_memes(chat_id, meme_id)
        await update.message.reply_text(f"✅ Мем #{meme_id} отменён.")
    except:
        await update.message.reply_text("❌ Ошибка.")

async def cancel_meme_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    try:
        number = int(update.message.text.split('_')[1])
    except:
        await update.message.reply_text("❌ Использование: `/cancelmeme_1`, `/cancelmeme_2`...")
        return
    memes = get_user_memes(chat_id)
    if not memes:
        await update.message.reply_text("📭 Нет мемов.")
        return
    if number < 1 or number > len(memes):
        await update.message.reply_text(f"❌ Мема #{number} нет. Всего {len(memes)}.")
        return
    meme_id = memes[number - 1][0]
    delete_user_memes(chat_id, meme_id)
    await update.message.reply_text(f"✅ Мем #{number} отменён.")

async def cancel_all_memes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    delete_user_memes(chat_id)
    await update.message.reply_text("✅ Все мемы отменены.")

# --- БЭКАПЫ ---
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Создаю бэкап...")
    try:
        backup_file = backup_quizzes()
        if not backup_file:
            await update.message.reply_text("❌ База не найдена.")
            return
        with open(backup_file, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(backup_file), caption="✅ Бэкап создан!")
        os.remove(backup_file)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def base_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_base_quiz_text'
    await update.message.reply_text(
        "📝 Отправь вопрос в формате:\n"
        "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`"
    )

async def backup_base_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Создаю бэкап базы вопросов...")
    try:
        backup_file = backup_base_quizzes()
        if not backup_file:
            await update.message.reply_text("❌ База не найдена.")
            return
        with open(backup_file, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(backup_file), caption="✅ Бэкап создан!")
        os.remove(backup_file)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# --- ОСНОВНОЙ ОБРАБОТЧИК ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ Отправь текст")
        return
    
    # --- СОХРАНЯЕМ ПОЛЬЗОВАТЕЛЯ ---
    chat_id = str(update.effective_user.id)
    username = update.effective_user.username or "без_юзернейма"
    save_user(chat_id, username)
    
    step = context.user_data.get('step')
    
    # --- БАЗОВЫЙ ВОПРОС ---
    if step == 'waiting_for_base_quiz_text':
        parsed = parse_quiz(text)
        if parsed and len(parsed['options']) >= 2:
            save_base_quiz(parsed['question'], '|||'.join(parsed['options']), parsed['correct_option_id'])
            await update.message.reply_text(f"✅ Вопрос сохранён!\n❓ {parsed['question']}")
        else:
            await update.message.reply_text("❌ Неправильный формат.\nНужно: `Вопрос (А; Б*; В; Г)`")
        context.user_data['step'] = None
        return
    
    # --- ВРЕМЯ ДЛЯ МЕМА ---
    if step == 'waiting_for_meme_time':
        await handle_meme_time(update, context)
        return
    
    
    # --- ТЕКСТ ВИКТОРИНЫ ---
    if step == 'waiting_for_quiz_text':
        parsed = parse_quiz(text)
        if parsed and len(parsed['options']) >= 2:
            context.user_data['quiz_data'] = parsed
            context.user_data['step'] = 'waiting_for_hashtag'
            
            keyboard = []
            for hashtag in HASHTAGS:
                keyboard.append([InlineKeyboardButton(hashtag, callback_data=f"hashtag_{hashtag}")])
            keyboard.append([InlineKeyboardButton("✏️ Свой", callback_data="hashtag_custom")])
            
            await update.message.reply_text(
                f"❓ {parsed['question']}\n"
                f"✅ Правильный ответ: {parsed['options'][parsed['correct_option_id']]}\n\n"
                "🏷️ Выбери хэштег:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text("❌ Неправильный формат. Пример: `Вопрос (А; Б*; В; Г)`")
        return
    
    # --- ВРЕМЯ ДЛЯ ВИКТОРИНЫ ---
    if step == 'waiting_for_time':
        dt = parse_datetime(text)
        if dt is None:
            await update.message.reply_text("❌ Не понял формат. Пример: `20:33` или `08.07 20:33`")
            return
        
        now = datetime.now()
        if dt < now:
            await update.message.reply_text("❌ Время уже прошло! Укажи будущее время.")
            return
        
        context.user_data['publish_time'] = dt
        context.user_data['step'] = 'waiting_for_confirmation'
        
        delay = int((dt - now).total_seconds())
        msk_time = (dt + timedelta(hours=3)).strftime('%d.%m.%Y в %H:%M')
        
        keyboard = [
            [InlineKeyboardButton("✅ Запланировать", callback_data="confirm_publish")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_publish")]
        ]
        
        await update.message.reply_text(
            f"📅 **Публикация:** {msk_time} МСК\n"
            f"⏳ **Осталось:** {delay} сек\n\n"
            f"❓ {context.user_data['quiz_data']['question']}\n"
            f"🏷️ {context.user_data['quiz_hashtag']}\n"
            f"📝 {context.user_data.get('post_text', 'Без текста')}\n\n"
            "✅ Подтверждаешь?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # --- СВОЙ ХЭШТЕГ ---
    if step == 'waiting_for_custom_hashtag':
        text = text.strip()
        if not text.startswith('#'):
            text = '#' + text
        context.user_data['quiz_hashtag'] = text
        context.user_data['step'] = 'waiting_for_post_text'
        
        keyboard = [
            [InlineKeyboardButton("✅ Добавить текст", callback_data="add_text_yes")],
            [InlineKeyboardButton("⏭️ Без текста", callback_data="add_text_no")]
        ]
        
        await update.message.reply_text(
            f"✅ Хэштег: {text}\n\n"
            "📝 Добавить текст к посту?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # --- ЛЮБОЙ ДРУГОЙ ТЕКСТ ---
    await update.message.reply_text(
        "❓ Я не понял.\n\n"
        "Команды:\n"
        "/quiz — викторина\n"
        "/meme — мем\n"
        "/my — мои викторины\n"
        "/mymemes — мои мемы\n"
        "/cancel_all — отменить все викторины\n"
        "/cancelallmemes — отменить все мемы\n"
        "/id — мой ID\n"
        "/view @username — викторины пользователя"
    )

# --- КНОПКИ ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    print(f"🔘 Нажата кнопка: {data}")
    
    # --- ХЭШТЕГИ ДЛЯ МЕМА ---
    if data in ["meme_hashtag_add", "meme_hashtag_skip"]:
        await meme_hashtag_callback(update, context)
        return
    
    # --- КНОПКИ МЕМА ---
    if data in ["meme_publish_now", "meme_schedule", "meme_cancel"]:
        await meme_button_callback(update, context)
        return
    
    # --- ВЫБОР ХЭШТЕГА (ДЛЯ ВИКТОРИНЫ) ---
    # --- ВЫБОР ХЭШТЕГА (ДЛЯ ВИКТОРИНЫ) ---
    if data.startswith("hashtag_"):
        hashtag = data.replace("hashtag_", "")
    
        if hashtag == "custom":
            await query.edit_message_text("✏️ Напиши свой хэштег (например, #МойХэштег)")
            context.user_data['step'] = 'waiting_for_custom_hashtag'
            return
    
        context.user_data['quiz_hashtag'] = hashtag
        context.user_data['step'] = 'waiting_for_image'  # <-- СРАЗУ НА КАРТИНКУ
    
        await query.edit_message_text(
            f"✅ Хэштег: {hashtag}\n\n"
            "🖼️ Отправь картинку для поста.\n\n"
            "После картинки выбери действие."
        )
        return
  
    
    # --- ЗАПЛАНИРОВАТЬ ---
    if data == "schedule":
        context.user_data['step'] = 'waiting_for_time'
        await query.edit_message_text("📅 **Укажи время публикации** (МСК):\nНапример: `20:33`")
        return
    
    # --- ПОДТВЕРЖДЕНИЕ ПУБЛИКАЦИИ ---
    # --- ПОДТВЕРЖДЕНИЕ ПУБЛИКАЦИИ ---
    if data == "confirm_publish":
        chat_id = str(update.effective_user.id)
        username = update.effective_user.username or "без_юзернейма"
        quiz_data = context.user_data.get('quiz_data')
        hashtag = context.user_data.get('quiz_hashtag')
        file_id = context.user_data.get('file_id')
        publish_time = context.user_data.get('publish_time')
    
    if not quiz_data or not hashtag or not file_id or not publish_time:
        await query.edit_message_text("❌ Ошибка. Начни заново через /quiz")
        context.user_data.clear()
        return
    
    save_scheduled(
        chat_id,
        username,
        quiz_data['question'],
        '|||'.join(quiz_data['options']),
        quiz_data['correct_option_id'],
        hashtag,
        file_id,
        publish_time
    )
    
    msk_time = (publish_time + timedelta(hours=3)).strftime('%d.%m.%Y в %H:%M')
    delay = int((publish_time - datetime.now()).total_seconds())
    
    await query.edit_message_text(
        f"✅ Викторина запланирована на **{msk_time}** МСК!\n"
        f"⏳ Осталось: {delay} сек\n"
        f"🏷️ {hashtag}\n"
        "📋 /my — посмотреть все"
    )
        context.user_data.clear()
        return
    
    # --- МОМЕНТАЛЬНАЯ ПУБЛИКАЦИЯ ---
    # --- МОМЕНТАЛЬНАЯ ПУБЛИКАЦИЯ (для викторин) ---
   if data == "publish_now":
       quiz_data = context.user_data.get('quiz_data')
       hashtag = context.user_data.get('quiz_hashtag')
       file_id = context.user_data.get('file_id')
    
    if not quiz_data or not hashtag or not file_id:
        await query.edit_message_text("❌ Ошибка. Начни заново через /quiz")
        context.user_data.clear()
        return
    
    await query.edit_message_text("📤 Публикую викторину сейчас...")
    
    try:
        # Подпись БЕЗ текста
        caption = f"Викторина\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
        
        # Отправляем фото
        url_photo = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        requests.post(url_photo, data={
            "chat_id": CHANNEL_ID,
            "photo": file_id,
            "caption": caption,
            "parse_mode": "HTML"
        })
        
        # Отправляем опрос
        url_poll = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPoll"
        resp = requests.post(url_poll, json={
            "chat_id": CHANNEL_ID,
            "question": quiz_data['question'],
            "options": quiz_data['options'],
            "type": "quiz",
            "correct_option_id": quiz_data['correct_option_id'],
            "is_anonymous": True
        })
        
        if resp.json().get('ok'):
            conn = sqlite3.connect(QUIZZES_DB)
            c = conn.cursor()
            c.execute('''
                INSERT INTO quizzes (question, options, correct_option_id, hashtag, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (quiz_data['question'], '|||'.join(quiz_data['options']), quiz_data['correct_option_id'], hashtag, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ Викторина ОПУБЛИКОВАНА!\n\n"
                f"❓ {quiz_data['question']}\n"
                f"🏷️ {hashtag}"
            )
        else:
            await query.edit_message_text(f"❌ Ошибка: {resp.json()}")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")
    
    context.user_data.clear()
    return
    
    # --- ОТМЕНА ---
    if data == "cancel_publish":
        await query.edit_message_text("❌ Отменено.")
        context.user_data.clear()
        return
    
    await query.edit_message_text("❌ Неизвестная команда.")

# --- КАРТИНКА ДЛЯ ВИКТОРИНЫ ---
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'waiting_for_image':
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Отправь именно картинку")
        return
    
    photo = update.message.photo[-1]
    context.user_data['file_id'] = photo.file_id
    
    # Получаем данные
    hashtag = context.user_data.get('quiz_hashtag')
    quiz_data = context.user_data.get('quiz_data')
    
    # Формируем подпись БЕЗ текста
    caption = f"Викторина\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
    context.user_data['caption'] = caption
    
    keyboard = [
        [InlineKeyboardButton("✅ Опубликовать сейчас", callback_data="publish_now")],
        [InlineKeyboardButton("⏰ Запланировать на время", callback_data="schedule")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_publish")]
    ]
    
    await update.message.reply_text(
        f"🖼️ Картинка сохранена!\n\n"
        f"❓ {quiz_data['question'] if quiz_data else '?'}\n"
        f"🏷️ {hashtag}\n\n"
        "Что делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает фото и видео для викторин и мемов"""
    step = context.user_data.get('step')
    
    # Если ждём картинку для викторины
    if step == 'waiting_for_image':
        if not update.message.photo:
            await update.message.reply_text("❌ Для викторины нужна именно картинка (фото).")
            return
        await handle_image(update, context)
        return
    
    # Если ждём медиа для мема
    if step == 'waiting_for_meme_media':
        if not update.message.photo and not update.message.video:
            await update.message.reply_text("❌ Для мема нужна картинка или видео.")
            return
        await handle_meme_media(update, context)
        return
    
    # Если ничего не ждём
    await update.message.reply_text("❌ Я не жду медиа. Используй /quiz или /meme чтобы начать.")

# --- ЗАПУСК ---
def main():
    init_db()
    init_base_db()
    
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    print("🔄 Планировщик запущен")

    reminder_thread = threading.Thread(target=reminder_loop, daemon=True)
    reminder_thread.start()
    print("⏰ Напоминалка запущена")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("meme", start_meme))
    app.add_handler(CommandHandler("my", my_quizzes))
    app.add_handler(CommandHandler("mymemes", my_memes))
    app.add_handler(CommandHandler("cancel_all", cancel_all))
    app.add_handler(CommandHandler("cancelallmemes", cancel_all_memes))
    app.add_handler(CommandHandler("cancel", cancel_quiz))
    app.add_handler(CommandHandler("cancel", cancel_quiz_by_number))
    app.add_handler(CommandHandler("cancelmeme", cancel_meme))
    app.add_handler(CommandHandler("cancelmeme", cancel_meme_by_number))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("view", view_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("basequiz", base_quiz_command))
    app.add_handler(CommandHandler("backupbase", backup_base_command))
    
      # --- МЕДИА (фото и видео) - ТОЛЬКО ОДИН! ---
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))
    
    # --- ТЕКСТ (только ОДИН!) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
