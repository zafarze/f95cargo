# -*- coding: utf-8 -*-
# bot.py
import logging
import asyncio
import os
import sys
from pathlib import Path  # Добавлено для работы с путями
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    PicklePersistence,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# --- Настройка логов ---
from logging_config import setup_logging

# --- (!!!) ИСПРАВЛЕНИЕ: УНИВЕРСАЛЬНАЯ ЗАГРУЗКА .ENV (!!!) ---
# Этот код работает и на Windows, и на Linux
# Он ищет .env прямо в той папке, где лежит этот файл bot.py
env_path = Path(__file__).resolve().parent / '.env'

print(f"🔍 Загружаю настройки из: {env_path}") # Для отладки в консоли
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print("✅ Файл .env успешно найден и загружен.")
else:
    print("❌ Файл .env НЕ НАЙДЕН! Проверьте, что он в папке с ботом.")
# -------------------------------------------------------------

# --- Импорты из наших модулей ---
# Важно: импортируем config ПОСЛЕ загрузки .env
import config
from config import BOT_TOKEN, logger, JOBS, ADMIN_USER_IDS
from handlers import (
    get_main_conv_handler,
    get_broadcast_conv_handler,
    get_admin_conv_handler,
    document_handler,
    admin_mark_delivered,
    link_order_callback,
    error_handler
)
from jobs import (
    reload_codes_job,
    notify_dushanbe_arrival_job
)
from db_utils import init_db_pool, close_db_pool

# --- Функции управления жизненным циклом ---

async def post_init(app: Application) -> None:
    """Выполняется после инициализации приложения."""
    logger.info("Бот успешно инициализирован.")
    
    from config import (
        PHOTO_CONTACT_PATH, PHOTO_PRICE_PATH, 
        PHOTO_ADDRESS_TAJIK_PATH, PHOTO_ADDRESS_CHINA_PATH
    )
    
    photo_paths = {
        "Контакты": PHOTO_CONTACT_PATH,
        "Тарифы": PHOTO_PRICE_PATH,
        "Адрес Таджикистан": PHOTO_ADDRESS_TAJIK_PATH,
        "Адрес Китай": PHOTO_ADDRESS_CHINA_PATH
    }
    
    for name, path in photo_paths.items():
        if os.path.exists(path):
            logger.info(f"✅ Файл {name}: {path} - найден")
        else:
            logger.warning(f"❌ Файл {name}: {path} - НЕ НАЙДЕН!")

async def post_shutdown(app: Application) -> None:
    """Выполняется при остановке бота."""
    logger.info("Бот остановлен. Закрываю пул соединений Postgres...")
    await asyncio.to_thread(close_db_pool)

# --- Проверка подключения к БД ---
def check_db_connection():
    """Проверяет подключение к БД."""
    from db_utils import get_db, release_db
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            logger.info("✅ Подключение к PostgreSQL успешно")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return False
    finally:
        if conn:
            release_db(conn)

