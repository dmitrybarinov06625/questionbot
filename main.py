import re
import sqlite3
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- КОНФИГ ---
BOT_TOKEN = "8637399765:AAEM-WJizcYZ2kYIrQoNKJovAXZdTgNYNMU"
DB_NAME = 'quiz_data.db'

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            questions TEXT,
            hashtags TEXT,
            date TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(text, questions, hashtags=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO posts (text, questions, hashtags, date)
        VALUES (?, ?, ?, ?)
    ''', (
        text,
        json.dumps(questions, ensure_ascii=False),
        json.dumps(hashtags, ensure_ascii=False) if hashtags else None,
        datetime.now()
    ))
    conn.commit()
    conn.close()

def get_all_questions():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT questions FROM posts ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    
    all_q = []
    for row in rows:
        questions = json.loads(row[0])
        all_q.extend(questions)
    return all_q

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM posts')
    posts_count = c.fetchone()[0]
    
    c.execute('SELECT questions FROM posts')
    rows = c.fetchall()
    conn.close()
    
    questions_count = 0
    for row in rows:
        questions = json.loads(row[0])
        questions_count += len(questions)
    
    return {
        "posts": posts_count,
        "questions": questions_count
    }

# --- ЛОГИКА ВОПРОСОВ (упрощённая) ---
def extract_questions(text):
    """Вытаскивает вопросы из текста (только те, что с ?)"""
    text = text or ""
    hashtags = re.findall(r'#\w+', text)
    
    # Ищем предложения с вопросительным знаком
    pattern = r'[^.!?]*\?'
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    
    questions = [m.strip() for m in matches if len(m.strip()) > 5]
    
    # Если вопросов нет — пробуем найти вопросительные слова
    if not questions:
        word_pattern = r'(Кто|Что|Где|Когда|Куда|Откуда|Почему|Зачем|Как|Сколько|Какие?|Чей)\s+[^.!?]+'
        matches = re.findall(word_pattern, text, re.IGNORECASE | re.DOTALL)
        questions = [m.strip() + '?' for m in matches if len(m.strip()) > 5]
    
    return list(dict.fromkeys(questions))[:10], hashtags

# --- ОБРАБОТЧИКИ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для сбора вопросов.\n\n"
        "📩 **Просто отправь мне текст** (скопируй из поста) — я вытащу вопросы и сохраню в базу.\n\n"
        "📚 `/all` — показать все вопросы.\n"
        "📊 `/stats` — статистика базы."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    
    if not text:
        await update.message.reply_text("❌ Отправь мне текст с вопросами.")
        return
    
    await update.message.reply_text("🔄 Обрабатываю...")
    
    questions, hashtags = extract_questions(text)
    save_to_db(text, questions, hashtags)
    
    if questions:
        reply = f"✅ Найдено вопросов: {len(questions)}\n\n"
        for i, q in enumerate(questions, 1):
            reply += f"{i}. {q}\n"
    else:
        reply = "⚠️ В тексте не найдено вопросов. Но текст сохранён в базу."
    
    if hashtags:
        reply += f"\n🏷️ Хэштеги: {', '.join(hashtags)}"
    
    await update.message.reply_text(reply)

async def show_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    questions = get_all_questions()
    
    if not questions:
        await update.message.reply_text("📭 В базе пока нет вопросов.")
        return
    
    reply = "📚 **Все вопросы из базы:**\n\n"
    for i, q in enumerate(questions, 1):
        reply += f"{i}. {q}\n"
    
    await update.message.reply_text(reply)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    await update.message.reply_text(
        f"📊 **Статистика базы:**\n\n"
        f"📝 Постов в базе: {stats['posts']}\n"
        f"❓ Вопросов всего: {stats['questions']}"
    )

# --- ЗАПУСК ---
def main():
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("all", show_all))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
