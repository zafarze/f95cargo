# -*- coding: utf-8 -*-
# db_utils.py
# (!!!) ИСПРАВЛЕННАЯ ВЕРСИЯ (с Пулом Соединений) (!!!)

import psycopg2
import psycopg2.pool
import psycopg2.extras
import asyncio
from urllib.parse import urlparse
# Импорты из наших модулей
from config import DATABASE_URL, logger


# --- Глобальный Пул Соединений ---
pool = None

# === Управление Пулом Соединений ===

def parse_database_url(url):
    """Парсит URL базы данных (для совместимости с Heroku/Render)."""
    try:
        result = urlparse(url)
        return {
            'dbname': result.path[1:],
            'user': result.username,
            'password': result.password,
            'host': result.hostname,
            'port': result.port
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга DATABASE_URL: {e}")
        return None

def init_db_pool():
    """Инициализирует пул соединений PostgreSQL."""
    global pool
    if pool:
        logger.info("Пул соединений уже инициализирован.")
        return

    try:
        if not DATABASE_URL:
            logger.critical("DATABASE_URL не найден. Пул не может быть создан.")
            return

        db_params = parse_database_url(DATABASE_URL)
        if not db_params:
            logger.critical("Не удалось разобрать DATABASE_URL.")
            return

        logger.info("Попытка инициализации пула соединений PostgreSQL (с парсингом)...")
        
        # minconn=1, maxconn=20
        pool = psycopg2.pool.SimpleConnectionPool(1, 20, **db_params)
        
        if pool:
            logger.info("✅ Пул соединений Postgres успешно создан (с парсингом).")
            # Проверка и создание таблиц при инициализации
            conn = get_db()
            if conn:
                create_tables(conn)
                release_db(conn)
            else:
                logger.error("Не удалось получить соединение из пула для создания таблиц.")
        else:
            logger.error("❌ Не удалось создать пул соединений Postgres (pool is None).")
            
    except psycopg2.DatabaseError as e:
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к PostgreSQL. Ошибка: {e}")
        logger.critical(f"   Параметры: user={db_params.get('user')}, host={db_params.get('host')}, port={db_params.get('port')}, dbname={db_params.get('dbname')}")
    except Exception as e:
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Неизвестная ошибка при инициализации пула: {e}")

def close_db_pool():
    """Закрывает все соединения в пуле."""
    global pool
    if pool:
        try:
            pool.closeall()
            pool = None
            logger.info("Пул соединений PostgreSQL успешно закрыт.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии пула соединений: {e}")
    else:
        logger.info("Пул соединений уже был закрыт или не инициализирован.")

# (!!!) ИСПРАВЛЕННАЯ ВЕРСИЯ (!!!)
def get_db():
    """Получает соединение из пула (ПРОДАКШН ВЕРСИЯ)."""
    global pool
    if pool is None:
        logger.error("❌ Пул не инициализирован! Попытка получить соединение не удалась.")
        init_db_pool() # Попытка аварийной инициализации
        if pool is None:
             logger.critical("❌ Аварийная инициализация пула не удалась.")
             return None
    
    try:
        conn = pool.getconn()
        conn.autocommit = False 
        logger.debug("--- DIAGNOSTICS: Connection retrieved from pool ---")
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка при получении соединения из пула: {e}")
        return None

# (!!!) ИСПРАВЛЕННАЯ ВЕРСИЯ (!!!)
def release_db(conn):
    """Возвращает соединение в пул (ПРОДАКШН ВЕРСИЯ)."""
    global pool
    if conn:
        try:
            if pool:
                pool.putconn(conn)
                logger.debug("--- DIAGNOSTICS: Connection returned to pool ---")
            else:
                conn.close() # Fallback, если пул потерян
                logger.warning("--- DIAGNOSTICS: Pool not found, connection closed directly ---")
        except Exception as e:
            logger.error(f"Ошибка при возврате соединения в пул: {e}")

# === Базовая Функция Выполнения Запросов ===

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """
    Универсальная функция для выполнения SQL-запросов.
    Использует DictCursor для получения результатов в виде словаря.
    """
    conn = None
    try:
        conn = get_db()
        if conn is None:
            logger.error("Не удалось получить соединение с БД для execute_query")
            return None
            
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            
            if commit:
                conn.commit()
                logger.debug("--- COMMIT SUCCESSFUL ---")
                
                if result is not None:
                    return result 
                
                return cursor.rowcount
            
            if result is not None:
                return result
            
            return cursor.rowcount

    except psycopg2.DatabaseError as e:
        # ❌ Ключевой блок для диагностики: Логирование ROLLBACK
        error_msg = str(e)
        logger.error(f"❌ DB ERROR: Ошибка базы данных (rollback). Код: {e.pgcode}")
        logger.error(f"   Проблема может быть в кодировке/типе данных. Ошибка: {error_msg}")
        logger.error(f"   Query: {query}")
        logger.error(f"   Params: {params}")
        if conn:
            conn.rollback() # Откатываем транзакцию при ошибке
        return None
        
    except Exception as e:
        logger.error(f"❌ UNKNOWN ERROR: Неизвестная ошибка при выполнении запроса (rollback): {e}")
        if conn:
            conn.rollback()
        return None
        
    finally:
        if conn:
            release_db(conn)

# === Инициализация Таблиц ===

def create_tables(conn):
    """
    Создает таблицы users и orders, если они не существуют.
    Вызывается один раз при инициализации пула.
    """
    try:
        # (!!!) ИСПРАВЛЕНИЕ: Курсор открывается здесь (!!!)
        with conn.cursor() as cursor:
            # --- Таблица Пользователей (users) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    full_name VARCHAR(255),
                    username VARCHAR(255),
                    phone_number VARCHAR(50),
                    address TEXT,
                    language_code VARCHAR(10) DEFAULT 'ru',
                    registration_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_subscribed BOOLEAN DEFAULT FALSE,
                    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            logger.info("Таблица 'users' проверена/создана.")

            # --- Таблица Заказов (orders) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    track_code VARCHAR(100) UNIQUE NOT NULL,
                    
                    user_id BIGINT, 
                    
                    status_yiwu VARCHAR(100),
                    date_yiwu DATE,
                    
                    status_dushanbe VARCHAR(100),
                    date_dushanbe DATE,
                    
                    status_delivered VARCHAR(100),
                    date_delivered DATE,
                    
                    notify_dushanbe BOOLEAN DEFAULT FALSE,
                    notify_delivered BOOLEAN DEFAULT FALSE,
                    notify_pickup_reminder BOOLEAN DEFAULT FALSE,
                    
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
                );
            """)
            logger.info("Таблица 'orders' проверена/создана.")

            # (!!!) БЛОК ИСПРАВЛЕНИЯ (ПЕРЕНЕСЕН ВНУТРЬ 'with') (!!!)
            # Этот блок теперь не нужен, т.к. мы удалили orders, но на будущее пусть будет
            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id BIGINT;")
                logger.info("--- FIX --- Колонка 'user_id' в 'orders' проверена.")
            except psycopg2.Error as e:
                conn.rollback() 
                logger.warning(f"--- FIX --- Не удалось добавить user_id: {e}")

            try:
                cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS notify_pickup_reminder BOOLEAN DEFAULT FALSE;")
                logger.info("--- FIX --- Колонка 'notify_pickup_reminder' в 'orders' проверена.")
            except psycopg2.Error as e:
                conn.rollback()
                logger.warning(f"--- FIX --- Не удалось добавить notify_pickup_reminder: {e}")


            try:
                cursor.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint 
                            WHERE conname = 'fk_orders_user'
                        ) THEN
                            ALTER TABLE orders 
                            ADD CONSTRAINT fk_orders_user 
                            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL;
                        END IF;
                    END $$;
                """)
                logger.info("--- FIX --- Внешний ключ 'fk_orders_user' проверен.")
            except psycopg2.Error as e:
                conn.rollback()
                logger.warning(f"--- FIX --- Не удалось добавить внешний ключ: {e}")

            # --- Индексы ---
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status_dushanbe ON orders (status_dushanbe);")
            
            # (!!!) ИСПРАВЛЕНИЕ: Commit теперь выполняется здесь, ВНУТРИ 'with' (!!!)
            conn.commit()
            
        logger.info("Таблицы 'users' и 'orders' проверены/созданы.")
            
    except psycopg2.DatabaseError as e:
        logger.error(f"❌ DB ERROR: Ошибка базы данных. Ошибка: {str(e)}")
        # if conn:
        #     conn.rollback() # <--- ЗАКОММЕНТИРУЙТЕ
        return None
    except Exception as e:
        logger.error(f"❌ UNKNOWN ERROR: Неизвестная ошибка: {e}")
        # if conn:
        #     conn.rollback() # <--- ЗАКОММЕНТИРУЙТЕ
        return None


