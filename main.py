import sqlite3
import os
import random
import re
import threading
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- КОНФИГ ---
BOT_TOKEN = "8798378718:AAEmRvVmnWBKCDu_sHQY8bvVhclnMwUmnFM"
DB_NAME = 'posts.db'
QUIZZES_DB = 'quizzes.db'
CHANNEL_ID = "@tryaslos"  # ЗАМЕНИ
SUGGESTION_LINK = "https://t.me/trassa993?direct"  # ЗАМЕНИ

HASHTAGS = [
    "#Новое_поколение",
    "#Игра_бога",
    "#Идеальный_мир",
    "#Голос_времени",
    "#Тринадцать_огней",
    "#Последняя_реальность",
    "#Сердце_вселенной",
    "#Точка_невозврата",
    "#Мастерская_47",
    "#внесезонов"
]

# --- БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, date TEXT)')
    conn.commit()
    conn.close()

def init_quizzes_db():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            correct_answer TEXT,
            correct_option_id INTEGER,
            hashtag TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Базы данных готовы")

def save_quiz(question, options, correct_answer, correct_option_id, hashtag=None):
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO quizzes (question, options, correct_answer, correct_option_id, hashtag, date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (question, options, correct_answer, correct_option_id, hashtag, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"✅ Викторина сохранена: {question[:30]}...")

def get_all_quizzes():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('SELECT id, question, options, correct_answer, hashtag FROM quizzes ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_random_quiz():
    conn = sqlite3.connect(QUIZZES_DB)
    c = conn.cursor()
    c.execute('SELECT question, options, correct_answer, correct_option_id, hashtag FROM quizzes ORDER BY RANDOM() LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row

# --- ПАРСИНГ ---
def parse_quiz(text):
    text = text.strip()
    match = re.match(r'^(.+?)\s*\((.+)\)\s*$', text)
    if not match:
        return None
    
    question = match.group(1).strip()
    options_raw = match.group(2).strip()
    options = [opt.strip() for opt in options_raw.split(';') if opt.strip()]
    
    if len(options) < 2:
        return None
    
    correct_answer = None
    correct_option_id = None
    cleaned_options = []
    
    for i, opt in enumerate(options):
        if opt.endswith('*'):
            correct_answer = opt[:-1].strip()
            correct_option_id = i
            cleaned_options.append(correct_answer)
        else:
            cleaned_options.append(opt)
    
    if not correct_answer and cleaned_options:
        correct_answer = cleaned_options[0]
        correct_option_id = 0
    
    return {
        "question": question,
        "options": cleaned_options,
        "correct_answer": correct_answer,
        "correct_option_id": correct_option_id
    }

# --- ПАРСИНГ ДАТЫ ---
def parse_datetime(text):
    """Парсит время и вычитает 3 часа (поправка на UTC)"""
    from datetime import timedelta
    
    patterns = [
        r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2}):(\d{2})\s+(\d{1,2})\.(\d{1,2})',
        r'(\d{1,2}):(\d{2})',  # Только время
    ]
    
    now = datetime.now()
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            
            # Только время (20:33)
            if len(groups) == 2 and all(g.isdigit() for g in groups):
                hour, minute = int(groups[0]), int(groups[1])
                dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if dt < now:
                    dt = dt + timedelta(days=1)
                # ВЫЧИТАЕМ 3 ЧАСА (поправка на UTC)
                dt = dt - timedelta(hours=3)
                return dt
            
            elif len(groups) == 3:  # 2026-07-03 20:33
                date_str, hour, minute = groups
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    dt = dt.replace(hour=int(hour), minute=int(minute))
                    dt = dt - timedelta(hours=3)
                    return dt
                except:
                    continue
                    
            elif len(groups) == 5:  # 03.07.2026 20:33
                day, month, year, hour, minute = groups
                try:
                    dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                    dt = dt - timedelta(hours=3)
                    return dt
                except:
                    continue
                    
            elif len(groups) == 4:  # 03.07 20:33 или 20:33 03.07
                if '.' in groups[0] or '.' in groups[1]:
                    if '.' in groups[0]:
                        day_month = groups[0].split('.')
                        hour, minute = int(groups[2]), int(groups[3])
                        day, month = int(day_month[0]), int(day_month[1])
                        dt = datetime(now.year, month, day, hour, minute)
                        dt = dt - timedelta(hours=3)
                        return dt
                    elif '.' in groups[2]:
                        day_month = groups[2].split('.')
                        hour, minute = int(groups[0]), int(groups[1])
                        day, month = int(day_month[0]), int(day_month[1])
                        dt = datetime(now.year, month, day, hour, minute)
                        dt = dt - timedelta(hours=3)
                        return dt
                else:
                    hour, minute = int(groups[0]), int(groups[1])
                    day, month = int(groups[2]), int(groups[3])
                    dt = datetime(now.year, month, day, hour, minute)
                    dt = dt - timedelta(hours=3)
                    return dt
    
    return None
    
# --- ФУНКЦИЯ ДЛЯ ТАЙМЕРА (ПРОСТОЙ ВАРИАНТ) ---
def publish_quiz_task(bot_token, chat_id, file_id, quiz_data, hashtag):
    """Запускается в отдельном потоке и публикует викторину"""
    try:
        # Создаём отдельный экземпляр бота для потока
        from telegram import Bot
        bot = Bot(token=bot_token)
        
        caption = (
            f"🎯 ВИКТОРИНА\n{hashtag}\n\n"
            f'<a href="{SUGGESTION_LINK}">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>'
        )
        
        # Отправляем фото
        bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=caption,
            parse_mode="HTML"
        )
        
        # Отправляем опрос
        bot.send_poll(
            chat_id=chat_id,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type="quiz",
            correct_option_id=quiz_data['correct_option_id'],
            is_anonymous=True
        )
        
        print(f"✅ Викторина опубликована в {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
    except Exception as e:
        print(f"❌ Ошибка публикации: {e}")

# --- ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот для викторин\n\n"
        "📝 **Создать викторину:** `/quiz`\n"
        "📩 **Просто текст** — сохраню в базу\n"
        "🎲 `/random` — случайная викторина\n"
        "📚 `/all` — все викторины"
    )

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
                f"❓ {parsed['question']}\n\n✅ Правильный ответ: {parsed['correct_answer']}\n\n🏷️ Выбери хэштег:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text("❌ Неправильный формат. Пример: `Вопрос (А; Б*; В; Г)`")
        return
    
    if step == 'waiting_for_time':
        dt = parse_datetime(text)
        if dt:
            now = datetime.now()
            if dt < now:
                await update.message.reply_text("❌ Нельзя указать время в прошлом!")
                return
            
            context.user_data['publish_time'] = dt
            context.user_data['step'] = 'waiting_for_confirmation'
            
            quiz_data = context.user_data.get('quiz_data')
            hashtag = context.user_data.get('quiz_hashtag')
            
            keyboard = [
                [InlineKeyboardButton("✅ Запланировать", callback_data="confirm_publish")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_publish")]
            ]
            
            await update.message.reply_text(
                f"📅 **Публикация:** {dt.strftime('%d.%m.%Y в %H:%M')} МСК\n\n"
                f"❓ {quiz_data['question']}\n"
                f"🏷️ {hashtag}\n\n"
                "✅ Подтверждаешь?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ Не понял формат времени.\n\n"
                "Примеры:\n"
                "`15.07 14:30`\n"
                "`2026-07-15 14:30`"
            )
        return
    
    # Обычный текст
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO posts (text, date) VALUES (?, ?)', (text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Текст сохранён!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("hashtag_"):
        hashtag = data.replace("hashtag_", "")
        
        if hashtag == "custom":
            await query.edit_message_text("✏️ Напиши свой хэштег (например, #МойХэштег)")
            context.user_data['step'] = 'waiting_for_custom_hashtag'
            return
        
        quiz_data = context.user_data.get('quiz_data')
        if not quiz_data:
            await query.edit_message_text("❌ Ошибка. Начни заново через /quiz")
            context.user_data.clear()
            return
        
        context.user_data['quiz_hashtag'] = hashtag
        context.user_data['step'] = 'waiting_for_image'
        
        await query.edit_message_text(
            f"✅ Хэштег: {hashtag}\n\n"
            "🖼️ Отправь картинку для поста.\n\n"
            "После картинки укажи время публикации."
        )
    
    elif data == "confirm_publish":
        quiz_data = context.user_data.get('quiz_data')
        hashtag = context.user_data.get('quiz_hashtag')
        file_id = context.user_data.get('file_id')
        publish_time = context.user_data.get('publish_time')
        
        if not quiz_data or not hashtag or not file_id or not publish_time:
            await query.edit_message_text("❌ Ошибка. Начни заново через /quiz")
            context.user_data.clear()
            return
        
        # Сохраняем в базу
        save_quiz(
            quiz_data['question'],
            ", ".join(quiz_data['options']),
            quiz_data['correct_answer'],
            quiz_data['correct_option_id'],
            hashtag
        )
        
        # Вычисляем задержку
        delay = (publish_time - datetime.now()).total_seconds()
        
        # Создаём и запускаем поток с таймером
        thread = threading.Thread(
            target=publish_quiz_task,
            args=[BOT_TOKEN, CHANNEL_ID, file_id, quiz_data, hashtag]
        )
        thread.daemon = True
        thread.start()
        
        await query.edit_message_text(
            f"✅ Викторина запланирована на **{publish_time.strftime('%d.%m.%Y в %H:%M')}** МСК!\n\n"
            f"⏳ Осталось: {int(delay)} секунд\n\n"
            "В указанное время она автоматически появится в канале. 🚀"
        )
        
        # Запускаем отдельный поток, который подождёт и опубликует
        def delayed_publish():
            # Ждём нужное время
            time.sleep(delay)
            # Публикуем
            publish_quiz_task(BOT_TOKEN, CHANNEL_ID, file_id, quiz_data, hashtag)
        
        timer_thread = threading.Thread(target=delayed_publish)
        timer_thread.daemon = True
        timer_thread.start()
        
        context.user_data.clear()
    
    elif data == "cancel_publish":
        await query.edit_message_text("❌ Публикация отменена.")
        context.user_data.clear()

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
        "После картинки укажи время публикации."
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
    
    await update.message.reply_text(
        f"🖼️ Картинка сохранена!\n\n"
        f"❓ {quiz_data['question']}\n"
        f"🏷️ {hashtag}\n\n"
        "📅 **Укажи время публикации** (МСК):\n"
        "Например: `15.07 14:30` или `14:30 15.07`"
    )

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = get_random_quiz()
    if not quiz:
        await update.message.reply_text("📭 В базе пока нет викторин")
        return
    
    question, options, correct_answer, correct_option_id, hashtag = quiz
    options_list = options.split(", ") if options else []
    
    reply = f"🎲 **Случайная викторина:**\n\n❓ {question}\n\n"
    for i, opt in enumerate(options_list, 1):
        reply += f"{i}. {opt}\n"
    reply += f"\n✅ Правильный ответ: {correct_answer}"
    if hashtag:
        reply += f"\n🏷️ {hashtag}"
    
    await update.message.reply_text(reply)

async def all_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quizzes = get_all_quizzes()
    if not quizzes:
        await update.message.reply_text("📭 В базе пока нет викторин")
        return
    
    reply = "📚 **Все викторины:**\n\n"
    for i, (id_, question, options, correct, hashtag) in enumerate(quizzes[:10], 1):
        reply += f"{i}. {question[:50]}...\n"
        if hashtag:
            reply += f"   🏷️ {hashtag}\n"
    
    await update.message.reply_text(reply)

# --- ЗАПУСК ---
def main():
    init_db()
    init_quizzes_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("random", random_quiz))
    app.add_handler(CommandHandler("all", all_quizzes))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^#'), handle_custom_hashtag))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Бот запущен!")
    print(f"📅 Текущее время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    app.run_polling()

if __name__ == "__main__":
    main()
