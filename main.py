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
CHANNEL_ID = "@trassa993"  # ЗАМЕНИ
SUGGESTION_LINK = "https://t.me/trassa993?direct"  # ЗАМЕНИ
QUIZZES_DB = 'quizzes.db'
BASE_QUIZZES_DB = 'basequizzes.db'

HASHTAGS = [
    "#Новое_поколение", "#Игра_бога", "#Идеальный_мир", "#Голос_времени",
    "#Тринадцать_огней", "#Последняя_реальность", "#Сердце_вселенной",
    "#Точка_невозврата", "#Мастерская_47", "#внесезонов"
]

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    # Таблица для сохранённых викторин (история)
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
    # Таблица для запланированных викторин
    c.execute('''
        CREATE TABLE IF NOT EXISTS scheduled (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            question TEXT,
            options TEXT,
            correct_option_id INTEGER,
            hashtag TEXT,
            file_id TEXT,
            publish_time TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def save_scheduled(chat_id, question, options, correct_option_id, hashtag, file_id, publish_time):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO scheduled (chat_id, question, options, correct_option_id, hashtag, file_id, publish_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, question, options, correct_option_id, hashtag, file_id, publish_time.isoformat()))
    conn.commit()
    conn.close()

def get_due_quizzes():
    """Возвращает все викторины, у которых наступило время публикации"""
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
    """Возвращает все запланированные викторины пользователя"""
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        SELECT id, question, publish_time FROM scheduled WHERE chat_id = ? ORDER BY publish_time
    ''', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_user_scheduled(chat_id, quiz_id=None):
    """Удаляет викторину пользователя по ID или все"""
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    if quiz_id:
        c.execute('DELETE FROM scheduled WHERE chat_id = ? AND id = ?', (chat_id, quiz_id))
    else:
        c.execute('DELETE FROM scheduled WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

# --- ФОНОВЫЙ ПОТОК ДЛЯ ПРОВЕРКИ РАСПИСАНИЯ ---
def scheduler_loop():
    """Проверяет БД каждые 10 секунд и публикует викторины"""
    while True:
        try:
            due = get_due_quizzes()
            for row in due:
                quiz_id, chat_id, question, options, correct_option_id, hashtag, file_id, publish_time = row
                options_list = options.split('|||') if options else []
                
                try:
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
                    
        except Exception as e:
            print(f"❌ Ошибка в планировщике: {e}")
        
        time.sleep(10)  # Проверяем каждые 10 секунд

# --- ПАРСИНГ ВРЕМЕНИ ---
def parse_datetime(text):
    now = datetime.now()
    
    # Только время (20:33)
    match = re.search(r'(\d{1,2}):(\d{2})', text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now:
            dt = dt + timedelta(days=1)
        dt = dt - timedelta(hours=3)
        return dt
    
    # Дата + время (15.07 20:33)
    match = re.search(r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if match:
        day, month, hour, minute = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        dt = datetime(now.year, month, day, hour, minute)
        dt = dt - timedelta(hours=3)
        return dt
    
    # Дата + время с годом (15.07.2026 20:33)
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})', text)
    if match:
        day, month, year, hour, minute = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5))
        dt = datetime(year, month, day, hour, minute)
        dt = dt - timedelta(hours=3)
        return dt
    
    return None

# --- ПАРСИНГ ВИКТОРИНЫ ---
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
    print(f"✅ Базовый вопрос сохранён: {question[:30]}...")

def backup_base_quizzes():
    if os.path.exists(BASE_QUIZZES_DB):
        backup_name = f"base_quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(BASE_QUIZZES_DB, backup_name)
        return backup_name
    return None

# --- ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот для викторин\n\n"
        "📝 /quiz — создать викторину\n"
        "📋 /my — мои запланированные викторины\n"
        "🗑️ /cancel_all — отменить все мои викторины"
    )

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все запланированные викторины пользователя"""
    chat_id = str(update.effective_user.id)
    scheduled = get_user_scheduled(chat_id)
    
    if not scheduled:
        await update.message.reply_text("📭 У тебя нет запланированных викторин.")
        return
    
    reply = "📋 **Твои запланированные викторины:**\n\n"
    for quiz_id, question, publish_time in scheduled:
        dt = datetime.fromisoformat(publish_time) + timedelta(hours=3)  # Показываем в МСК
        reply += f"• {question[:40]}... → {dt.strftime('%d.%m %H:%M')}\n"
        reply += f"  /cancel_{quiz_id} — отменить эту\n"
    
    await update.message.reply_text(reply)

async def cancel_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет конкретную викторину по ID"""
    chat_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("❌ Укажи ID викторины: /cancel_123")
        return
    
    try:
        quiz_id = int(context.args[0])
        delete_user_scheduled(chat_id, quiz_id)
        await update.message.reply_text(f"✅ Викторина #{quiz_id} отменена.")
    except:
        await update.message.reply_text("❌ Ошибка. Проверь ID.")