# === ----------------------------------- ===
# === АСИНХРОННЫЕ ФУНКЦИИ (WRAPPERS)     ===
# === ----------------------------------- ===
#
# Эти функции вызываются из `handlers.py` и `jobs.py`.
# Они используют `asyncio.to_thread`, чтобы безопасно
# вызывать синхронный `execute_query` в асинхронном коде.

# --- Управление Пользователями (Users) ---

async def get_user(user_id):
    """Получает пользователя по ID."""
    query = "SELECT * FROM users WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (user_id,), fetchone=True)

async def create_user(user_id, lang, username=None, full_name=None):
    """
    Создает нового пользователя или обновляет язык/username/имя, 
    если он уже существует (ON CONFLICT).
    """
    query = """
        INSERT INTO users (user_id, language_code, username, full_name, last_activity)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            language_code = EXCLUDED.language_code,
            username = EXCLUDED.username,
            full_name = COALESCE(users.full_name, EXCLUDED.full_name), -- Не перезаписываем ФИО, если оно уже есть
            last_activity = CURRENT_TIMESTAMP
    """
    return await asyncio.to_thread(execute_query, query, (user_id, lang, username, full_name), commit=True)

async def update_user_activity(user_id):
    """Обновляет время последней активности пользователя."""
    query = "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (user_id,), commit=True)


