import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
import time

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ТОКЕН ВАШЕГО БОТА (уже вставлен)
TOKEN = "8720983024:AAE6gKTI9yp3K_KS1crrRTkA2TnK1fHs7KE"

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('calendar.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  chat_id INTEGER,
                  event_date TEXT,
                  event_time TEXT,
                  description TEXT,
                  notified INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

# Добавление события
async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Использование: /addevent ДД.ММ.ГГГГ ЧЧ:ММ Описание")
        return

    date_str = args[0]
    time_str = args[1]
    description = ' '.join(args[2:])

    try:
        event_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты/времени. Используйте ДД.ММ.ГГГГ ЧЧ:ММ")
        return

    event_date_iso = event_datetime.strftime("%Y-%m-%d")
    event_time_iso = event_datetime.strftime("%H:%M")

    conn = sqlite3.connect('calendar.db')
    c = conn.cursor()
    c.execute("INSERT INTO events (chat_id, event_date, event_time, description) VALUES (?, ?, ?, ?)",
              (chat_id, event_date_iso, event_time_iso, description))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Событие добавлено:\n📅 {date_str} {time_str}\n📝 {description}")

# Просмотр событий
async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('calendar.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT id, event_date, event_time, description FROM events
                 WHERE chat_id = ? AND event_date >= ?
                 ORDER BY event_date, event_time""", (chat_id, today))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 Нет предстоящих событий.")
        return

    message = "📋 **Предстоящие события:**\n\n"
    for row in rows:
        date_obj = datetime.strptime(row[1], "%Y-%m-%d")
        date_display = date_obj.strftime("%d.%m.%Y")
        message += f"🆔 {row[0]} | {date_display} {row[2]} — {row[3]}\n"
    await update.message.reply_text(message, parse_mode='Markdown')

# Удаление события
async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ Использование: /deleteevent ID")
        return

    try:
        event_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return

    conn = sqlite3.connect('calendar.db')
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id = ? AND chat_id = ?", (event_id, chat_id))
    if c.rowcount > 0:
        await update.message.reply_text(f"✅ Событие с ID {event_id} удалено.")
    else:
        await update.message.reply_text("❌ Событие не найдено или у вас нет прав на его удаление.")
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я семейный календарь.\n"
        "Вот что я умею:\n"
        "/addevent ДД.ММ.ГГГГ ЧЧ:ММ описание – добавить событие\n"
        "/events – список предстоящих событий\n"
        "/deleteevent ID – удалить событие\n"
        "/help – показать эту справку"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Функция проверки и отправки напоминаний
def check_reminders():
    conn = sqlite3.connect('calendar.db')
    c = conn.cursor()
    now = datetime.now()
    one_hour_later = now + timedelta(hours=1)
    now_date = now.strftime("%Y-%m-%d")
    now_time = now.strftime("%H:%M")
    later_date = one_hour_later.strftime("%Y-%m-%d")
    later_time = one_hour_later.strftime("%H:%M")

    c.execute("""SELECT id, chat_id, event_date, event_time, description FROM events
                 WHERE notified = 0 AND
                       (event_date || ' ' || event_time) BETWEEN ? AND ?""",
              (f"{now_date} {now_time}", f"{later_date} {later_time}"))
    rows = c.fetchall()

    global app
    for row in rows:
        event_id, chat_id, event_date, event_time, description = row
        date_display = datetime.strptime(event_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        text = f"⏰ **Напоминание:**\n📅 {date_display} {event_time}\n📝 {description}"
        try:
            app.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            c.execute("UPDATE events SET notified = 1 WHERE id = ?", (event_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Не удалось отправить напоминание: {e}")

    conn.close()

# Запуск планировщика
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    scheduler.start()

# Главная функция
def main():
    init_db()
    global app
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addevent", add_event))
    app.add_handler(CommandHandler("events", list_events))
    app.add_handler(CommandHandler("deleteevent", delete_event))

    import threading
    scheduler_thread = threading.Thread(target=start_scheduler, daemon=True)
    scheduler_thread.start()

    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
