import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8798378718:AAEmRvVmnWBKCDu_sHQY8bvVhclnMwUmnFM"
DB_NAME = 'posts.db'

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
    print("✅ База готова")

def save_post(text):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Сохраняем дату как ISO-строку
    c.execute('INSERT INTO posts (text, date) VALUES (?, ?)', 
              (text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"✅ Сохранено: {text[:30]}...")

def search_posts(word):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT text, date FROM posts WHERE text LIKE ? ORDER BY date DESC', 
              (f'%{word}%',))
    rows = c.fetchall()
    conn.close()
    
    # Конвертируем строку даты обратно в datetime
    result = []
    for text, date_str in rows:
        try:
            date_obj = datetime.fromisoformat(date_str) if date_str else None
        except:
            date_obj = None
        result.append((text, date_obj))
    return result

def get_all():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT text, date FROM posts ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    
    # Конвертируем строку даты обратно в datetime
    result = []
    for text, date_str in rows:
        try:
            date_obj = datetime.fromisoformat(date_str) if date_str else None
        except:
            date_obj = None
        result.append((text, date_obj))
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Отправь текст — сохраню.\n"
        "/find слово — поиск.\n"
        "/all — все посты."
    )

async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ Отправь текст")
        return
    save_post(text)
    await update.message.reply_text("✅ Сохранено!")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Напиши: /find слово")
        return
    
    word = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: {word}")
    
    results = search_posts(word)
    if not results:
        await update.message.reply_text(f"❌ Ничего не найдено: {word}")
        return
    
    reply = f"🔍 Найдено: {len(results)}\n\n"
    for i, (text, date_obj) in enumerate(results[:10], 1):
        if date_obj:
            date_str = date_obj.strftime("%d.%m %H:%M")
        else:
            date_str = "??"
        preview = text[:80] + "..." if len(text) > 80 else text
        reply += f"{i}. {preview} ({date_str})\n"
    
    await update.message.reply_text(reply)

async def all_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    posts = get_all()
    if not posts:
        await update.message.reply_text("📭 Нет постов")
        return
    
    reply = f"📚 Всего: {len(posts)}\n\n"
    for i, (text, date_obj) in enumerate(posts[:10], 1):
        if date_obj:
            date_str = date_obj.strftime("%d.%m %H:%M")
        else:
            date_str = "??"
        preview = text[:80] + "..." if len(text) > 80 else text
        reply += f"{i}. {preview} ({date_str})\n"
    
    await update.message.reply_text(reply)

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("all", all_posts))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