async def update_user_profile(user_id, full_name, phone_number, address):
    """Обновляет ФИО, телефон и адрес при регистрации."""
    query = """
        UPDATE users 
        SET full_name = %s, phone_number = %s, address = %s
        WHERE user_id = %s
    """
    return await asyncio.to_thread(execute_query, query, (full_name, phone_number, address, user_id), commit=True)

async def update_user_phone(user_id, phone_number):
    """Обновляет только телефон (из ЛК)."""
    query = "UPDATE users SET phone_number = %s WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (phone_number, user_id), commit=True)

async def update_user_address(user_id, address):
    """Обновляет только адрес (из ЛК)."""
    query = "UPDATE users SET address = %s WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (address, user_id), commit=True)

async def update_user_lang(user_id, lang):
    """Обновляет язык пользователя."""
    query = "UPDATE users SET language_code = %s WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (lang, user_id), commit=True)

async def get_all_users_count(active_only=False):
    """
    Считает всех пользователей.
    Если active_only=True, считает тех, кто был активен за последние 30 дней.
    """
    if active_only:
        query = "SELECT COUNT(*) as count FROM users WHERE last_activity >= CURRENT_TIMESTAMP - INTERVAL '30 days'"
    else:
        query = "SELECT COUNT(*) as count FROM users"
        
    result = await asyncio.to_thread(execute_query, query, fetchone=True)
    return result['count'] if result else 0

async def get_all_user_ids(active_only=False):
    """
    Получает ID всех пользователей для рассылки.
    """
    if active_only:
        # Убираем проверку на подписку, оставляем только активность
        query = "SELECT user_id FROM users WHERE last_activity >= CURRENT_TIMESTAMP - INTERVAL '30 days'"
    else:
        # ПРОСТО ВЫБИРАЕМ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
        query = "SELECT user_id FROM users"
        
    result = await asyncio.to_thread(execute_query, query, fetchall=True)
    return [row['user_id'] for row in result] if result else []

async def get_user_subscription_status(user_id):
    """Проверяет, подписан ли пользователь (флаг в БД)."""
    query = "SELECT is_subscribed FROM users WHERE user_id = %s"
    result = await asyncio.to_thread(execute_query, query, (user_id,), fetchone=True)
    return result['is_subscribed'] if result else False

async def set_user_subscription_status(user_id, status):
    """Устанавливает флаг подписки (True/False)."""
    query = "UPDATE users SET is_subscribed = %s WHERE user_id = %s"
    return await asyncio.to_thread(execute_query, query, (status, user_id), commit=True)

# --- Управление Заказами (Orders) ---

async def get_order_by_track_code(track_code):
    """Получает ОДИН заказ по трек-коду."""
    query = "SELECT * FROM orders WHERE track_code = %s"
    return await asyncio.to_thread(execute_query, query, (track_code,), fetchone=True)

async def get_orders_by_user_id(user_id):
    """Получает ВСЕ заказы, привязанные к user_id."""
    query = "SELECT * FROM orders WHERE user_id = %s ORDER BY date_yiwu DESC, id DESC"
    return await asyncio.to_thread(execute_query, query, (user_id,), fetchall=True)

