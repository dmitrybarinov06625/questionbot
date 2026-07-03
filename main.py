import sqlite3
import os
import random
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- КОНФИГ ---
BOT_TOKEN = "8798378718:AAEmRvVmnWBKCDu_sHQY8bvVhclnMwUmnFM"
DB_NAME = 'posts.db'
QUIZZES_DB = 'quizzes.db'
CHANNEL_ID = "@tryaslos"  # ЗАМЕНИ НА СВОЙ КАНАЛ

# ССЫЛКА НА ПРЕДЛОЖКУ — ЗАМЕНИ НА СВОЮ!
SUGGESTION_LINK = "https://t.me/trassa993?direct"  # <-- СЮДА ВСТАВЬ СВОЮ ССЫЛКУ

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

# --- СОСТОЯНИЯ ДЛЯ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот для викторин\n\n"
        "📝 **Как создать викторину:**\n"
        "1. Напиши `/quiz`\n"
        "2. Отправь в формате:\n"
        "   `Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n\n"
        "   Где * — правильный ответ\n\n"
        "3. Выбери хэштег\n"
        "4. Отправь картинку\n"
        "5. Бот опубликует **опрос** в канал!\n\n"
        "📩 **Просто текст** — сохраню в базу\n"
        "🎲 `/random` — случайная викторина\n"
        "📚 `/all` — все викторины"
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
                "`Вопрос (Вариант 1; Вариант 2*; Вариант 3; Вариант 4)`\n\n"
                "Где * — правильный ответ"
            )
        return
    
    # --- ОБЫЧНЫЙ ТЕКСТ ---
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
            "🖼️ **Отправь картинку** для поста (обложка викторины)."
        )

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
        "🖼️ **Отправь картинку** для поста."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ЕСЛИ БОТ НЕ ЖДЁТ КАРТИНКУ — ИГНОРИРУЕМ
    if context.user_data.get('step') != 'waiting_for_image':
        # Просто игнорируем фото, если оно не нужно
        return
    
    if not update.message.photo:
        await update.message.reply_text("❌ Отправь именно картинку")
        return
    
    quiz_data = context.user_data.get('quiz_data')
    hashtag = context.user_data.get('quiz_hashtag')
    
    if not quiz_data or not hashtag:
        await update.message.reply_text("❌ Ошибка. Попробуй /quiz заново.")
        context.user_data.clear()
        return
    
    save_quiz(
        quiz_data['question'],
        ", ".join(quiz_data['options']),
        quiz_data['correct_answer'],
        quiz_data['correct_option_id'],
        hashtag
    )
    
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    await update.message.reply_text("📤 Публикую в канал...")
    
    try:
        # 1. Картинка с подписью (гиперссылка)
        caption = (
            f"🎯 ВИКТОРИНА\n{hashtag}\n\n"
            f'<a href="{SUGGESTION_LINK}">ТрясЛо №993 | Скинуть что-нибудь в предложку</a>'
        )
        
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=file_id,
            caption=caption,
            parse_mode="HTML"
        )
        
        # 2. Опрос (без объяснения)
        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type="quiz",
            correct_option_id=quiz_data['correct_option_id'],
            is_anonymous=True
        )
        
        await update.message.reply_text("✅ Викторина опубликована в канале!")
        context.user_data.clear()
        
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
    app.run_polling()

if __name__ == "__main__":
    main()