# --- Тестовые команды для диагностики ---
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки работы бота."""
    await update.message.reply_text(
        "✅ Бот работает!\n"
        "✅ Получил ваше сообщение.\n"
        "✅ Готов к работе!"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для проверки статуса бота."""
    from db_utils import get_all_users_count, execute_query
    
    try:
        users_count = await asyncio.to_thread(get_all_users_count)
        
        result = await asyncio.to_thread(
            execute_query, 
            "SELECT COUNT(*) as count FROM orders", 
            fetchone=True
        )
        orders_count = result['count'] if result else 0
        
        status_text = (
            "📊 Статус бота:\n"
            f"✅ Бот активен\n"
            f"👥 Пользователей в БД: {users_count}\n"
            f"📦 Заказов в БД: {orders_count}\n"
            f"🔄 Фоновые задачи: активны\n"
            f"🗄️ База данных: PostgreSQL"
        )
        
        await update.message.reply_text(status_text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при проверке статуса: {e}")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отладки."""
    user = update.effective_user
    debug_info = (
        "🐛 Отладочная информация:\n"
        f"ID пользователя: {user.id}\n"
        f"Имя: {user.first_name}\n"
        f"Username: @{user.username or 'N/A'}\n"
        f"Язык: {user.language_code or 'N/A'}\n"
        f"Админ: {'✅' if user.id in ADMIN_USER_IDS else '❌'}"
    )
    
    await update.message.reply_text(debug_info)

# --- Главная функция ---
def main() -> None:
    """Главная функция запуска бота."""
    
    # Настраиваем логирование
    setup_logging()
    
    logger.info("--- Запуск Бота (режим PostgreSQL) ---")

    if not BOT_TOKEN:
        logger.critical("❌ Токен бота не установлен! Проверьте .env файл")
        return

    try:
        logger.info("🔄 Инициализация пула соединений PostgreSQL...")
        init_db_pool()  
        logger.info("✅ Пул соединений Postgres и таблицы успешно инициализированы.")
        
        if not check_db_connection():
            logger.critical("❌ Не удалось подключиться к БД! Проверьте настройки в .env")
            return
            
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: Не удалось инициализировать Пул Postgres: {e}", exc_info=True)
        return

    try:
        persistence = PicklePersistence(filepath="bot_persistence.pickle")
        logger.info("✅ Persistence инициализирован")
    except Exception as e:
        logger.error(f"❌ Ошибка при создании persistence: {e}")
        persistence = None

    try:
        application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .persistence(persistence)
            .connect_timeout(60.0)  # Было 30.0
            .read_timeout(120.0)    # Было 30.0 -> Ставим 120 секунд
            .write_timeout(120.0)   # Было 30.0 -> Ставим 120 секунд
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )
        logger.info("✅ Приложение собрано успешно")
    except Exception as e:
        logger.critical(f"❌ Не удалось собрать приложение: {e}")
        return
    
    job_queue = application.job_queue
    
    if JOBS['reload_codes']['enabled']:
        try:
            job_queue.run_repeating(
                reload_codes_job,
                interval=JOBS['reload_codes']['interval'],
                first=JOBS['reload_codes']['first'],
                name="job_reload_codes"
            )
            logger.info("✅ Задача 'reload_codes' включена.")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении задачи reload_codes: {e}")

    if JOBS['notify_dushanbe']['enabled']:
        try:
            job_queue.run_repeating(
                notify_dushanbe_arrival_job,
                interval=JOBS['notify_dushanbe']['interval'],
                first=JOBS['notify_dushanbe']['first'],
                name="job_notify_dushanbe"
            )
            logger.info("✅ Задача 'notify_dushanbe' включена.")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении задачи notify_dushanbe: {e}")

    try:
        application.add_handler(MessageHandler(filters.Document.ALL, document_handler), group=0)
        
        application.add_handler(get_broadcast_conv_handler(), group=0)
        application.add_handler(get_main_conv_handler(), group=0)
        application.add_handler(get_admin_conv_handler(), group=0)
        
        application.add_handler(CommandHandler("delivered", admin_mark_delivered), group=1)
        application.add_handler(CommandHandler("test", test_command), group=1)
        application.add_handler(CommandHandler("status", status_command), group=1)
        application.add_handler(CommandHandler("debug", debug_command), group=1)
                
        application.add_handler(CallbackQueryHandler(link_order_callback, pattern='^link_'), group=1)
        
        logger.info("✅ Все обработчики добавлены успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении обработчиков: {e}")

    application.add_error_handler(error_handler)
    logger.info("✅ Обработчик ошибок добавлен")

    logger.info("--- 🚀 Бот запущен и готов к работе (polling) ---")
    
    try:
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка при запуске бота: {e}")
    finally:
        logger.info("--- Бот остановлен ---")


if __name__ == "__main__":
    main()