# (!!!) ИЗМЕНЕНИЕ 1 из 3 (!!!)
# Добавили 'status_delivered' в SELECT
async def get_user_orders(user_id):
    """
    Получает ВСЕ заказы пользователя (для ЛК).
    (!!!) ИЗМЕНЕНИЕ: Теперь мы также выбираем 'status_delivered' (!!!)
    """
    query = """
        SELECT track_code, status_yiwu, date_yiwu, status_dushanbe, date_dushanbe, status_delivered
        FROM orders 
        WHERE user_id = %s
        ORDER BY date_yiwu DESC, id DESC
    """
    return await asyncio.to_thread(execute_query, query, (user_id,), fetchall=True)


async def link_order_to_user(track_code, user_id):
    """
    Привязывает заказ (найденный в Excel) к пользователю.
    Обновляет только если user_id IS NULL.
    Возвращает rowcount (1 если успешно, 0 если нет).
    """
    query = "UPDATE orders SET user_id = %s WHERE track_code = %s AND user_id IS NULL"
    # commit=True вернет rowcount
    return await asyncio.to_thread(execute_query, query, (user_id, track_code), commit=True)

async def mark_order_as_delivered(track_code):
    """
    Устанавливает статус 'Доставлен' (используется админом /delivered).
    """
    query = """
        UPDATE orders 
        SET status_delivered = 'Доставлен', date_delivered = CURRENT_DATE 
        WHERE track_code = %s
    """
    return await asyncio.to_thread(execute_query, query, (track_code,), commit=True)

# (!!!) ИЗМЕНЕНИЕ 2 из 3 (!!!)
# Добавили эту НОВУЮ функцию
async def request_delivery_for_order(track_code):
    """
    Устанавливает статус 'Запрошена' (используется клиентом).
    Мы обновляем только если он еще не 'Доставлен'.
    """
    query = """
        UPDATE orders 
        SET status_delivered = 'Запрошена'
        WHERE track_code = %s AND (status_delivered IS NULL OR status_delivered = 'В Душанбе')
    """
    # Мы используем commit=True, чтобы изменения сохранились
    return await asyncio.to_thread(execute_query, query, (track_code,), commit=True)


async def get_dushanbe_arrivals_to_notify():
    """
    Получает список заказов, прибывших в Душанбе, по которым нужно отправить уведомление.
    """
    query = """
        SELECT o.track_code, o.user_id, u.language_code
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status_dushanbe IN ('В Душанбе', 'Dushanbe', 'Душанбе') -- Исправлен список
          AND o.notify_dushanbe = FALSE
          AND o.user_id IS NOT NULL
    """
    return await asyncio.to_thread(execute_query, query, fetchall=True)

async def set_dushanbe_notification_sent(track_code):
    """Помечает, что уведомление о прибытии в Душанбе было отправлено."""
    query = "UPDATE orders SET notify_dushanbe = TRUE WHERE track_code = %s"
    return await asyncio.to_thread(execute_query, query, (track_code,), commit=True)

async def get_orders_pending_pickup_reminder():
    """
    Возвращает заказы, которые уже 3+ дней в Душанбе,
    клиент не запросил доставку и напоминание ещё не отправлялось.
    """
    query = """
        SELECT o.track_code, o.user_id, u.language_code
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status_dushanbe IN ('В Душанбе', 'Dushanbe', 'Душанбе')
          AND o.date_dushanbe <= CURRENT_DATE - INTERVAL '3 days'
          AND (o.status_delivered IS NULL OR o.status_delivered NOT IN ('Запрошена', 'Доставлен'))
          AND o.notify_pickup_reminder = FALSE
          AND o.user_id IS NOT NULL
    """
    return await asyncio.to_thread(execute_query, query, fetchall=True)

async def set_pickup_reminder_sent(track_code):
    """Помечает, что напоминание о самовывозе отправлено."""
    query = "UPDATE orders SET notify_pickup_reminder = TRUE WHERE track_code = %s"
    return await asyncio.to_thread(execute_query, query, (track_code,), commit=True)


