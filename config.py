# -*- coding: utf-8 -*-
# config.py
# (!!!) ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ (!!!)

import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# --- Настройка логирования ---
logger = logging.getLogger(__name__)

# --- Определение путей ---
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'

# --- Загрузка .env ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_TOKEN не найден в .env файле!")
    sys.exit(1)
else:
    logger.info("✅ TELEGRAM_TOKEN загружен успешно")

# --- База данных ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: DATABASE_URL не найден в .env!")
    sys.exit(1)
else:
    logger.info("✅ DATABASE_URL загружен успешно")

# --- ID Администраторов ---
ADMIN_USER_IDS = [
    515809298,   # Zafar
    1009549613,   # Firdavs

]

logger.info(f"✅ Загружено {len(ADMIN_USER_IDS)} ID администраторов")

# --- Настройки Файлов ---
XLSX_FILENAME = "f95cargo.xlsx"
BACKUP_DIR = "backups"
ACTIVE_USERS_STATS = "active_users"
CHANNEL_USERNAME = "@f95cargo"

# --- Создание необходимых директорий ---
try:
    BACKUP_DIR_PATH = BASE_DIR / BACKUP_DIR
    BACKUP_DIR_PATH.mkdir(exist_ok=True)
    logger.info(f"✅ Директория бэкапов создана: {BACKUP_DIR_PATH}")
except Exception as e:
    logger.warning(f"⚠️ Не удалось создать директорию бэкапов: {e}")

# --- Пути к файлам (Фото) ---
PHOTO_FILES = {
    "contact_ru": "img/contact_ru.png",
    "contact_en": "img/contact_en.png",
    "contact_tg": "img/contact_tj.png",
    "price_ru": "img/price_ru.png",
    "price_en": "img/price_en.png",
    "price_tg": "img/price_tj.png",
    "price": "price.jpg",
    "address_tajik": "img/address_tajik.jpg",
    "address_china": "img/address_china.jpeg"
}

# Языковые фото контактов
PHOTO_CONTACT_PATH_RU = BASE_DIR / PHOTO_FILES["contact_ru"]
PHOTO_CONTACT_PATH_EN = BASE_DIR / PHOTO_FILES["contact_en"]
PHOTO_CONTACT_PATH_TG = BASE_DIR / PHOTO_FILES["contact_tg"]
# Обратная совместимость — по умолчанию русская
PHOTO_CONTACT_PATH = PHOTO_CONTACT_PATH_RU

# Языковые фото тарифов
PHOTO_PRICE_PATH_RU = BASE_DIR / PHOTO_FILES["price_ru"]
PHOTO_PRICE_PATH_EN = BASE_DIR / PHOTO_FILES["price_en"]
PHOTO_PRICE_PATH_TG = BASE_DIR / PHOTO_FILES["price_tg"]
# Обратная совместимость
PHOTO_PRICE_PATH = PHOTO_PRICE_PATH_RU

PHOTO_ADDRESS_TAJIK_PATH = BASE_DIR / PHOTO_FILES["address_tajik"]
PHOTO_ADDRESS_CHINA_PATH = BASE_DIR / PHOTO_FILES["address_china"]

# Проверяем существование фото файлов
for photo_name, photo_path in [
    ("Контакты RU", PHOTO_CONTACT_PATH_RU),
    ("Контакты EN", PHOTO_CONTACT_PATH_EN),
    ("Контакты TG", PHOTO_CONTACT_PATH_TG),
    ("Тарифы RU", PHOTO_PRICE_PATH_RU),
    ("Тарифы EN", PHOTO_PRICE_PATH_EN),
    ("Тарифы TG", PHOTO_PRICE_PATH_TG),
    ("Адрес Таджикистан", PHOTO_ADDRESS_TAJIK_PATH),
    ("Адрес Китай", PHOTO_ADDRESS_CHINA_PATH)
]:
    if photo_path.exists():
        logger.info(f"✅ Фото {photo_name}: {photo_path.name} - найден")
    else:
        logger.warning(f"⚠️ Фото {photo_name}: {photo_path.name} - НЕ НАЙДЕН!")
        logger.warning(f"   Полный путь: {photo_path}")

# --- Настройки JobQueue (Фоновые задачи) ---
JOBS = {
    'reload_codes': {
        'enabled': True,  # (!!!) УСТАНОВЛЕНО В True (!!!)
        'interval': 300,  # Каждые 300 сек = 5 минут
        'first': 10       # Запустить через 10 сек после старта бота
    },
    'notify_dushanbe': {
        'enabled': True,
        'interval': 300,  # Каждые 300 сек = 5 минут
        'first': 15       # Запустить через 15 сек после старта бота
    }
}

logger.info("✅ Настройки фоновых задач загружены")

