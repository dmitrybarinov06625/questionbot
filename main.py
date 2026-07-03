import sqlite3
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- КОНФИГ ---
BOT_TOKEN = "8798378718:AAEmRvVmnWBKCDu_sHQY8bvVhclnMwUmnFM"
DB_NAME = 'posts.db'  # новая база

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            source TEXT,
            date TIMESTAMP
        )
    ''')
    # Создаём индекс для быстрого поиска
    c.execute('CREATE INDEX IF NOT EXISTS idx_text ON posts(text)')
    conn.commit()
    conn.close()

def save_post(text, source=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO posts (text, source, date)
        VALUES (?, ?, ?)
    ''', (text, source, datetime.now()))
    conn.commit()
    conn.close()

def search_posts(keyword):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Ищем текст, содержащий ключевое слово (регистронезависимо)
    c.execute('''
        SELECT text, source, date FROM posts
        WHERE text LIKE ?
        ORDER BY date DESC
    ''', (f'%{keyword}%',))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_posts():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT text, source, date FROM posts ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM posts')
    count = c.fetchone()[0]
    conn.close()
    return count

# --- ОБРАБОТЧИКИ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для хранения текстов.\n\n"
        "📩 **Просто отправь мне текст** — я сохраню его в базу.\n\n"
        "🔍 `/find <слово>` — найти все посты с этим словом.\n"
        "📚 `/all` — показать все сохранённые посты.\n"
        "📊 `/stats` — сколько всего постов в базе."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    if not text:
        await update.message.reply_text("❌ Отправь мне текст для сохранения.")
        return

    # Сохраняем
    save_post(text, source="от пользователя")
    await update.message.reply_text("✅ Текст сохранён в базу!")

async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи слово для поиска. Пример: `/find Чебурашка`")
        return

    keyword = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу посты со словом: **{keyword}**...")

    results = search_posts(keyword)
    if not results:
        await update.message.reply_text(f"📭 Ничего не найдено по запросу: {keyword}")
        return

    # Показываем первые 10 результатов (чтобы не заспамить)
    reply = f"🔍 **Найдено постов: {len(results)}**\n\n"
    for i, (text, source, date) in enumerate(results[:10], 1):
        # Обрезаем текст до 100 символов для краткости
        preview = text[:100] + "..." if len(text) > 100 else text
        date_str = date.strftime("%d.%m.%Y %H:%M") if date else "неизвестно"
        reply += f"{i}. {preview}\n   📅 {date_str}\n\n"

    if len(results) > 10:
        reply += f"... и ещё {len(results) - 10} постов. Для просмотра всех используй /all"

    await update.message.reply_text(reply)

async def show_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    posts = get_all_posts()
    if not posts:
        await update.message.reply_text("📭 В базе пока нет постов.")
        return

    reply = "📚 **Все сохранённые посты:**\n\n"
    for i, (text, source, date) in enumerate(posts[:20], 1):
        preview = text[:100] + "..." if len(text) > 100 else text
        date_str = date.strftime("%d.%m.%Y %H:%M") if date else "неизвестно"
        reply += f"{i}. {preview}\n   📅 {date_str}\n\n"

    if len(posts) > 20:
        reply += f"\n... и ещё {len(posts) - 20} постов."

    await update.message.reply_text(reply)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_stats()
    await update.message.reply_text(f"📊 **Всего постов в базе:** {count}")

# --- ЗАПУСК ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("all", show_all))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен! Сохраняет тексты и ищет по ключевым словам.")
    app.run_polling()

if __name__ == "__main__":
    main()