# (!!!) ИЗМЕНЕНИЕ 3 из 3 (!!!)
# Изменили логику 'status_delivered = ...' в 'ON CONFLICT'
async def upsert_order_from_excel(track_code, status_yiwu, date_yiwu, status_dushanbe, date_dushanbe, status_delivered, date_delivered):
    """
    Обновляет или вставляет заказ из Excel (из jobs.py).
    (!!!) ВАЖНО: Эта функция НЕ ДОЛЖНА перезаписывать статус 'Запрошена' (!!!)
    """
    
    # (!!!) Этот блок очистки был в твоем файле, я его сохраняю (!!!)
    def clean_value(value):
        if isinstance(value, str):
            if value.lower() in ('nan', 'none', '', 'null'):
                return None
        return value

    def clean_date(date_val):
        if str(date_val).lower() in ('nan', 'none', 'nat', '', 'null'):
            return None
        # (!!!) Предполагаем, что pd.to_datetime уже вернул None или объект date
        return date_val

    status_yiwu_clean = clean_value(status_yiwu)
    date_yiwu_clean = clean_date(date_yiwu)
    status_dushanbe_clean = clean_value(status_dushanbe)
    date_dushanbe_clean = clean_date(date_dushanbe)
    status_delivered_clean = clean_value(status_delivered) # Это статус из Excel
    date_delivered_clean = clean_date(date_delivered)

    query = """
        INSERT INTO orders (
            track_code, status_yiwu, date_yiwu, status_dushanbe, date_dushanbe, status_delivered, date_delivered
        ) 
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (track_code) DO UPDATE SET
        status_yiwu = EXCLUDED.status_yiwu,
        date_yiwu = EXCLUDED.date_yiwu,
        status_dushanbe = EXCLUDED.status_dushanbe,
        date_dushanbe = EXCLUDED.date_dushanbe,
    
        -- Защищает СТАТУС
        status_delivered = CASE 
                         WHEN orders.status_delivered = 'Запрошена' THEN 'Запрошена'
                         WHEN orders.status_delivered = 'Доставлен' THEN 'Доставлен'
                         ELSE EXCLUDED.status_delivered 
                       END,
                         
        -- Защищает ДАТУ
        date_delivered = CASE 
                         WHEN orders.status_delivered = 'Запрошена' THEN orders.date_delivered
                         WHEN orders.status_delivered = 'Доставлен' THEN orders.date_delivered
                         ELSE EXCLUDED.date_delivered
                       END
        
RETURNING track_code, (SELECT user_id IS NULL FROM orders WHERE track_code = %s) AS was_unlinked
    """
    
    params = (
        track_code, 
        status_yiwu_clean, date_yiwu_clean, 
        status_dushanbe_clean, date_dushanbe_clean, 
        status_delivered_clean, date_delivered_clean,
        track_code # Для RETURNING
    )
    logger.info(f"DB_CALL: Attempting upsert for code: {track_code}. Status: {status_dushanbe_clean}")

    # execute_query с fetchone=True вернет результат RETURNING
    result = await asyncio.to_thread(execute_query, query, params, fetchone=True, commit=True)
    
    # 🎯 НОВОЕ ЛОГИРОВАНИЕ: ПОСЛЕ ВЫЗОВА
    if result:
        logger.info(f"DB_COMMIT_SUCCESS: Code {result['track_code']} committed.")
    else:
        # Если result == None (произошла ошибка и execute_query вернул None)
        logger.error(f"DB_COMMIT_FAILED: Code {track_code} failed (execute_query returned None).")
        
    return result
    
    # execute_query с fetchone=True вернет результат RETURNING
    #return await asyncio.to_thread(execute_query, query, params, fetchone=True, commit=True)

# 1. Регистрация / обновление пользователя (используется при /start)
async def register_user(user_id: int, full_name: str, username: str | None,
                        phone_number: str, address: str, language_code: str = 'ru') -> bool:
    """
    INSERT нового пользователя или UPDATE существующего (UPSERT).
    Возвращает True, если запись была вставлена/обновлена.
    """
    query = """
        INSERT INTO users (
            user_id, full_name, username, phone_number, address, language_code,
            registration_date, last_activity
        ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            username = EXCLUDED.username,
            phone_number = EXCLUDED.phone_number,
            address = EXCLUDED.address,
            language_code = EXCLUDED.language_code,
            last_activity = CURRENT_TIMESTAMP
        RETURNING user_id;
    """
    result = await asyncio.to_thread(
        execute_query,
        query,
        (user_id, full_name, username, phone_number, address, language_code),
        fetchone=True,
        commit=True
    )
    return bool(result)


# 2. Получение одного заказа по трек-коду (уже есть, но на всякий случай)
async def get_order(track_code: str):
    """Устаревшее имя, оставлено для совместимости. Используйте get_order_by_track_code."""
    return await get_order_by_track_code(track_code)


