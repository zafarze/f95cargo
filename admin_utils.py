# admin_utils.py
import asyncio
from telegram.error import Forbidden, BadRequest
from config import logger, ADMIN_USER_IDS

async def notify_admins(bot, message: str, parse_mode=None): # <-- Добавлен parse_mode
    """
    Асинхронно отправляет сообщение всем админам из списка ADMIN_USER_IDS.
    """
    tasks = []
    for admin_id in ADMIN_USER_IDS:
        # (!!!) ИСПРАВЛЕНИЕ (!!!)
        # Теперь мы передаем parse_mode внутрь
        tasks.append(send_admin_message(bot, admin_id, message, parse_mode))
    
    await asyncio.gather(*tasks)

async def send_admin_message(bot, admin_id: int, message: str, parse_mode=None):
    """
    Отправляет одно сообщение админу с обработкой ошибок.
    """
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=message,
            parse_mode=parse_mode # <-- Он используется здесь
        )
        logger.info(f"Successfully notified admin {admin_id}")
    except Forbidden:
        logger.warning(f"Cannot send message to admin {admin_id}: Bot was blocked")
    except BadRequest as e:
        if "chat not found" in str(e).lower():
            logger.error(f"Network error sending to admin {admin_id}: Chat not found")
        else:
            logger.error(f"Failed to send to admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred when sending to admin {admin_id}: {e}")