async def cancel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет все викторины пользователя"""
    chat_id = str(update.effective_user.id)
    delete_user_scheduled(chat_id)
    await update.message.reply_text("✅ Все твои викторины отменены.")

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_quiz_text'
    await update.message.reply_text(
        "📝 Отправь в формате:\n"
        "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n"
        "Где * — правильный ответ\n\n"
        "Пример:\n"
        "`Как зовут персонажа (Глен; Ашра; Кацпер; Воланд*)`"
    )

                      
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ Отправь текст")
        return
    
    step = context.user_data.get('step')
    
    # --- ШАГ 1: БАЗОВЫЙ ВОПРОС (/basequiz) ---
    if step == 'waiting_for_base_quiz_text':
        parsed = parse_quiz(text)
        if parsed and len(parsed['options']) >= 2:
            save_base_quiz(parsed['question'], '|||'.join(parsed['options']), parsed['correct_option_id'])
            await update.message.reply_text(
                f"✅ Вопрос сохранён в базовую базу!\n\n"
                f"❓ {parsed['question']}\n"
                f"📊 Вариантов: {len(parsed['options'])}\n"
                f"✅ Правильный ответ: {parsed['options'][parsed['correct_option_id']]}"
            )
        else:
            await update.message.reply_text(
                "❌ Неправильный формат.\n\n"
                "Нужно: `Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n"
                "Где * — правильный ответ"
            )
        context.user_data['step'] = None
        return
    
    # --- ШАГ 2: ТЕКСТ ВИКТОРИНЫ (/quiz) ---
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
                f"❓ {parsed['question']}\n\n"
                f"✅ Правильный ответ: {parsed['options'][parsed['correct_option_id']]}\n\n"
                "🏷️ Выбери хэштег:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ Неправильный формат.\n\n"
                "Нужно: `Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n"
                "Где * — правильный ответ"
            )
        return
    
    # --- ШАГ 3: ВРЕМЯ ПУБЛИКАЦИИ ---
    if step == 'waiting_for_time':
        dt = parse_datetime(text)
        if dt:
            now = datetime.now()
            if dt < now:
                await update.message.reply_text(
                    "❌ Время уже прошло! Укажи будущее время.\n"
                    "Пример: `20:33` или `15.07 20:33`"
                )
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
                f"⏳ **Осталось:** {delay} секунд\n\n"
                "❓ " + context.user_data['quiz_data']['question'] + "\n"
                "🏷️ " + context.user_data['quiz_hashtag'] + "\n\n"
                "✅ Подтверждаешь?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ Не понял формат времени.\n\n"
                "Примеры:\n"
                "`20:33` — сегодня в 20:33\n"
                "`15.07 20:33` — 15 июля в 20:33\n"
                "`15.07.2026 20:33` — 15 июля 2026 в 20:33"
            )
        return
    
    # --- ШАГ 4: СВОЙ ХЭШТЕГ ---
    if step == 'waiting_for_custom_hashtag':
        text = text.strip()
        if not text.startswith('#'):
            text = '#' + text
        context.user_data['quiz_hashtag'] = text
        context.user_data['step'] = 'waiting_for_image'
        await update.message.reply_text(
            f"✅ Хэштег: {text}\n\n"
            "🖼️ Отправь картинку для поста.\n\n"
            "После картинки укажи время публикации (например, 20:33)"
        )
        return
    
    # --- ЛЮБОЙ ДРУГОЙ ТЕКСТ ---
    await update.message.reply_text(
        "❓ Я не понял.\n\n"
        "Доступные команды:\n"
        "/quiz — создать викторину\n"
        "/basequiz — добавить вопрос в базу\n"
        "/my — мои запланированные викторины\n"
        "/cancel_all — отменить все мои викторины\n"
        "/backup — бэкап основной базы\n"
        "/backupbase — бэкап базы вопросов"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    print(f"🔘 Нажата кнопка: {data}")
    
    # --- ВЫБОР ХЭШТЕГА ---
    if data.startswith("hashtag_"):
        hashtag = data.replace("hashtag_", "")
        
        if hashtag == "custom":
            await query.edit_message_text("✏️ Напиши свой хэштег (например, #МойХэштег)")
            context.user_data['step'] = 'waiting_for_custom_hashtag'
            return
        
        context.user_data['quiz_hashtag'] = hashtag
        context.user_data['step'] = 'waiting_for_image'
        
        await query.edit_message_text(
            f"✅ Хэштег: {hashtag}\n\n"
            "🖼️ Отправь картинку для поста.\n\n"
            "После картинки выбери действие."
        )
        return
    
    # --- ЗАПЛАНИРОВАТЬ ---
    if data == "schedule":
        context.user_data['step'] = 'waiting_for_time'
        await query.edit_message_text(
            "📅 **Укажи время публикации** (МСК):\n"
            "Например: `20:33` или `15.07 20:33`"
        )
        return
    
    # --- ПОДТВЕРЖДЕНИЕ ПУБЛИКАЦИИ (с таймером) ---
    if data == "confirm_publish":
        chat_id = str(update.effective_user.id)
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
            f"✅ Викторина запланирована на **{msk_time}** МСК!\n\n"
            f"⏳ Осталось: {delay} секунд\n\n"
            "📋 /my — посмотреть все твои викторины"
        )
        
        context.user_data.clear()
        return
    
    # --- МОМЕНТАЛЬНАЯ ПУБЛИКАЦИЯ ---
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
            caption = f"🎯 ВИКТОРИНА\n{hashtag}\n\n<a href=\"{SUGGESTION_LINK}\">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>"
            
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
                    f"✅ Викторина ОПУБЛИКОВАНА в канале!\n\n"
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
            


        
    
        
        
      
    async def handle_custom_hashtag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'waiting_for_custom_hashtag':
        return
    
    text = update.message.text.strip()
    if not text.startswith('#'):
        text = '#' + text
    
    context.user_data['quiz_hashtag'] = text
    context.user_data['step'] = 'waiting_for_image'
    
    await update.message.reply_text(
        f"✅ Хэштег: {text}\n\n"
        "🖼️ Отправь картинку для поста.\n\n"
        "После картинки укажи время публикации (например, 20:33)"
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'waiting_for_image':
        return
    
    if not update.message.photo:
        await update.message.reply_text("❌ Отправь именно картинку")
        return
    
    photo = update.message.photo[-1]
    context.user_data['file_id'] = photo.file_id
    context.user_data['step'] = 'waiting_for_time'
    
    quiz_data = context.user_data.get('quiz_data')
    hashtag = context.user_data.get('quiz_hashtag')
    
    keyboard = [
        [InlineKeyboardButton("✅ Опубликовать сейчас", callback_data="publish_now")],
        [InlineKeyboardButton("⏰ Запланировать на время", callback_data="schedule")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_publish")]
    ]
    
    await update.message.reply_text(
        f"🖼️ Картинка сохранена!\n\n"
        f"❓ {quiz_data['question']}\n"
        f"🏷️ {hashtag}\n\n"
        "Что делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    

def backup_quizzes():
    """Создаёт бэкап базы данных"""
    if os.path.exists(QUIZZES_DB):
        backup_name = f"quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(QUIZZES_DB, backup_name)
        return backup_name
    return None

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /backup — скачать бэкап базы"""
    await update.message.reply_text("💾 Создаю бэкап базы данных...")
    
    try:
        backup_file = backup_quizzes()
        
        if not backup_file or not os.path.exists(backup_file):
            await update.message.reply_text("❌ База данных не найдена или пуста.")
            return
        
        # Отправляем файл
        with open(backup_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(backup_file),
                caption="✅ Бэкап базы данных создан!"
            )
        
        # Удаляем временный файл после отправки
        os.remove(backup_file)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при создании бэкапа: {e}")