# 3. Запрос доставки одним заказом (клиент → «Запрошена»)
async def request_delivery(track_code: str, address: str | None = None):
    """Меняет статус на «Запрошена». Адрес сохраняется в отдельной таблице доставок (если нужно)."""
    # Сначала меняем статус
    await request_delivery_for_order(track_code)
    # Если нужна отдельная таблица доставок – добавьте её позже
    return True


# 4. Запрос доставки нескольких заказов сразу
async def request_delivery_multiple(track_codes: list[str], address: str):
    """Массовый запрос доставки."""
    success = 0
    for code in track_codes:
        if await request_delivery_for_order(code):
            success += 1
    return success == len(track_codes)


# 5. Получить все запросы на доставку (для админа)
async def get_delivery_requests():
    query = """
        SELECT o.track_code, u.user_id, u.full_name, u.phone_number, u.address
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status_delivered = 'Запрошена'
        ORDER BY o.date_dushanbe DESC;
    """
    return await asyncio.to_thread(execute_query, query, fetchall=True)


# 6. Подтвердить доставку (админ → «Доставлен»)
async def confirm_delivery(track_codes: list[str]):
    query = """
        UPDATE orders
        SET status_delivered = 'Доставлен',
            date_delivered = CURRENT_DATE,
            notify_delivered = FALSE
        WHERE track_code = ANY(%s)
        RETURNING track_code;
    """
    result = await asyncio.to_thread(
        execute_query,
        query,
        (track_codes,),
        fetchall=True,
        commit=True
    )
    return [row['track_code'] for row in result] if result else []


# 7. Пагинация доставленных заказов (для админа)
async def get_delivered_orders_paginated(page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page
    query = """
        SELECT o.track_code, o.date_delivered,
               u.full_name, u.phone_number
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status_delivered = 'Доставлен'
        ORDER BY o.date_delivered DESC
        LIMIT %s OFFSET %s;
    """
    return await asyncio.to_thread(execute_query, query, (per_page, offset), fetchall=True)


async def get_delivered_orders_count():
    query = "SELECT COUNT(*) as cnt FROM orders WHERE status_delivered = 'Доставлен';"
    res = await asyncio.to_thread(execute_query, query, fetchone=True)
    return res['cnt'] if res else 0


async def get_delivered_orders():
    """Все доставленные (без пагинации, если мало)."""
    query = """
        SELECT o.track_code, o.date_delivered, u.full_name
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status_delivered = 'Доставлен'
        ORDER BY o.date_delivered DESC;
    """
    return await asyncio.to_thread(execute_query, query, fetchall=True)


# 8. Админский upsert (ручное добавление/изменение заказа)
async def admin_upsert_order(track_code: str, status: str,
                             date_yiwu: str | None,
                             date_dushanbe: str | None,
                             owner_id: int | None = None):
    """
    Используется в ConversationHandler админа (addorder).
    """
    # Приводим статусы к нужному виду
    status_yiwu = status if status in ('Yiwu', 'В Иу', 'Иу') else None
    status_dushanbe = status if status in ('Dushanbe', 'В Душанбе', 'Душанбе') else None
    
    # Логика для статуса 'Доставлен'
    status_delivered = None
    date_delivered = None
    
    if status in ('Delivered', 'Доставлен'):
        status_delivered = 'Доставлен'
        # Если ставим статус доставлен, дата доставки = сегодня (или дата Душанбе, если ее передали)
        from datetime import datetime
        date_delivered = datetime.now().date() 

    query = """
        INSERT INTO orders (
            track_code, user_id,
            status_yiwu, date_yiwu,
            status_dushanbe, date_dushanbe,
            status_delivered, date_delivered
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (track_code) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            status_yiwu = EXCLUDED.status_yiwu,
            date_yiwu = EXCLUDED.date_yiwu,
            status_dushanbe = EXCLUDED.status_dushanbe,
            date_dushanbe = EXCLUDED.date_dushanbe,
            status_delivered = EXCLUDED.status_delivered,
            date_delivered = EXCLUDED.date_delivered
        RETURNING track_code;
    """
    params = (
        track_code, owner_id,
        status_yiwu, date_yiwu,
        status_dushanbe, date_dushanbe,
        status_delivered, date_delivered
    )
    result = await asyncio.to_thread(execute_query, query, params, fetchone=True, commit=True)
    return bool(result)


# 9. Маркировка заказа как доставленный по коду (команда /delivered)
async def mark_order_delivered_by_code(track_code: str):
    return await mark_order_as_delivered(track_code)