# --- Состояния для ConversationHandler (Логика диалогов) ---
# (!!!) ИСПРАВЛЕННЫЙ БЛОК (!!!)
(
    START_ROUTES,          # 0
    AWAITING_SUBSCRIPTION, # 1

    # --- ГЛАВНЫЕ СОСТОЯНИЯ ---
    MAIN_MENU,             # 2
    LK_MENU,               # 3
    ADMIN_MENU,            # 4

    # --- РЕГИСТРАЦИЯ ---
    AWAITING_FULL_NAME,    # 5
    AWAITING_PHONE,        # 6
    AWAITING_ADDRESS,      # 7
    AWAITING_LANG_CHOICE,  # 8

    # --- ОТСЛЕЖИВАНИЕ ЗАКАЗА ---
    AWAITING_TRACK_CODE,   # 9

    # --- ЛИЧНЫЙ КАБИНЕТ (ЛК) ---
    LK_AWAIT_DELIVERY_ADDRESS, # 10
    LK_AWAIT_PROFILE_ADDRESS,  # 11
    LK_AWAIT_PHONE,            # 12

    # --- АДМИН-ПАНЕЛЬ ---
    AWAITING_BROADCAST_MESSAGE, # 13
    CONFIRM_BROADCAST,          # 14
    ADMIN_AWAIT_SEARCH_CODE,    # 15

    # (!!!) УПРОЩЕННЫЕ СОСТОЯНИЯ ДЛЯ ДОБАВЛЕНИЯ ЗАКАЗА (!!!)
    ADMIN_AWAIT_ORDER_CODE,     # 16
    ADMIN_AWAIT_ORDER_STATUS,   # 17
    ADMIN_AWAIT_ORDER_DATE_YIWU, # 18
    ADMIN_AWAIT_ORDER_DATE_DUSH  # 19

) = range(20) # (!!!) ИЗМЕНЕНО на 20 (!!!)

# (!!!) ИЗМЕНЕНО на 20 (!!!)
logger.info(f"✅ Загружено {20} состояний ConversationHandler")

# --- Функция для проверки конфигурации ---
def check_config():
    """Проверяет всю конфигурацию и возвращает результат."""
    issues = []

    if not BOT_TOKEN:
        issues.append("❌ TELEGRAM_TOKEN не установлен")

    if not DATABASE_URL:
        issues.append("❌ DATABASE_URL не установлен")

    missing_photos = []
    for name, path in [
        ("Контакты RU", PHOTO_CONTACT_PATH_RU),
        ("Контакты EN", PHOTO_CONTACT_PATH_EN),
        ("Контакты TG", PHOTO_CONTACT_PATH_TG),
        ("Тарифы", PHOTO_PRICE_PATH),
        ("Адрес Таджикистан", PHOTO_ADDRESS_TAJIK_PATH),
        ("Адрес Китай", PHOTO_ADDRESS_CHINA_PATH)
    ]:
        if not path.exists():
            missing_photos.append(f"❌ {name}: {path.name}")

    if missing_photos:
        issues.append("Отсутствуют файлы изображений:")
        issues.extend(missing_photos)

    # (!!!) Эта проверка больше не критична, но оставим ее (!!!)
    xlsx_path = BASE_DIR / XLSX_FILENAME
    if not xlsx_path.exists():
        issues.append(f"⚠️ Excel файл не найден: {XLSX_FILENAME}")

    return issues

# --- Автопроверка при импорте ---
if __name__ != "__main__":
    config_issues = check_config()
    if config_issues:
        logger.warning("⚠️ Обнаружены проблемы в конфигурации:")
        for issue in config_issues:
            logger.warning(f"   {issue}")
    else:
        logger.info("✅ Конфигурация проверена - все критически важные параметры установлены")

# --- Информация о конфигурации ---
logger.info("=" * 50)
logger.info("🎯 КОНФИГУРАЦИЯ ЗАГРУЖЕНА")
logger.info(f"📁 Рабочая директория: {BASE_DIR}")
logger.info(f"🤖 Токен бота: {'✅ Установлен' if BOT_TOKEN else '❌ Отсутствует'}")
logger.info(f"🗄️  База данных: {'✅ PostgreSQL' if DATABASE_URL else '❌ Не настроена'}")
logger.info(f"👑 Админы: {len(ADMIN_USER_IDS)} пользователей")
logger.info(f"📊 Фоновые задачи: {sum(1 for job in JOBS.values() if job['enabled'])} активны")
logger.info("=" * 50)

# Добавляем настройки для видео
VIDEO_FILES = {
    "address_tajik": "address_tajik.mov"  # Лучше писать маленькими, как в папке
}

VIDEO_ADDRESS_TAJIK_PATH = BASE_DIR / VIDEO_FILES["address_tajik"]

# Проверка наличия (для логов)
if VIDEO_ADDRESS_TAJIK_PATH.exists():
    logger.info(f"✅ Видео адреса: {VIDEO_ADDRESS_TAJIK_PATH.name} - найдено")
else:
    logger.warning(f"⚠️ Видео адреса: {VIDEO_ADDRESS_TAJIK_PATH.name} - НЕ НАЙДЕНО!")