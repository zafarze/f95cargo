# -*- coding: utf-8 -*-
# jobs.py
# (!!!) ИСПРАВЛЕННАЯ ВЕРСИЯ (!!!)

import asyncio
import pandas as pd
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Импорты из наших модулей
from config import logger, XLSX_FILENAME, BASE_DIR
from admin_utils import notify_admins

# (!!!) ИСПРАВЛЕНИЕ 1: ИМПОРТИРУЕМ 'get_text' ИЗ HANDLERS (!!!)
# Это исправляет баг с отправкой уведомлений только на русском языке
from handlers import get_text, process_excel_to_db

from db_utils import (
    get_dushanbe_arrivals_to_notify,
    set_dushanbe_notification_sent,
    upsert_order_from_excel,
    link_order_to_user,
    get_user,
    get_order_by_track_code
)


# === 1. ЗАДАЧА: ОПОВЕЩЕНИЕ О ПРИБЫТИИ В ДУШАНБЕ ===

async def notify_dushanbe_arrival_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Проверяет заказы, прибывшие в Душанбе, о которых еще не уведомляли,
    и отправляет сообщения пользователям.
    """
    logger.info("Job: Checking for Dushanbe arrivals in DATABASE (Postgres)...")
    
    try:
        orders_to_notify = await get_dushanbe_arrivals_to_notify()

        if not orders_to_notify:
            logger.info("Job: No new Dushanbe arrivals found in DB to notify.")
            return

        logger.info(f"Job: Found {len(orders_to_notify)} Dushanbe arrivals to notify.")
        
        notification_tasks = []
        for order in orders_to_notify:
            notification_tasks.append(
                send_notification(
                    context, 
                    order['user_id'], 
                    order['track_code'], 
                    order['language_code']
                )
            )
        
        await asyncio.gather(*notification_tasks)

    except Exception as e:
        logger.error(f"CRITICAL Notify Job Error: {e}", exc_info=True)
        try:
            await notify_admins(context.bot, f"❌ CRITICAL Notify Job Error:\n{e}")
        except Exception as admin_e:
            logger.error(f"Failed to notify admins about job error: {admin_e}")

async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id: int, track_code: str, lang: str):
    """
    (Утилита) Отправляет одно уведомление и помечает его в БД.
    """
    try:
        # (!!!) ТЕПЕРЬ ЭТА ФУНКЦИЯ 'get_text' РАБОТАЕТ ПРАВИЛЬНО ДЛЯ ВСЕХ ЯЗЫКОВ (!!!)
        # Получаем текст на языке пользователя
        message_text = get_text('dushanbe_arrival_notification', lang).format(code=track_code)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode=ParseMode.HTML
        )
        
        # Если отправка удалась, помечаем в БД
        await set_dushanbe_notification_sent(track_code)
        logger.info(f"Successfully notified user {user_id} for track_code {track_code}")
        
    except Exception as e:
        logger.warning(f"Failed to send Dushanbe notification to {user_id} for {track_code}: {e}")
        if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
            pass


# === 2. ЗАДАЧА: МИГРАЦИЯ EXCEL -> POSTGRES ===

# (!!!) ИСПРАВЛЕНИЕ 2: СТАРЫЙ ПАРСЕР УДАЛЕН (!!!)
# Старая функция 'load_excel_data' и 'migrate_excel_to_db' удалены.
# Мы будем использовать единую функцию 'process_excel_to_db' из handlers.py,
# чтобы гарантировать, что и ручная, и автоматическая загрузка
# работают АБСОЛЮТНО ОДИНАКОВО.

async def reload_codes_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    (Главная функция Job) Запускает миграцию Excel -> DB.
    """
    logger.info(f"Job: Starting background data migration from Excel ({XLSX_FILENAME})...")
    
    file_path = str(BASE_DIR / XLSX_FILENAME) # Путь к файлу
    
    try:
        # (!!!) ИСПОЛЬЗУЕМ ЕДИНЫЙ ПАРСЕР ИЗ HANDLERS (!!!)
        stats = await process_excel_to_db(file_path)
        
        logger.info(f"Job: Background data migration finished. Stats: {stats}")
        
        if 'error' in stats:
             await notify_admins(
                context.bot,
                f"⚠️ Ошибка миграции Excel (Фон):\n"
                f"<code>{stats['error']}</code>"
            )
        elif stats.get('failed', 0) > 0:
            await notify_admins(
                context.bot,
                f"⚠️ Ошибка миграции Excel (Фон):\n"
                f"Не удалось обработать {stats['failed']} из {stats['total']} строк.\n"
                f"См. `bot.log` для деталей."
            )
            
    except FileNotFoundError:
        logger.error(f"CRITICAL Migration Job Error: Файл {file_path} не найден!")
        await notify_admins(context.bot, f"❌ CRITICAL Migration Job Error:\nФайл {XLSX_FILENAME} не найден на сервере!")
    except Exception as e:
        logger.error(f"CRITICAL Migration Job Error: {e}", exc_info=True)
        try:
            await notify_admins(context.bot, f"❌ CRITICAL Migration Job Error:\n{e}")
        except Exception as admin_e:
            logger.error(f"Failed to notify admins about migration error: {admin_e}")