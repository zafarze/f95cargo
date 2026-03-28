# -*- coding: utf-8 -*-
# logging_config.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Настраивает систему логирования для всего приложения."""
    
    # Определяем базовую директорию (где лежит этот файл)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_DIR = os.path.join(BASE_DIR, 'logs')

    # Создаем папку 'logs', если ее нет
    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except OSError as e:
            # Обработка случая, если папка создается одновременно
            # в нескольких потоках (хотя здесь это маловероятно)
            print(f"Warning: Could not create log directory {LOG_DIR}. {e}", file=sys.stderr)
            pass

    # Пути к файлам логов
    log_file = os.path.join(LOG_DIR, 'bot.log')
    error_log_file = os.path.join(LOG_DIR, 'error.log')

    # --- Настройка корневого логгера ---
    # Устанавливаем базовый уровень на DEBUG, 
    # чтобы обработчики могли фильтровать более детально.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Удаляем все существующие обработчики, чтобы избежать дублирования
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # --- Форматтер ---
    # Единый формат для всех логов
    formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # --- 1. Обработчик для консоли (StreamHandler) ---
    # Выводит в консоль логи уровня INFO и выше
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # --- 2. Обработчик для общего файла (RotatingFileHandler) ---
    # Пишет в bot.log ВСЕ логи уровня DEBUG и выше
    # Ротация: 5 файлов по 5 MB
    try:
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=5*1024*1024, # 5 MB
            backupCount=5, 
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except PermissionError:
        print(f"Warning: No permission to write to {log_file}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not create file handler for {log_file}. {e}", file=sys.stderr)


    # --- 3. Обработчик для файла ошибок (FileHandler) ---
    # Пишет в error.log ТОЛЬКО логи уровня ERROR и выше
    try:
        error_handler = logging.FileHandler(error_log_file, mode='a', encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
    except PermissionError:
        print(f"Warning: No permission to write to {error_log_file}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not create error handler for {error_log_file}. {e}", file=sys.stderr)


    # --- Уменьшаем "шум" от сторонних библиотек ---
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # Лог о том, что настройка завершена
    # Используем __name__, чтобы в логе было 'logging_config'
    initial_logger = logging.getLogger(__name__)
    initial_logger.info("--- (re)Logging setup complete ---")

# Важно: Эта функция должна быть определена на верхнем уровне,
# чтобы ее можно было импортировать.