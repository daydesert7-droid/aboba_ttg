import os
import sys
import logging
import sqlite3
import time
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

TOKEN = os.environ.get('BOT_TOKEN', '')
if not TOKEN:
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
if not TOKEN:
    TOKEN = os.environ.get('BOTHOST_BOT_TOKEN', '')

CREATOR_ID = os.environ.get('CREATOR_ID', '')
if not CREATOR_ID:
    CREATOR_ID = os.environ.get('TELEGRAM_CREATOR_ID', '')
if not CREATOR_ID:
    CREATOR_ID = os.environ.get('BOTHOST_CREATOR_ID', '')

print("=" * 50)
print("WEBHOOK БОТ ДЛЯ BOTHOST.RU")
print("=" * 50)
print(f"Токен: {'✓ установлен' if TOKEN else '✗ НЕТ'}")
print(f"Создатель: {CREATOR_ID if CREATOR_ID else 'не указан'}")
print("=" * 50)

if not TOKEN:
    print("❌ ОШИБКА: Токен бота не найден!")
    print("Добавьте переменную BOT_TOKEN в настройках bothost.ru")
    sys.exit(1)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()

MAX_MESSAGE_LENGTH = 150
WELCOME_IMAGE_PATH = "world_start.jpg"

def format_time_remaining(hours, minutes):
    if hours > 0:
        if hours == 1 or hours == 21:
            hours_text = f"{hours} час"
        elif 2 <= hours <= 4 or 22 <= hours <= 24:
            hours_text = f"{hours} часа"
        else:
            hours_text = f"{hours} часов"
    
    if minutes > 0:
        if minutes == 1 or minutes == 21 or minutes == 31 or minutes == 41 or minutes == 51:
            minutes_text = f"{minutes} минуту"
        elif (2 <= minutes <= 4 or 22 <= minutes <= 24 or 
              32 <= minutes <= 34 or 42 <= minutes <= 44 or 
              52 <= minutes <= 54):
            minutes_text = f"{minutes} минуты"
        else:
            minutes_text = f"{minutes} минут"
    
    if hours > 0 and minutes > 0:
        return f"{hours_text} {minutes_text}"
    elif hours > 0:
        return hours_text
    elif minutes > 0:
        return minutes_text
    else:
        return "0 минут"