async def base_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_base_quiz_text'
    await update.message.reply_text(
        "📝 Отправь вопрос в формате:\n"
        "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n"
        "Где * — правильный ответ"
    )

async def backup_base_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Создаю бэкап базы базовых вопросов...")
    
    try:
        backup_file = backup_base_quizzes()
        if not backup_file or not os.path.exists(backup_file):
            await update.message.reply_text("❌ База базовых вопросов не найдена.")
            return
        
        with open(backup_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(backup_file),
                caption="✅ Бэкап базовых вопросов создан!"
            )
        os.remove(backup_file)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
# --- ЗАПУСК ---
def main():
    init_db()
    init_base_db()
    
    # Запускаем фоновый поток для проверки расписания
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()
    print("🔄 Планировщик запущен (проверка каждые 10 секунд)")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("my", my_quizzes))
    app.add_handler(CommandHandler("cancel_all", cancel_all))
    app.add_handler(CommandHandler("cancel", cancel_quiz))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^#'), handle_custom_hashtag))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("basequiz", base_quiz_command))
    app.add_handler(CommandHandler("backupbase", backup_base_command))
    
    print("🤖 Бот запущен!")
    print(f"📅 Текущее время (МСК): {(datetime.now() + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')}")
    app.run_polling()

if __name__ == "__main__":
    main()
