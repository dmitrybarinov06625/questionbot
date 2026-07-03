import sqlite3
import os
import random
import re
import shutil
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- КОНФИГ ---
BOT_TOKEN = "8798378718:AAEmRvVmnWBKCDu_sHQY8bvVhclnMwUmnFM"
DB_NAME = 'posts.db'
QUIZZES_DB = 'quizzes.db'
CHANNEL_ID = "@trassa993"
SUGGESTION_LINK = "https://t.me/trassa993?direct"

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            date TEXT
        )
    ''')
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

def backup_quizzes():
    if os.path.exists(QUIZZES_DB):
        backup_name = f"quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(QUIZZES_DB, backup_name)
        return backup_name
    return None

def restore_quizzes(file_path):
    try:
        if os.path.exists(file_path) and file_path.endswith('.db'):
            shutil.copy2(file_path, QUIZZES_DB)
            return True
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
    return False

# --- ПАРСИНГ ВИКТОРИНЫ ---
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

async def parse_datetime(text):
    patterns = [
        r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})',
        r'(\d{1,2}):(\d{2})\s+(\d{1,2})\.(\d{1,2})',
    ]
    
    now = datetime.now()
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            
            if len(groups) == 3:
                date_str, hour, minute = groups
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    return dt.replace(hour=int(hour), minute=int(minute))
                except:
                    continue
                    
            elif len(groups) == 5:
                day, month, year, hour, minute = groups
                try:
                    return datetime(int(year), int(month), int(day), int(hour), int(minute))
                except:
                    continue
                    
            elif len(groups) == 4:
                if '.' in groups[0] or '.' in groups[1]:
                    if '.' in groups[0]:
                        day_month = groups[0].split('.')
                        hour, minute = int(groups[2]), int(groups[3])
                        day, month = int(day_month[0]), int(day_month[1])
                        return datetime(now.year, month, day, hour, minute)
                    elif '.' in groups[2]:
                        day_month = groups[2].split('.')
                        hour, minute = int(groups[0]), int(groups[1])
                        day, month = int(day_month[0]), int(day_month[1])
                        return datetime(now.year, month, day, hour, minute)
                else:
                    hour, minute = int(groups[0]), int(groups[1])
                    day, month = int(groups[2]), int(groups[3])
                    return datetime(now.year, month, day, hour, minute)
    
    return None

async def publish_quiz(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    quiz_data = job_data['quiz_data']
    hashtag = job_data['hashtag']
    file_id = job_data['file_id']
    
    try:
        caption = (
            f"Викторина\n{hashtag}\n\n"
            f'<a href="{SUGGESTION_LINK}">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>'
        )
        
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=caption,
            parse_mode="HTML"
        )
        
        await context.bot.send_poll(
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
        "📝 **Как создать викторину:**\n"
        "1. Напиши `/quiz`\n"
        "2. Отправь в формате:\n"
        "   `Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n\n"
        "3. Выбери хэштег\n"
        "4. Отправь картинку\n"
        "5. **Укажи время публикации**\n"
        "6. Бот опубликует **опрос** в канал в указанное время!\n\n"
        "🎲 `/random` — случайная викторина\n"
        "📚 `/all` — все викторины\n"
        "💾 `/backup_quizzes` — скачать бэкап"
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_for_quiz_text'
    await update.message.reply_text(
        "📝 Отправь викторину в формате:\n\n"
        "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n\n"
        "Где * — правильный ответ\n\n"
        "Пример:\n"
        "`Как зовут персонажа (Глен; Ашра; Кацпер; Воланд*)`"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ Отправь мне текст")
        return
    
    step = context.user_data.get('step')
    
    if step == 'waiting_for_time':
        dt = await parse_datetime(text)
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
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_publish")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_publish")]
            ]
            
            await update.message.reply_text(
                f"📅 **Время публикации:** {dt.strftime('%d.%m.%Y в %H:%M')} МСК\n\n"
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
    
    if step == 'waiting_for_quiz_text':
        parsed = parse_quiz(text)
        
        if parsed and len(parsed['options']) >= 2:
            context.user_data['quiz_data'] = parsed
            context.user_data['step'] = 'waiting_for_hashtag'
            
            keyboard = []
            for hashtag in HASHTAGS:
                keyboard.append([InlineKeyboardButton(hashtag, callback_data=f"hashtag_{hashtag}")])
            keyboard.append([InlineKeyboardButton("✏️ Свой хэштег", callback_data="hashtag_custom")])
            
            options_preview = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(parsed['options'])])
            await update.message.reply_text(
                f"📝 **Превью викторины:**\n\n"
                f"❓ {parsed['question']}\n\n"
                f"{options_preview}\n\n"
                f"✅ Правильный ответ: {parsed['correct_answer']}\n\n"
                "🏷️ **Выбери хэштег:**",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ Неправильный формат.\n\n"
                "Нужно:\n"
                "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`"
            )
        return
    
    # Обычный текст
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO posts (text, date) VALUES (?, ?)', 
              (text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Текст сохранён в базу!")

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
        
        context.user_data['quiz_hashtag'] = hashtag
        context.user_data['step'] = 'waiting_for_image'
        
        await query.edit_message_text(
            f"✅ Хэштег: {hashtag}\n\n"
            "🖼️ **Отправь картинку** для поста.\n\n"
            "После картинки укажи время публикации."
        )
    
    elif data == "confirm_publish":
        quiz_data = context.user_data.get('quiz_data')
        hashtag = context.user_data.get('quiz_hashtag')
        file_id = context.user_data.get('file_id')
        publish_time = context.user_data.get('publish_time')
        
        if not quiz_data or not hashtag or not file_id or not publish_time:
            await query.edit_message_text("❌ Ошибка. Попробуй /quiz заново.")
            context.user_data.clear()
            return
        
        save_quiz(
            quiz_data['question'],
            ", ".join(quiz_data['options']),
            quiz_data['correct_answer'],
            quiz_data['correct_option_id'],
            hashtag
        )
        
        # Проверяем JobQueue
        if context.job_queue is None:
            await query.edit_message_text(
                "❌ Ошибка: JobQueue не инициализирован.\n"
                "Перезапусти бота."
            )
            return
        
        job_data = {
            'chat_id': CHANNEL_ID,
            'quiz_data': quiz_data,
            'hashtag': hashtag,
            'file_id': file_id
        }
        
        context.job_queue.run_once(
            publish_quiz,
            when=publish_time,
            data=job_data,
            name=f"quiz_{datetime.now().timestamp()}"
        )
        
        await query.edit_message_text(
            f"✅ Викторина запланирована на **{publish_time.strftime('%d.%m.%Y в %H:%M')}** МСК!\n\n"
            "В указанное время она автоматически появится в канале. 🚀"
        )
        
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
        "🖼️ **Отправь картинку** для поста.\n\n"
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
    
    await update.message.reply_text(
        "🖼️ Картинка сохранена!\n\n"
        "📅 **Укажи время публикации** (МСК):\n"
        "Например: `15.07 14:30` или `14:30 15.07`"
    )

async def backup_quizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Создаю бэкап викторин...")
    
    backup_file = backup_quizzes()
    if backup_file and os.path.exists(backup_file):
        try:
            with open(backup_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"quizzes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    caption="✅ Бэкап викторин создан!"
                )
            os.remove(backup_file)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при отправке: {e}")
    else:
        await update.message.reply_text("❌ База викторин не найдена")

async def restore_quizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ Отправь файл .db с викторинами")
        return
    
    document = update.message.document
    if not document.file_name.endswith('.db'):
        await update.message.reply_text("❌ Файл должен иметь расширение .db")
        return
    
    await update.message.reply_text("📥 Восстанавливаю викторины...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_path = f"restore_quizzes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        await file.download_to_drive(file_path)
        
        if restore_quizzes(file_path):
            os.remove(file_path)
            await update.message.reply_text("✅ База викторин восстановлена!")
            quizzes = get_all_quizzes()
            await update.message.reply_text(f"📊 Всего викторин в базе: {len(quizzes)}")
        else:
            await update.message.reply_text("❌ Ошибка при восстановлении")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = get_random_quiz()
    if not quiz:
        await update.message.reply_text("📭 В базе пока нет викторин")
        return
    
    question, options, correct_answer, correct_option_id, hashtag = quiz
    options_list = options.split(", ") if options else []
    
    reply = f"🎲 **Случайная викторина:**\n\n"
    reply += f"❓ {question}\n\n"
    for i, opt in enumerate(options_list, 1):
        reply += f"{i}. {opt}\n"
    reply += f"\n✅ Правильный ответ: {correct_answer}"
    reply += f"\n🏷️ {hashtag}" if hashtag else ""
    
    await update.message.reply_text(reply)

async def all_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quizzes = get_all_quizzes()
    if not quizzes:
        await update.message.reply_text("📭 В базе пока нет викторин")
        return
    
    reply = "📚 **Все викторины:**\n\n"
    for i, (id_, question, options, correct, hashtag) in enumerate(quizzes[:10], 1):
        reply += f"{i}. {question[:50]}...\n"
        reply += f"   🏷️ {hashtag}\n" if hashtag else ""
    
    await update.message.reply_text(reply)

# --- ЗАПУСК ---
# --- ЗАПУСК ---
def main():
    init_db()
    init_quizzes_db()
    
    # Создаём приложение и сразу инициализируем JobQueue
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем JobQueue через билдер
    job_queue = app.job_queue
    
    # Регистрируем все обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("random", random_quiz))
    app.add_handler(CommandHandler("all", all_quizzes))
    app.add_handler(CommandHandler("backup_quizzes", backup_quizzes_command))
    app.add_handler(CommandHandler("restore_quizzes", restore_quizzes_command))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^#'), handle_custom_hashtag))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