def init_database():
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_limits (
                user_id INTEGER PRIMARY KEY,
                last_message_time INTEGER
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

def can_send_message(user_id):
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()
        cursor.execute('SELECT last_message_time FROM user_limits WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return True
        
        last_message_time = result[0]
        current_time = int(time.time())
        
        return (current_time - last_message_time) >= 86400
    except Exception as e:
        logger.error(f"Ошибка проверки лимита: {e}")
        return False

def save_message_time(user_id):
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_limits (user_id, last_message_time)
            VALUES (?, ?)
        ''', (user_id, int(time.time())))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения времени: {e}")

def get_time_until_next_message(user_id):
    try:
        conn = sqlite3.connect('user_limits.db')
        cursor = conn.cursor()
        cursor.execute('SELECT last_message_time FROM user_limits WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            return 0, 0
        
        last_message_time = result[0]
        current_time = int(time.time())
        time_passed = current_time - last_message_time
        
        if time_passed >= 86400:
            return 0, 0
        
        time_remaining = 86400 - time_passed
        
        hours = time_remaining // 3600
        minutes = (time_remaining % 3600) // 60
        
        if time_remaining % 60 > 0:
            minutes += 1
            if minutes == 60:
                hours += 1
                minutes = 0
        
        return hours, minutes
    except Exception as e:
        logger.error(f"Ошибка получения времени: {e}")
        return 23, 59

def get_user_mention(user):
    """Создает HTML-ссылку на пользователя с отображаемым именем"""
    display_name = ""
    if user.first_name:
        display_name = user.first_name
        if user.last_name:
            display_name += f" {user.last_name}"
    else:
        display_name = user.username if user.username else f"Пользователь {user.id}"
    
    user_link = f"tg://user?id={user.id}"
    display_name = display_name.replace('<', '&lt;').replace('>', '&gt;')
    
    return f'<a href="{user_link}">{display_name}</a>'

def get_user_info_html(user):
    """Создает информационное сообщение о пользователе с ссылкой"""
    user_mention = get_user_mention(user)
    
    user_info = f"<b>Пользователь:</b> {user_mention}\n"
    user_info += f"<b>ID:</b> <code>{user.id}</code>\n"
    
    if user.username:
        user_info += f"Username: @{user.username}\n"
    
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
        user_info += f"Имя: {name}\n"
    
    return user_info

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        welcome_text = (
            '<b>Добро пожаловать!</b>\n\n'
            'Отправь мне сообщение, и оно опубликуется в канале "мир знает, что".'
        )
        
        if os.path.exists(WELCOME_IMAGE_PATH):
            try:
                with open(WELCOME_IMAGE_PATH, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=welcome_text,
                        parse_mode=ParseMode.HTML
                    )
                logger.info(f"Пользователь {update.effective_user.id} использовал /start с изображением")
            except Exception as e:
                logger.error(f"Ошибка отправки изображения: {e}")
                await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        else:
            logger.warning(f"Файл {WELCOME_IMAGE_PATH} не найден")
            await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    message_text = update.message.text
    
    try:
        if not can_send_message(user_id):
            hours, minutes = get_time_until_next_message(user_id)
            time_text = format_time_remaining(hours, minutes)
            
            limit_text = (
                f"<b>Следующее сообщение можно отправить через:</b>\n"
                f"{time_text}"
            )
            
            await update.message.reply_text(limit_text, parse_mode=ParseMode.HTML)
            logger.info(f"Пользователь {user_id} попытался отправить раньше времени")
            return

        if not message_text or message_text.isspace():
            await update.message.reply_text(
                "Сообщение не может быть пустым.", 
                parse_mode=ParseMode.HTML
            )
            return
        
        message_length = len(message_text)
        if message_length > MAX_MESSAGE_LENGTH:
            length_error = (
                f"<b>Сообщение слишком длинное.</b>\n\n"
                f"Максимально допустимо: {MAX_MESSAGE_LENGTH} символов."
            )
            await update.message.reply_text(length_error, parse_mode=ParseMode.HTML)
            logger.info(f"Пользователь {user_id} отправил слишком длинное сообщение ({message_length} символов)")
            return
        
        save_message_time(user_id)

        confirmation_text = (
            f"<b>Сообщение отправлено.</b>\n"
            f"Опубликуется в порядке очереди."
        )
        await update.message.reply_text(confirmation_text, parse_mode=ParseMode.HTML)

        user_mention = get_user_mention(user)
        
        info_message = (
            f"Новое сообщение от {user_mention}:"
        )
        
        await context.bot.send_message(
    chat_id=CREATOR_ID, 
    text=info_message,
    parse_mode=ParseMode.HTML
        )

        await context.bot.send_message(
    chat_id=CREATOR_ID, 
    text=message_text,
    parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Сообщение от пользователя {user_id} успешно обработано ({message_length} символов)")
        
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения от {user_id}: {e}")
        try:
            await update.message.reply_text(
                "<i>Произошла ошибка. Попробуйте позже.</i>", 
                parse_mode=ParseMode.HTML
            )
        except:
            pass

async def handle_unsupported_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "<b>Принимаются только текстовые сообщения.</b>", 
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка обработки неподдерживаемого сообщения: {e}")

def main():
    logger.info("Запуск бота...")
    
    init_database()
    
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, handle_unsupported_message))
    
    logger.info("Бот запущен и готов к работе!")
    print(f"Бот успешно запущен! Ограничение длины сообщений: {MAX_MESSAGE_LENGTH} символов")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()