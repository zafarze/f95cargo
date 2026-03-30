# -*- coding: utf-8 -*-
# handlers.py
# (!!!) ВЕРСИЯ С ИСПРАВЛЕННЫМ ПАРСЕРОМ EXCEL, ВИДЕО И КНОПКАМИ (!!!)

import os
from datetime import datetime
import asyncio
import pandas as pd
import re   
import uuid
import config

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    InputMediaPhoto,
    InputFile
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode, ChatAction, ChatType
from telegram.error import Forbidden

from config import (
    logger,
    ADMIN_USER_IDS,
    CHANNEL_USERNAME,
    XLSX_FILENAME,
    PHOTO_CONTACT_PATH,
    PHOTO_CONTACT_PATH_RU,
    PHOTO_CONTACT_PATH_EN,
    PHOTO_CONTACT_PATH_TG,
    PHOTO_PRICE_PATH,
    PHOTO_PRICE_PATH_RU,
    PHOTO_PRICE_PATH_EN,
    PHOTO_PRICE_PATH_TG,
    PHOTO_ADDRESS_TAJIK_PATH,
    PHOTO_ADDRESS_CHINA_PATH,
    VIDEO_ADDRESS_TAJIK_PATH,
    START_ROUTES, AWAITING_SUBSCRIPTION, MAIN_MENU, LK_MENU, ADMIN_MENU,
    AWAITING_FULL_NAME, AWAITING_PHONE, AWAITING_ADDRESS, AWAITING_LANG_CHOICE,
    AWAITING_TRACK_CODE,
    LK_AWAIT_DELIVERY_ADDRESS, LK_AWAIT_PROFILE_ADDRESS, LK_AWAIT_PHONE,
    AWAITING_BROADCAST_MESSAGE, CONFIRM_BROADCAST, ADMIN_AWAIT_SEARCH_CODE,
    ADMIN_AWAIT_ORDER_CODE, ADMIN_AWAIT_ORDER_STATUS,
    ADMIN_AWAIT_ORDER_DATE_YIWU, ADMIN_AWAIT_ORDER_DATE_DUSH
)

from db_utils import (
    get_user,
    register_user,
    update_user_lang,
    update_user_address,
    update_user_phone,
    get_all_users_count,
    get_all_user_ids,
    get_order,
    link_order_to_user,
    get_user_orders,
    request_delivery,
    request_delivery_multiple,
    get_delivery_requests,
    confirm_delivery,
    get_delivered_orders_paginated,
    get_delivered_orders_count,
    get_delivered_orders,
    mark_order_delivered_by_code,
    admin_upsert_order,
    get_dushanbe_arrivals_to_notify,
    set_dushanbe_notification_sent,
    upsert_order_from_excel,
    get_order_by_track_code,
    update_user_profile 
)

from texts import TEXTS
from admin_utils import notify_admins

CONTACT_PHONE = "+992909020003"
CONTACT_INSTAGRAM = "F95cargo"
CONTACT_INSTAGRAM_URL = "https://www.instagram.com/F95cargo"

def create_admin_regex(key_index_tuple):
    """
    Создает Regex-строку, которая ловит текст кнопки на 3 языках.
    """
    key, idx1, idx2 = key_index_tuple
    
    # Получаем текст из texts.py
    text_ru = TEXTS.get('ru', {}).get(key, [[""]*5]*5)[idx1][idx2]
    text_tg = TEXTS.get('tg', {}).get(key, [[""]*5]*5)[idx1][idx2]
    text_en = TEXTS.get('en', {}).get(key, [[""]*5]*5)[idx1][idx2]
    
    # Экранируем спецсимволы
    text_ru_safe = re.escape(text_ru)
    text_tg_safe = re.escape(text_tg)
    text_en_safe = re.escape(text_en)
    
    return f"^({text_ru_safe}|{text_tg_safe}|{text_en_safe})$"

# --- Определяем наши Regex ---
REGEX_DELIVERY_REQUESTS = create_admin_regex(('lk_admin_menu_buttons', 0, 0))
REGEX_DELIVERED_LIST = create_admin_regex(('lk_admin_menu_buttons', 0, 1))
REGEX_STATS = create_admin_regex(('lk_admin_menu_buttons', 1, 0))
REGEX_BROADCAST = create_admin_regex(('lk_admin_menu_buttons', 1, 1))
REGEX_DOWNLOAD_EXCEL = create_admin_regex(('lk_admin_menu_buttons', 2, 0))
REGEX_ADMIN_PROFILE = create_admin_regex(('lk_admin_menu_buttons', 2, 1))

# =================================================================
# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
# =================================================================

def get_text(key: str, lang: str = 'ru', default_lang: str = 'ru', fallback: str = None) -> str:
    default_value = fallback if fallback is not None else f"<{key}>"
    return TEXTS.get(lang, {}).get(key) or TEXTS.get(default_lang, {}).get(key, default_value)

def get_main_keyboard(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = get_text('main_buttons', lang)
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_lk_keyboard(lang: str, is_admin: bool) -> ReplyKeyboardMarkup:
    key = 'lk_admin_menu_buttons' if is_admin else 'lk_menu_buttons'
    buttons = get_text(key, lang)
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_cancel_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[get_text('cancel_button', lang)]], 
        resize_keyboard=True
    )

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not CHANNEL_USERNAME:
        logger.warning("CHANNEL_USERNAME не установлен, проверка подписки пропускается.")
        return True
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id} в {CHANNEL_USERNAME}: {e}")
        if "chat not found" in str(e) or "bot is not a member" in str(e):
            logger.warning(f"Проверка подписки не удалась. Разрешаю доступ.")
            return True
        return False

async def send_photo_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, photo_path: str, caption: str = "", reply_markup=None, text_fallback: str = ""):
    try:
        if not os.path.exists(photo_path):
            logger.error(f"Файл фото не найден: {photo_path}")
            await context.bot.send_message(
                chat_id, 
                text_fallback or caption, 
                reply_markup=reply_markup
            )
            return

        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
        with open(photo_path, 'rb') as photo_file:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_file,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Не удалось отправить фото {photo_path} (user {chat_id}): {e}")
        try:
            await context.bot.send_message(
                chat_id, 
                text_fallback or caption, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e2:
            logger.error(f"Не удалось отправить даже резервный текст (user {chat_id}): {e2}")

async def send_document_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, photo_path: str, caption: str = "", reply_markup=None, text_fallback: str = ""):
    """Отправляет изображение как документ — сохраняет оригинальный размер без сжатия и растяжки."""
    try:
        if not os.path.exists(photo_path):
            logger.error(f"Файл не найден: {photo_path}")
            await context.bot.send_message(
                chat_id,
                text_fallback or caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            return

        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        with open(photo_path, 'rb') as doc_file:
            await context.bot.send_document(
                chat_id=chat_id,
                document=doc_file,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Не удалось отправить документ {photo_path} (user {chat_id}): {e}")
        try:
            await context.bot.send_message(
                chat_id,
                text_fallback or caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e2:
            logger.error(f"Не удалось отправить резервный текст (user {chat_id}): {e2}")



async def clear_user_data(context: ContextTypes.DEFAULT_TYPE):
    keys_to_delete = [
        'full_name', 'phone_number', 'address', 
        'broadcast_message',
        'delivery_track_code', 'delivery_track_codes'
    ]
    for key in keys_to_delete:
        if key in context.user_data:
            del context.user_data[key]
            
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

# =================================================================
# --- 1. ОБРАБОТЧИК /START (НАЧАЛО ДИАЛОГА) ---
# =================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id
    name = user.first_name
    
    logger.info(f"User {user_id} ({user.username or 'NoUsername'}) started the bot.")
    
    await clear_user_data(context)
    
    db_user = await get_user(user_id)

    if db_user:
        lang = db_user['language_code'] 
        context.user_data['lang'] = lang
        
        await update.message.reply_text(
            get_text('welcome_back', lang).format(name=name),
            reply_markup=get_main_keyboard(lang, is_admin(user_id))
        )
        return MAIN_MENU
        
    else:
        context.user_data['name_for_welcome'] = name
        
        lang_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"),
            InlineKeyboardButton("Тоҷикӣ 🇹🇯", callback_data="lang_tg"),
            InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")
        ]
    ])
        
        await update.message.reply_text(
            TEXTS['ru']['welcome'].format(name=name),
            reply_markup=lang_keyboard
        )
        return AWAITING_LANG_CHOICE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    lang = query.data.split('_')[1] 
    context.user_data['lang'] = lang
    
    logger.info(f"User {update.effective_user.id} selected initial language: {lang}")

    try:
        await query.edit_message_text(get_text('language_selected', lang))
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение о выборе языка: {e}")

    return await start_subscription_check(update, context)

# =================================================================
# --- 2. ЭТАПЫ РЕГИСТРАЦИИ ---
# =================================================================

async def start_subscription_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    user = update.effective_user
    
    if await check_subscription(user.id, context):
        logger.info(f"User {user.id} already subscribed. Skipping to registration.")
        return await start_registration(update, context)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            get_text('subscribe_button_channel', lang), 
            url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        )],
        [InlineKeyboardButton(
            get_text('subscribe_button_check', lang), 
            callback_data="check_subscription"
        )]
    ])
    
    query = update.callback_query
    if query:
        await query.message.reply_text(
            get_text('subscribe_prompt', lang),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    elif update.message:
        await update.message.reply_text(
            get_text('subscribe_prompt', lang),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    return AWAITING_SUBSCRIPTION

async def process_subscription_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    lang = context.user_data.get('lang', 'ru')
    
    await query.answer(get_text('checking_button', lang), show_alert=False)
    
    if await check_subscription(user.id, context):
        logger.info(f"User {user.id} passed subscription check. Starting registration.")
        await query.edit_message_text(get_text('subscription_success', lang))
        await query.message.reply_text(get_text('registration_start', lang))
        return await start_registration(update, context)
    else:
        await query.answer(get_text('subscribe_fail', lang), show_alert=True)
        return AWAITING_SUBSCRIPTION

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    message_sender = update.message or update.callback_query.message
    
    await message_sender.reply_text(
        get_text('registration_prompt_name', lang),
        reply_markup=ReplyKeyboardRemove()
    )
    return AWAITING_FULL_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    full_name = update.message.text.strip()
    
    if len(full_name.split()) < 2:
        await update.message.reply_text(get_text('registration_invalid_name', lang))
        return AWAITING_FULL_NAME
        
    logger.info(f"User {update.effective_user.id} provided name: {full_name}")
    context.user_data['full_name'] = full_name
    
    phone_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(get_text('send_contact_button', lang), request_contact=True)]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        get_text('registration_prompt_phone', lang).format(full_name=full_name),
        reply_markup=phone_keyboard
    )
    return AWAITING_PHONE

async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    phone = ""
    
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
        
    if not re.match(r'^\+?\d{9,15}$', phone):
        await update.message.reply_text(get_text('registration_invalid_phone', lang))
        return AWAITING_PHONE
        
    if not phone.startswith('+'):
        phone = '+' + phone
        
    logger.info(f"User {update.effective_user.id} provided phone: {phone}")
    context.user_data['phone_number'] = phone
    
    await update.message.reply_text(
        get_text('registration_prompt_address', lang),
        reply_markup=ReplyKeyboardRemove()
    )
    return AWAITING_ADDRESS

async def register_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    address = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    
    full_name = context.user_data.get('full_name')
    phone_number = context.user_data.get('phone_number')
    
    if not all([full_name, phone_number]):
        logger.warning(f"User {user_id} reached end of registration without full_name or phone. Restarting.")
        await update.message.reply_text(get_text('registration_error', lang))
        return await start(update, context)

    logger.info(f"User {user_id} provided address: {address}")
    
    try:
        username = user.username or f"id{user_id}"
        
        success = await register_user(
            user_id=user_id,
            full_name=full_name,
            phone_number=phone_number,
            address=address,
            username=username,
            language_code=lang
        )
        
        if not success:
            raise Exception("register_user returned False")
            
        logger.info(f"User {user_id} successfully registered in DB.")
        
        await update.message.reply_text(
            get_text('registration_complete', lang).format(full_name=full_name),
            reply_markup=get_main_keyboard(lang, is_admin(user_id))
        )
        
        admin_msg = get_text('admin_notify_new_user', 'ru').format(
            full_name=full_name,
            phone=phone_number,
            address=address,
            user_id=user_id,
            username=f"@{username}" if user.username else "N/A"
        )
        await notify_admins(context.bot, admin_msg, parse_mode=ParseMode.HTML)
        
        await clear_user_data(context)
        
        return MAIN_MENU

    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            get_text('registration_error', lang),
            reply_markup=ReplyKeyboardRemove()
        )
        return await start(update, context)
    

# =================================================================
# --- 3. ГЛАВНОЕ МЕНЮ ---
# =================================================================

async def track_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    await update.message.reply_text(
        get_text('track_code_prompt', lang),
        reply_markup=get_cancel_keyboard(lang)
    )
    return AWAITING_TRACK_CODE


async def link_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает callback-кнопку 'link_ТРЕККОД' – привязывает найденный заказ к пользователю.
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    lang = context.user_data.get('lang', 'ru')

    if not query.data.startswith('link_'):
        await query.edit_message_text(get_text('error', lang))
        return MAIN_MENU

    track_code = query.data.split('_', 1)[1].upper()

    linked_rows = await link_order_to_user(track_code, user_id)

    if linked_rows > 0:
        await query.edit_message_text(
            get_text('order_link_success', lang),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Заказ {track_code} успешно привязан к пользователю {user_id}")
        
        order = await get_order_by_track_code(track_code)
        if order:
            status_text = await build_status_text_safe(order, lang)
            await context.bot.send_message(user_id, status_text, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(
            get_text('order_link_fail', lang),
            parse_mode=ParseMode.HTML
        )
        logger.warning(f"Не удалось привязать заказ {track_code} к пользователю {user_id}")

    await context.bot.send_message(
        chat_id=user_id,
        text=get_text('select_action', lang),
        reply_markup=get_main_keyboard(lang, is_admin(user_id))
    )
    return MAIN_MENU

async def build_status_text_safe(order: dict, lang: str) -> str:
    """Строит текстовое описание статуса заказа на основе данных из БД."""
    track_code = order['track_code']
    
    if order.get('status_delivered'):
        date_str = order.get('date_delivered') or "N/A"
        return get_text('track_code_found_other', lang).format(
            code=track_code, 
            status=f"{order['status_delivered']} ({date_str})"
        )
        
    if order.get('status_dushanbe'):
        date_str = order.get('date_dushanbe') or "N/A"
        return get_text('track_code_found_dushanbe', lang).format(
            code=track_code, 
            date=date_str
        )
        
    if order.get('status_yiwu'):
        date_str = order.get('date_yiwu') or "N/A"
        return get_text('track_code_found_yiwu', lang).format(
            code=track_code, 
            date=date_str
        )
        
    return get_text('track_code_found_other', lang).format(
        code=track_code, 
        status="В обработке"
    )

async def process_track_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    user_id = update.effective_user.id
    track_code = update.message.text.strip().upper()
    
    order = await get_order_by_track_code(track_code)
    
    response_text = ""
    keyboard = None
    
    if order:
        response_text = await build_status_text_safe(order, lang)
        
        owner_id = order.get('user_id') 

        if not owner_id:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔗 Привязать этот заказ ко мне",
                    callback_data=f"link_{track_code}"
                )
            ]])
            
            try:
                success = await link_order_to_user(track_code, user_id)
                if success:
                    logger.info(f"Order {track_code} linked to user {user_id}")
                    response_text += f"\n\n{get_text('order_link_success', lang)}"
                    keyboard = None
                else:
                    logger.warning(f"Failed to link order {track_code} to {user_id} (race condition?)")
            except Exception as e:
                logger.error(f"Error linking order {track_code} to {user_id}: {e}")
        
        elif owner_id != user_id:
            logger.warning(f"User {user_id} checked order {track_code} which belongs to {owner_id}")
            
    else:
        response_text = get_text('track_code_not_found', lang)

    await update.message.reply_text(
        response_text, 
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard 
    )
    
    lang = context.user_data['lang']
    user_id = update.effective_user.id
    await update.message.reply_text(
        get_text('select_action', lang),
        reply_markup=get_main_keyboard(lang, is_admin(user_id))
    )
    return MAIN_MENU

async def track_order_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    await update.message.reply_text(get_text('track_code_prompt', lang))
    return AWAITING_TRACK_CODE


async def show_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    base_contacts_text = get_text('contacts', lang)
    phone_text = f"<b>📞 Телефон:</b> <a href='tel:{CONTACT_PHONE}'>{CONTACT_PHONE}</a>"
    contacts_text = f"{base_contacts_text}\n\n{phone_text}"
    
    # Выбираем фото по языку
    lang_photo_map = {
        'ru': PHOTO_CONTACT_PATH_RU,
        'en': PHOTO_CONTACT_PATH_EN,
        'tg': PHOTO_CONTACT_PATH_TG,
    }
    photo_path = lang_photo_map.get(lang, PHOTO_CONTACT_PATH_RU)
    
    # Текст кнопки Instagram по языку
    ig_button_text = {
        'ru': "📸 Наш Instagram",
        'en': "📸 Our Instagram",
        'tg': "📸 Instagram мо",
    }.get(lang, "📸 Instagram")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(ig_button_text, url=CONTACT_INSTAGRAM_URL)]
    ])
    fallback_text = get_text('photo_contact_error', lang).format(contacts=contacts_text)
    
    await send_photo_safe(
        context,
        chat_id=update.effective_chat.id,
        photo_path=photo_path,
        caption=contacts_text,
        reply_markup=keyboard, 
        text_fallback=fallback_text
    )
    return MAIN_MENU

async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    prices_text = get_text('prices_text', lang)

    # Выбираем фото по языку
    lang_price_photo_map = {
        'ru': PHOTO_PRICE_PATH_RU,
        'en': PHOTO_PRICE_PATH_EN,
        'tg': PHOTO_PRICE_PATH_TG,
    }
    photo_path = lang_price_photo_map.get(lang, PHOTO_PRICE_PATH_RU)

    await send_photo_safe(
        context,
        chat_id=update.effective_chat.id,
        photo_path=photo_path,
        caption=prices_text,
        text_fallback=get_text('photo_price_error', lang).format(price_list=prices_text)
    )
    return MAIN_MENU

async def show_forbidden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    await update.message.reply_text(
        get_text('forbidden_text', lang),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )
    return MAIN_MENU

async def show_address_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('button_china', lang), callback_data="address_china")],
        [InlineKeyboardButton(get_text('button_tajikistan', lang), callback_data="address_tajikistan")]
    ])
    await update.message.reply_text(get_text('address_text', lang), reply_markup=keyboard)
    return MAIN_MENU

async def show_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает адрес. Для Таджикистана - мгновенная карта + кнопка видео."""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data['lang']
    address_type = query.data.split('_')[1]
    
    if address_type == "china":
        # Китай
        photo_path = PHOTO_ADDRESS_CHINA_PATH
        caption = get_text('address_caption_china', lang)
        await send_photo_safe(
            context, query.message.chat_id, photo_path, caption,
            text_fallback=get_text('photo_address_error', lang).format(address=caption)
        )
    else:
        # --- ТАДЖИКИСТАН ---
        caption = get_text('address_caption_tajikistan', lang)

        # Текст кнопок на языках
        btn_video = "🎬 Video Guide"
        btn_map = "🗺 Yandex Map"
        if lang == 'ru':
            btn_video = "🎬 Видео проезда (Нажми)"
            btn_map = "🗺 Яндекс Карта"
        elif lang == 'tg':
            btn_video = "🎬 Видео роҳбалад (Зер кунед)"
            btn_map = "🗺 Харитаи Яндекс"

        YANDEX_MAP_URL = "https://yandex.ru/maps?whatshere%5Bpoint%5D=68.80115912695844%2C38.57415557386223&whatshere%5Bzoom%5D=16.0&ll=68.80147703204655%2C38.57502679530826&z=16.0&si=zafarze"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_map, url=YANDEX_MAP_URL)],
            [InlineKeyboardButton(btn_video, callback_data="show_video_tajik")]
        ])

        # Отправляем фото адреса с кнопками
        if os.path.exists(PHOTO_ADDRESS_TAJIK_PATH):
             await send_photo_safe(context, query.message.chat_id, PHOTO_ADDRESS_TAJIK_PATH, caption, reply_markup=keyboard)
        else:
             await query.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    return MAIN_MENU

async def show_video_tajik_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет видео с уведомлением о загрузке."""
    query = update.callback_query
    lang = context.user_data.get('lang', 'ru')
    
    # 1. Уведомление вверху экрана (всплывашка)
    wait_text = "⏳ Загружаю видео..."
    if lang == 'tg': wait_text = "⏳ Видео боргирӣ шуда истодааст..."
    elif lang == 'en': wait_text = "⏳ Uploading video..."
    
    await query.answer(wait_text)
    
    # Проверяем наличие файла (путь берется из config.py)
    if not os.path.exists(VIDEO_ADDRESS_TAJIK_PATH):
        await query.message.reply_text("⚠️ Видео файл не найден (File not found).")
        return MAIN_MENU

    try:
        # 2. Пишем сообщение "Подождите", чтобы клиент не паниковал
        status_msg = await query.message.reply_text(f"{wait_text} 0%")
        
        # 3. Отправляем видео
        with open(VIDEO_ADDRESS_TAJIK_PATH, 'rb') as video_file:
            await query.message.reply_video(
                video=video_file,
                caption=(
                    "📍 Улица Дилкушо, 26/1\n"
                    "Сино район, Душанбе (Ориентир: бозорчаи Ҷал-Ҷам)"
                ),
                supports_streaming=True, # Позволяет смотреть сразу, не скачивая полностью
                read_timeout=60,
                write_timeout=60
            )
        
        # 4. Удаляем сообщение "Загружаю..." после успеха
        try:
            await status_msg.delete()
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка отправки видео: {e}")
        await query.message.reply_text("⚠️ Ошибка при отправке видео. Попробуйте позже.")
        
    return MAIN_MENU

async def change_language_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru"),
                InlineKeyboardButton("Тоҷикӣ 🇹🇯", callback_data="set_lang_tg"),
                InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")
            ]
        ])
    
    await update.message.reply_text(
        "Выберите язык / Забонро интихоб кунед / Select language:", 
        reply_markup=lang_keyboard
    )
    return MAIN_MENU

async def change_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    lang = query.data.split('_')[2]
    user_id = update.effective_user.id
    
    try:
        success = await update_user_lang(user_id, lang) 
        
        if not success:
            raise Exception("update_user_lang returned False")
            
        context.user_data['lang'] = lang
        
        await query.edit_message_text(get_text('language_selected', lang))
        
        await query.message.reply_text(
            get_text('select_action', lang),
            reply_markup=get_main_keyboard(lang, is_admin(user_id))
        )
        
    except Exception as e:
        logger.error(f"Ошибка смены языка для {user_id}: {e}")
        await query.message.reply_text(
            "Произошла ошибка / Хатогӣ рух дод",
            reply_markup=get_main_keyboard(context.user_data.get('lang', 'ru'), is_admin(user_id))
        )
        
    return MAIN_MENU

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    await update.message.reply_text(
        get_text('help_message', lang),
        parse_mode=ParseMode.HTML
    )
    return MAIN_MENU


# =================================================================
# --- 4. ЛИЧНЫЙ КАБИНЕТ (ЛК) - ОБНОВЛЕННАЯ ЛОГИКА ---
# =================================================================

async def lk_menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    lang = context.user_data['lang']
    
    db_user = await get_user(user.id)
    if not db_user:
        await update.message.reply_text(get_text('registration_required', lang))
        return await start(update, context)
    
    await update.message.reply_text(
        get_text('lk_welcome', lang).format(name=user.first_name),
        reply_markup=get_lk_keyboard(lang, is_admin(user.id))
    )
    return LK_MENU

async def lk_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    await update.message.reply_text(
        get_text('select_action', lang),
        reply_markup=get_main_keyboard(lang, is_admin(user_id))
    )
    return MAIN_MENU

async def lk_show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    db_user = await get_user(user_id)
    if not db_user:
        await update.message.reply_text(get_text('registration_required', lang))
        return await start(update, context)
        
    profile_text = get_text('profile_info', lang).format(
        full_name=db_user.get('full_name', 'N/A'),
        phone_number=db_user.get('phone_number', 'N/A'),
        address=db_user.get('address') or get_text('profile_address_not_set', lang)
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('profile_button_edit_phone', lang), callback_data="lk_edit_phone")],
        [InlineKeyboardButton(get_text('profile_button_edit_address', lang), callback_data="lk_edit_address")]
    ])
    
    await update.message.reply_text(profile_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return LK_MENU

async def lk_show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает заказы пользователя с отображением статуса доставки"""
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    orders = await get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text(get_text('lk_no_orders', lang))
        return LK_MENU
        
    response = get_text('lk_orders_title', lang) + "\n\n"
    
    for order in orders:
        status_text = "В обработке"
        date_text = order.get('date_yiwu') or "N/A"
        
        if order.get('status_delivered'):
            status_text = get_text('status_delivered', lang)
            date_text = order.get('date_delivered') or "N/A"
        elif order.get('status_delivered') == 'Запрошена':
             status_text = get_text('status_deliveryrequested', lang)
             date_text = order.get('date_dushanbe') or "N/A"
        elif order.get('status_dushanbe'):
            status_text = get_text('status_dushanbe', lang)
            date_text = order.get('date_dushanbe') or "N/A"
        elif order.get('status_yiwu'):
            status_text = get_text('status_yiwu', lang)
            date_text = order.get('date_yiwu') or "N/A"

        response += get_text('lk_order_item', lang).format(
            code=order['track_code'],
            status=status_text,
            date=date_text
        )
        
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)
    return LK_MENU

async def lk_delivery_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает заказы, готовые к доставке, с проверкой статуса из БД"""
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    all_orders = await get_user_orders(user_id)
    
    # Фильтруем заказы: только те, что в Душанбе и без запроса/доставки
    available_orders = []
    
    # Список статусов, которые считаем "Прибывшими" (в нижнем регистре)
    target_statuses = ['в душанбе', 'душанбе', 'dushanbe'] 

    for order in all_orders:
        status_db = order['status_dushanbe']
        is_in_dushanbe = (status_db and status_db.strip().lower() in target_statuses)
        
        # Проверяем новый 'status_delivered'
        is_requested_or_delivered = order.get('status_delivered') is not None
        
        if is_in_dushanbe and not is_requested_or_delivered:
            available_orders.append(order)
    
    if not available_orders:
        await update.message.reply_text(get_text('lk_delivery_no_orders', lang))
        return LK_MENU
    
    context.user_data['available_delivery_orders'] = available_orders
    
    keyboard = []
    
    if len(available_orders) > 1:
        keyboard.append([
            InlineKeyboardButton(
                get_text('lk_delivery_button_all', lang).format(count=len(available_orders)),
                callback_data="delivery_select_ALL"
            )
        ])
    
    for order in available_orders:
        keyboard.append([
            InlineKeyboardButton(
                f"📦 {order['track_code']}",
                callback_data=f"delivery_select_{order['track_code']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            get_text('cancel_button', lang),
            callback_data="delivery_cancel"
        )
    ])
    
    text_to_send = get_text('lk_delivery_select_order', lang)
    if len(available_orders) > 1:
        codes_str = "\n".join([f"• <code>{o['track_code']}</code>" for o in available_orders])
        text_to_send = get_text('lk_delivery_select_all_orders', lang).format(codes=codes_str)

    await update.message.reply_text(
        text_to_send,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return LK_MENU

async def lk_select_delivery_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор заказа для доставки (один или все)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    track_code_str = query.data.split('_')[2]
    
    prompt_text = ""
    
    if track_code_str == "ALL":
        available_orders = context.user_data.get('available_delivery_orders', [])
        if not available_orders:
            await query.message.edit_text(get_text('lk_delivery_no_orders', lang))
            return LK_MENU
            
        track_codes_list = [o['track_code'] for o in available_orders]
        context.user_data['delivery_track_codes'] = track_codes_list 
        
        prompt_text = get_text('order_delivery_prompt_all', lang)
        
    else:
        track_code = track_code_str
        
        order = await get_order_by_track_code(track_code)
        
        if not order or order.get('status_delivered') is not None:
            await query.message.edit_text(get_text('error', lang))
            return LK_MENU
        
        context.user_data['delivery_track_codes'] = [track_code] 
        
        prompt_text = get_text('order_delivery_prompt', lang).format(track_code=track_code)

    
    db_user = await get_user(user_id)
    saved_address = db_user.get('address') if db_user else None
    
    keyboard = []
    if saved_address:
        keyboard.append([
            InlineKeyboardButton(
                get_text('order_delivery_button_use_saved', lang).format(address=saved_address[:50]),
                callback_data="delivery_use_saved"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            get_text('order_delivery_button_new', lang),
            callback_data="delivery_use_new"
        )
    ])
    
    keyboard.append([
        InlineKeyboardButton(
            get_text('cancel_button', lang),
            callback_data="delivery_cancel"
        )
    ])
    
    await query.message.edit_text(
        prompt_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return LK_MENU

async def lk_delivery_use_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Использует сохраненный адрес для доставки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id  
    lang = context.user_data['lang']
    
    db_user = await get_user(user_id)
    saved_address = db_user.get('address')
    
    if not saved_address:
        await query.message.edit_text(get_text('lk_edit_address_prompt', lang))
        return LK_AWAIT_DELIVERY_ADDRESS
    
    return await lk_save_delivery_request(update, context, saved_address)

async def lk_delivery_use_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает ввод нового адреса"""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data['lang']
    
    await query.message.edit_text(get_text('order_delivery_prompt_new', lang))
    return LK_AWAIT_DELIVERY_ADDRESS

async def lk_delivery_address_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет новый адрес доставки (из ввода)"""
    new_address = update.message.text
    return await lk_save_delivery_request(update, context, new_address)

async def lk_save_delivery_request(update: Update, context: ContextTypes.DEFAULT_TYPE, address: str) -> int:
    """Сохраняет запрос доставки в БД и уведомляет админов"""
    if update.message:
        user_id = update.message.from_user.id
    else:
        user_id = update.callback_query.from_user.id
        
    lang = context.user_data['lang']
    
    track_codes_list = context.user_data.get('delivery_track_codes')
    
    if not track_codes_list:
        if update.message:
            await update.message.reply_text(get_text('error', lang))
        else:
            await update.callback_query.message.reply_text(get_text('error', lang))
        return LK_MENU
    
    success = await request_delivery_multiple(track_codes_list, address)
    
    track_codes_str = ", ".join([f"<code>{c}</code>" for c in track_codes_list])
    
    if success:
        logger.info(f"Delivery request created for {track_codes_str} (user {user_id})")
        
        success_text = get_text('order_delivery_request_sent', lang)
        
        if update.message:
            await update.message.reply_text(
                success_text,
                reply_markup=get_lk_keyboard(lang, is_admin(user_id))
            )
        else:
            await update.callback_query.message.edit_text(success_text)
        
        db_user = await get_user(user_id)
        
        admin_msg = get_text('admin_notify_delivery_request', 'ru').format(
            full_name=db_user.get('full_name', 'N/A'),
            username=f"@{db_user.get('username', '')}" or "N/A",
            phone_number=db_user.get('phone_number', 'N/A'),
            track_codes=track_codes_str,
            address=address
        )
        await notify_admins(context.bot, admin_msg, parse_mode=ParseMode.HTML)
        
    else:
        error_text = get_text('error', lang)
        if update.message:
            await update.message.reply_text(error_text)
        else:
            await update.callback_query.message.edit_text(error_text)
    
    context.user_data.pop('delivery_track_code', None)
    context.user_data.pop('available_delivery_orders', None)
    context.user_data.pop('delivery_track_codes', None)
    
    return LK_MENU


async def lk_delivery_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс запроса доставки"""
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data['lang']
    
    context.user_data.pop('delivery_track_code', None)
    context.user_data.pop('available_delivery_orders', None)
    context.user_data.pop('delivery_track_codes', None)
    
    await query.message.edit_text(get_text('admin_broadcast_cancelled', lang)) 
    
    await query.message.reply_text(
        get_text('lk_welcome_back', lang),
        reply_markup=get_lk_keyboard(lang, is_admin(update.effective_user.id))
    )
    return LK_MENU

async def lk_edit_address_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    db_user = await get_user(user_id)
    current_address = db_user.get('address') or get_text('profile_address_not_set', lang)
    
    await query.message.reply_text(
        get_text('lk_edit_address_prompt', lang).format(address=current_address),
        reply_markup=get_cancel_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return LK_AWAIT_PROFILE_ADDRESS

async def lk_edit_address_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    user_id = update.effective_user.id
    new_address = update.message.text
    
    if new_address == get_text('cancel_button', lang):
        await update.message.reply_text(
            get_text('lk_welcome_back', lang),
            reply_markup=get_lk_keyboard(lang, is_admin(user_id))
        )
        return LK_MENU
        
    try:
        success = await update_user_address(user_id, new_address)
        
        if not success:
            raise Exception("update_user_address returned False")
            
        logger.info(f"User {user_id} updated profile address.")
        
        await update.message.reply_text(
            get_text('lk_edit_address_success', lang),
            reply_markup=get_lk_keyboard(lang, is_admin(user_id))
        )
        return LK_MENU
        
    except Exception as e:
        logger.error(f"Error updating address for {user_id}: {e}")
        await update.message.reply_text(get_text('lk_edit_error', lang))
        return LK_MENU

async def lk_edit_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    db_user = await get_user(user_id)
    current_phone = db_user.get('phone_number', 'N/A')
    
    await query.message.reply_text(
        get_text('lk_edit_phone_prompt', lang).format(phone=current_phone),
        reply_markup=get_cancel_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return LK_AWAIT_PHONE

async def lk_edit_phone_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    user_id = update.effective_user.id
    new_phone = update.message.text
    
    if new_phone == get_text('cancel_button', lang):
        await update.message.reply_text(
            get_text('lk_welcome_back', lang),
            reply_markup=get_lk_keyboard(lang, is_admin(user_id))
        )
        return LK_MENU
        
    if not re.match(r'^\+?\d{9,15}$', new_phone):
        await update.message.reply_text(get_text('registration_invalid_phone', lang))
        return LK_AWAIT_PHONE
        
    if not new_phone.startswith('+'):
        new_phone = '+' + new_phone
        
    try:
        success = await update_user_phone(user_id, new_phone)

        if not success:
            raise Exception("update_user_phone returned False")
            
        logger.info(f"User {user_id} updated profile phone.")
        
        await update.message.reply_text(
            get_text('lk_edit_phone_success', lang),
            reply_markup=get_lk_keyboard(lang, is_admin(user_id))
        )
        return LK_MENU
        
    except Exception as e:
        logger.error(f"Error updating phone for {user_id}: {e}")
        await update.message.reply_text(get_text('lk_edit_error', lang))
        return LK_MENU


# =================================================================
# --- 5. АДМИН-ПАНЕЛЬ (в ЛК) ---
# =================================================================

async def admin_show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    if not is_admin(user_id):
        return await lk_menu_start(update, context)
        
    count = await get_all_users_count()
    await update.message.reply_text(
        get_text('stats_message', lang).format(count=count)
    )
    return LK_MENU

async def admin_download_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await lk_menu_start(update, context)

    await context.bot.send_chat_action(user_id, ChatAction.UPLOAD_DOCUMENT)
    
    try:
        if not os.path.exists(XLSX_FILENAME):
            await update.message.reply_text(f"Файл {XLSX_FILENAME} не найден на сервере.")
            return LK_MENU
            
        with open(XLSX_FILENAME, 'rb') as doc:
            await context.bot.send_document(
                chat_id=user_id,
                document=doc,
                filename=XLSX_FILENAME
            )
    except Exception as e:
        logger.error(f"Admin {user_id} failed to download Excel: {e}")
        await update.message.reply_text(f"Не удалось отправить файл: {e}")
        
    return LK_MENU

async def admin_show_delivery_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    if not is_admin(user_id):
        return await lk_menu_start(update, context)
        
    requests = await get_delivery_requests()
    
    if not requests:
        await update.message.reply_text(get_text('admin_delivery_requests_empty', lang))
        return LK_MENU
        
    await update.message.reply_text(
        get_text('admin_delivery_requests_title', lang),
        parse_mode=ParseMode.HTML
    )
    
    user_requests = {} 
    
    for req in requests:
        uid = req['user_id']
        if uid not in user_requests:
            user_requests[uid] = {
                'full_name': req['full_name'],
                'phone_number': req['phone_number'],
                'address': req['address'],
                'track_codes': []
            }
        user_requests[uid]['track_codes'].append(req['track_code'])
        
    
    for user_id, data in user_requests.items():
        
        codes_str = ", ".join([f"<code>{c}</code>" for c in data['track_codes']])
        
        msg = get_text('admin_delivery_requests_item', 'ru').format(
            full_name=data['full_name'],
            user_id=user_id,
            phone_number=data['phone_number'],
            address=data['address'], 
            track_codes=codes_str
        )
        
        callback_data = f"admin_confirm_{user_id}"
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                get_text('admin_delivery_button_confirm', 'ru').format(user_id=user_id),
                callback_data=callback_data
            )
        ]])
        
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        
    return LK_MENU

async def admin_confirm_delivery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    admin_id = update.effective_user.id
    lang = context.user_data['lang']
    
    try:
        client_user_id = int(query.data.split('_')[2])
        
        requests = await get_delivery_requests()
        codes_to_confirm = [
            req['track_code'] for req in requests if req['user_id'] == client_user_id
        ]
        
        if not codes_to_confirm:
             await query.message.reply_text(
                f"Не найдено заказов для подтверждения (ID: {client_user_id}). Возможно, уже подтверждено?"
            )
             return LK_MENU

        confirmed_codes = await confirm_delivery(codes_to_confirm)
        
        if not confirmed_codes:
            logger.warning(f"Admin {admin_id} нажал 'confirm' для {client_user_id}, но 0 заказов было обновлено.")
            await query.message.reply_text(
                f"Не найдено заказов для подтверждения (ID: {client_user_id}). Возможно, уже подтверждено?"
            )
            return LK_MENU

        track_codes_str = ", ".join(confirmed_codes)

        logger.info(f"Admin {admin_id} confirmed delivery for user {client_user_id}, codes: {track_codes_str}")
        
        client_user = await get_user(client_user_id)
        client_name = client_user['full_name'] if client_user else f"ID {client_user_id}"
        client_lang = client_user['language_code'] if client_user else 'ru'

        await query.message.reply_text(
            get_text('admin_delivery_confirm_success', lang).format(
                full_name=client_name,
                track_codes=track_codes_str
            )
        )
        
        await query.edit_message_reply_markup(reply_markup=None)
        
        try:
            client_msg_title = get_text('user_notify_delivered_title', client_lang)
            client_msg_body = get_text('user_notify_delivered_body', client_lang).format(
                track_codes="\n".join([f"• <code>{code}</code>" for code in confirmed_codes])
            )
            await context.bot.send_message(
                client_user_id,
                f"<b>{client_msg_title}</b>\n\n{client_msg_body}",
                parse_mode=ParseMode.HTML 
            )
        except Forbidden:
            logger.warning(f"Admin confirm: Cannot notify client {client_user_id} (bot blocked).")
        except Exception as e:
            logger.error(f"Admin confirm: Failed to notify client {client_user_id}: {e}")

    except Exception as e:
        logger.error(f"Admin {admin_id} failed to confirm delivery (callback): {e}", exc_info=True)
        await query.message.reply_text(get_text('admin_delivery_confirm_fail', lang))

    return LK_MENU

async def admin_show_delivered_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    if not is_admin(user_id):
        return await lk_menu_start(update, context)
    
    page = context.user_data.get('delivered_page', 1)
    limit = 50
    offset = (page - 1) * limit
    
    orders = await get_delivered_orders_paginated(page, limit)
    total_count = await get_delivered_orders_count()
    
    if not orders:
        await update.message.reply_text(get_text('admin_delivered_list_empty', lang))
        return LK_MENU
        
    response = f"{get_text('admin_delivered_list_title', lang)}\n"
    response += f"Страница {page} (всего: {total_count})\n\n"
    
    for order in orders:
        try:
            if isinstance(order['date_delivered'], datetime):
                 date_str = order['date_delivered'].strftime('%Y-%m-%d %H:%M')
            else:
                 date_str = str(order['date_delivered'] or "N/A")
        except:
            date_str = str(order['date_delivered'] or "N/A")
            
        response += get_text('admin_delivered_item', 'ru').format(
            code=order['track_code'],
            full_name=order['full_name'] or "N/A",
            date=date_str
        )
    
    keyboard = []
    if page > 1:
        keyboard.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"delivered_page_{page-1}"))
    if offset + limit < total_count:
        keyboard.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"delivered_page_{page+1}"))
    
    reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None
    
    await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return LK_MENU

async def delivered_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.split('_')[2])
    context.user_data['delivered_page'] = page
    
    return await admin_show_delivered_list(query.message, context)
    
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data['lang']
    
    if not is_admin(user_id):
        return await lk_menu_start(update, context)
        
    await update.message.reply_text(
        get_text('admin_broadcast_prompt', lang),
        reply_markup=get_cancel_keyboard(lang)
    )
    return AWAITING_BROADCAST_MESSAGE

async def admin_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    context.user_data['broadcast_message'] = update.message
    
    await update.message.reply_text(get_text('admin_broadcast_confirm_prompt', lang).format(message=""))
    await context.bot.copy_message(
        chat_id=update.effective_chat.id,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
    
    keyboard = ReplyKeyboardMarkup(
        [["Да, отправить"], ["Нет, отменить"]],
        resize_keyboard=True
    )
    await update.message.reply_text("Отправляем?", reply_markup=keyboard)
    
    return CONFIRM_BROADCAST

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    admin_id = update.effective_user.id
    
    message_to_send = context.user_data.get('broadcast_message')
    if not message_to_send:
        await update.message.reply_text("Ошибка: сообщение не найдено.")
        return await lk_menu_start(update, context)
        
    await update.message.reply_text("Начинаю рассылку...", reply_markup=get_lk_keyboard(lang, is_admin(admin_id)))
    
    user_ids = await get_all_user_ids()
    
    success_count = 0
    failed_count = 0
    
    for user_id in user_ids:
        if user_id == admin_id:
            continue
            
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message_to_send.chat_id,
                message_id=message_to_send.message_id
            )
            success_count += 1
        except Forbidden:
            failed_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Broadcast error to {user_id}: {e}")
        await asyncio.sleep(0.1)
        
    await update.message.reply_text(
        get_text('admin_broadcast_report', lang).format(
            success=success_count,
            failed=failed_count
        )
    )
    
    del context.user_data['broadcast_message']
    return LK_MENU

async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data['lang']
    if 'broadcast_message' in context.user_data:
        del context.user_data['broadcast_message']
        
    await update.message.reply_text(
        get_text('admin_broadcast_cancelled', lang),
        reply_markup=get_lk_keyboard(lang, is_admin(update.effective_user.id))
    )
    return LK_MENU

async def admin_mark_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    try:
        track_code = context.args[0].upper()
    except IndexError:
        await update.message.reply_text("Использование: /delivered <code>")
        return

    order = await get_order_by_track_code(track_code)
    if not order:
        await update.message.reply_text(f"❌ Заказ {track_code} не найден в БД.")
        return
    
    success = await mark_order_delivered_by_code(track_code)
    
    if success:
        logger.info(f"Admin {user_id} marked {track_code} as Delivered via command.")
        await update.message.reply_text(f"✅ Заказ {track_code} отмечен как 'Delivered'.")
        
        client_user_id = order.get('user_id')
        if client_user_id:
            try:
                client_user = await get_user(client_user_id)
                client_lang = client_user['language_code'] if client_user else 'ru'
                
                client_msg_title = get_text('user_notify_delivered_title', client_lang)
                client_msg_body = get_text('user_notify_delivered_body', client_lang).format(
                    track_codes=f"• <code>{track_code}</code>"
                )
                await context.bot.send_message(
                    client_user_id,
                    f"<b>{client_msg_title}</b>\n\n{client_msg_body}",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.warning(f"Admin /delivered: Failed to notify client {client_user_id}: {e}")
                
    else:
        await update.message.reply_text(f"❌ Не удалось обновить статус для {track_code}.")
        
    return

# =================================================================
# --- 6. ОБРАБОТЧИКИ ФАЙЛОВ И ОШИБОК ---
# =================================================================

async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'ru')
    await update.message.reply_text(get_text('image_received', lang))

async def invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'ru')
    user_id = update.effective_user.id
    
    await update.message.reply_text(
        get_text('invalid_input', lang),
        reply_markup=get_main_keyboard(lang, is_admin(user_id))
    )
    return MAIN_MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update: {update} caused error: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            lang = context.user_data.get('lang', 'ru')
            await update.effective_message.reply_text(get_text('error', lang))
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

# =================================================================
# --- 7. СБОРКА CONVERSATION HANDLERS ---
# =================================================================

def get_main_conv_handler() -> ConversationHandler:
    
    lang_filter = filters.TEXT & (~filters.COMMAND)

    entry_points = [
        CommandHandler("start", start),
        CommandHandler("help", show_help),

        CallbackQueryHandler(select_language, pattern='^lang_'),
        CallbackQueryHandler(process_subscription_check, pattern='^check_subscription$'),
        CallbackQueryHandler(show_address_callback, pattern='^address_'),
        CallbackQueryHandler(show_video_tajik_callback, pattern='^show_video_tajik$'),
        CallbackQueryHandler(change_language_callback, pattern='^set_lang_'),
        CallbackQueryHandler(lk_edit_address_start, pattern='^lk_edit_address$'),
        CallbackQueryHandler(lk_edit_phone_start, pattern='^lk_edit_phone$'),
        CallbackQueryHandler(lk_select_delivery_order, pattern='^delivery_select_'),
        CallbackQueryHandler(lk_delivery_use_saved, pattern='^delivery_use_saved$'),
        CallbackQueryHandler(lk_delivery_use_new, pattern='^delivery_use_new$'),
        CallbackQueryHandler(lk_delivery_cancel, pattern='^delivery_cancel$'),
        CallbackQueryHandler(admin_confirm_delivery_callback, pattern='^admin_confirm_'),
        CallbackQueryHandler(delivered_page_callback, pattern='^delivered_page_'),
        CallbackQueryHandler(link_order_callback, pattern='^link_'),
    ]
    
    states = {
        AWAITING_LANG_CHOICE: [
            CallbackQueryHandler(select_language, pattern='^lang_')
        ],
        
        AWAITING_SUBSCRIPTION: [
            CallbackQueryHandler(process_subscription_check, pattern='^check_subscription$')
        ],

        AWAITING_FULL_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)
        ],
        AWAITING_PHONE: [
            MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), register_phone)
        ],
        AWAITING_ADDRESS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, register_address)
        ],

        MAIN_MENU: [
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[0][0]}|{get_text('main_buttons', 'tg')[0][0]}|{get_text('main_buttons', 'en')[0][0]})$"), track_order_start),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[0][1]}|{get_text('main_buttons', 'tg')[0][1]}|{get_text('main_buttons', 'en')[0][1]})$"), lk_menu_start),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[1][0]}|{get_text('main_buttons', 'tg')[1][0]}|{get_text('main_buttons', 'en')[1][0]})$"), show_contacts),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[1][1]}|{get_text('main_buttons', 'tg')[1][1]}|{get_text('main_buttons', 'en')[1][1]})$"), show_prices),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[2][0]}|{get_text('main_buttons', 'tg')[2][0]}|{get_text('main_buttons', 'en')[2][0]})$"), show_forbidden),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[2][1]}|{get_text('main_buttons', 'tg')[2][1]}|{get_text('main_buttons', 'en')[2][1]})$"), show_address_menu),
            MessageHandler(lang_filter & filters.Regex(f"^({get_text('main_buttons', 'ru')[3][0]}|{get_text('main_buttons', 'tg')[3][0]}|{get_text('main_buttons', 'en')[3][0]})$"), change_language_start),
            
            CallbackQueryHandler(show_address_callback, pattern='^address_'),
            CallbackQueryHandler(change_language_callback, pattern='^set_lang_'),
            CallbackQueryHandler(link_order_callback, pattern='^link_'),
            
            # (!!!) ДОБАВЛЕН ОБРАБОТЧИК КНОПКИ ВИДЕО В MAIN_MENU (!!!)
            CallbackQueryHandler(show_video_tajik_callback, pattern='^show_video_tajik$'),
            
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_track_code)
        ],
        
        AWAITING_TRACK_CODE: [
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'ru')}$"), lk_back_to_main),
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'tg')}$"), lk_back_to_main),
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'en')}$"), lk_back_to_main),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_track_code)
        ],

        LK_MENU: [
            MessageHandler(lang_filter & filters.Regex(
                f"^({re.escape(get_text('lk_menu_buttons', 'ru')[2][0])}|{re.escape(get_text('lk_menu_buttons', 'tg')[2][0])}|{re.escape(get_text('lk_menu_buttons', 'en')[2][0])})$"
            ), lk_back_to_main),
            
            MessageHandler(lang_filter & filters.Regex(
                f"^({re.escape(get_text('lk_menu_buttons', 'ru')[0][0])}|{re.escape(get_text('lk_menu_buttons', 'tg')[0][0])}|{re.escape(get_text('lk_menu_buttons', 'en')[0][0])})$"
            ), lk_show_orders),
            MessageHandler(lang_filter & filters.Regex(
                f"^({re.escape(get_text('lk_menu_buttons', 'ru')[0][1])}|{re.escape(get_text('lk_menu_buttons', 'tg')[0][1])}|{re.escape(get_text('lk_menu_buttons', 'en')[0][1])})$"
            ), lk_show_profile),
            MessageHandler(lang_filter & filters.Regex(
                f"^({re.escape(get_text('lk_menu_buttons', 'ru')[1][0])}|{re.escape(get_text('lk_menu_buttons', 'tg')[1][0])}|{re.escape(get_text('lk_menu_buttons', 'en')[1][0])})$"
            ), lk_delivery_start),
            
            MessageHandler(lang_filter & filters.Regex(REGEX_DELIVERY_REQUESTS), admin_show_delivery_requests),
            MessageHandler(lang_filter & filters.Regex(REGEX_DELIVERED_LIST), admin_show_delivered_list),
            MessageHandler(lang_filter & filters.Regex(REGEX_STATS), admin_show_stats),
            MessageHandler(lang_filter & filters.Regex(REGEX_BROADCAST), admin_broadcast_start),
            MessageHandler(lang_filter & filters.Regex(REGEX_DOWNLOAD_EXCEL), admin_download_excel),
            
            MessageHandler(lang_filter & filters.Regex(REGEX_ADMIN_PROFILE), lk_show_profile),
            
            CallbackQueryHandler(lk_edit_address_start, pattern='^lk_edit_address$'),
            CallbackQueryHandler(lk_edit_phone_start, pattern='^lk_edit_phone$'),
            CallbackQueryHandler(lk_select_delivery_order, pattern='^delivery_select_'),
            CallbackQueryHandler(lk_delivery_use_saved, pattern='^delivery_use_saved$'),
            CallbackQueryHandler(lk_delivery_use_new, pattern='^delivery_use_new$'),
            CallbackQueryHandler(lk_delivery_cancel, pattern='^delivery_cancel$'),
            CallbackQueryHandler(admin_confirm_delivery_callback, pattern='^admin_confirm_'),
            CallbackQueryHandler(delivered_page_callback, pattern='^delivered_page_'),
            
            MessageHandler(filters.TEXT & ~filters.COMMAND, invalid_input)
        ],
        
        LK_AWAIT_DELIVERY_ADDRESS: [
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'ru')}$"), lk_menu_start),
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'tg')}$"), lk_menu_start),
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('cancel_button', 'en')}$"), lk_menu_start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, lk_delivery_address_save),
        ],
        
        LK_AWAIT_PROFILE_ADDRESS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lk_edit_address_save),
        ],

        LK_AWAIT_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lk_edit_phone_save),
        ],
    }

    return ConversationHandler(
        entry_points=entry_points,
        states=states,
        fallbacks=[
        CommandHandler("start", start),
        CommandHandler("help", show_help)
    ],
        persistent=True,
        name="main_conversation",
        per_message=False
    )

def get_broadcast_conv_handler() -> ConversationHandler:
    
    YES_BROADCAST = "Да, отправить"
    NO_BROADCAST = "Нет, отменить"
    confirm_filter = filters.Regex(f"^({YES_BROADCAST})$")
    cancel_filter = filters.Regex(
        f"^({NO_BROADCAST}|"
        f"{get_text('cancel_button', 'ru')}|"
        f"{get_text('cancel_button', 'tg')}|"
        f"{get_text('cancel_button', 'en')})$"
    )

    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & filters.Regex(f"^{get_text('lk_admin_menu_buttons', 'ru')[1][1]}$"), admin_broadcast_start),
        ],
        states={
            AWAITING_BROADCAST_MESSAGE: [
                MessageHandler(cancel_filter, admin_broadcast_cancel),
                CommandHandler("cancel", admin_broadcast_cancel),
                MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_confirm)
            ],
            CONFIRM_BROADCAST: [
                MessageHandler(confirm_filter, admin_broadcast_send),
                MessageHandler(cancel_filter, admin_broadcast_cancel),
                CommandHandler("cancel", admin_broadcast_cancel)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", admin_broadcast_cancel),
            CommandHandler("start", start)
        ],
        map_to_parent={
            LK_MENU: LK_MENU,
            MAIN_MENU: MAIN_MENU
        }
    )

# =================================================================
# --- 8. ДИАЛОГ АДМИНА: ДОБАВЛЕНИЕ/РЕДАКТИРОВАНИЕ ЗАКАЗА ---
# =================================================================

async def admin_add_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END

    context.user_data.pop('admin_order_data', None)
    
    await update.message.reply_text(
        "Вы вошли в режим <b>Добавить/Обновить Заказ</b>.\n\n"
        "<b>Шаг 1/4:</b> Введите <b>Трек-код</b> заказа\n"
        "(или /cancel для отмены):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_AWAIT_ORDER_CODE

async def admin_add_order_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    track_code = update.message.text.strip().upper()
    if not track_code:
        await update.message.reply_text("Трек-код не может быть пустым. Попробуйте снова:")
        return ADMIN_AWAIT_ORDER_CODE

    context.user_data['admin_order_data'] = {'track_code': track_code}
    
    existing_order = await get_order_by_track_code(track_code)
    
    if existing_order:
        await update.message.reply_text(
            f"Заказ <code>{track_code}</code> <b>НАЙДЕН</b> (режим обновления).\n"
            f"Текущий статус: {existing_order.get('status_yiwu') or existing_order.get('status_dushanbe') or existing_order.get('status_delivered')}\n"
            f"Владелец: {existing_order.get('user_id') or 'N/A'}\n\n"
            f"<b>Шаг 2/4:</b> Введите <b>НОВЫЙ статус</b>\n"
            "(Yiwu, Dushanbe, Delivered):",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"Заказ <code>{track_code}</code> <b>НЕ НАЙДЕН</b> (режим создания).\n\n"
            f"<b>Шаг 2/4:</b> Введите <b>статус</b>\n"
            "(Yiwu, Dushanbe):",
            parse_mode=ParseMode.HTML
        )
        
    return ADMIN_AWAIT_ORDER_STATUS

async def admin_add_order_get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    status = update.message.text.strip().capitalize()
    context.user_data['admin_order_data']['status'] = status
    
    await update.message.reply_text(
        "<b>Шаг 3/4:</b> Введите <b>дату Yiwu/Иу</b>\n"
        "(в формате ГГГГ-ММ-ДД, или <code>0</code>, или /skip, чтобы очистить):",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_AWAIT_ORDER_DATE_YIWU

async def admin_add_order_get_date_yiwu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_yiwu = update.message.text.strip()
    if date_yiwu == '0' or date_yiwu == '/skip':
        date_yiwu = None
        
    context.user_data['admin_order_data']['date_yiwu'] = date_yiwu
    
    await update.message.reply_text(
        "<b>Шаг 4/4:</b> Введите <b>дату Dushanbe/Душанбе</b>\n"
        "(в формате ГГГГ-ММ-ДД, или <code>0</code>, или /skip, чтобы очистить):",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_AWAIT_ORDER_DATE_DUSH

async def admin_add_order_get_date_dush_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'ru')
    date_dush = update.message.text.strip()
    if date_dush == '0' or date_dush == '/skip':
        date_dush = None
        
    data = context.user_data.pop('admin_order_data')
    data['date_dushanbe'] = date_dush
    
    existing_order = await get_order_by_track_code(data['track_code'])
    data['owner_id'] = existing_order.get('user_id') if existing_order else None
    
    try:
        success = await admin_upsert_order(**data)
        
        if success:
            await update.message.reply_text(
                f"✅ <b>Успешно!</b> Заказ <code>{data['track_code']}</code> сохранен в БД.\n"
                f"Статус: {data['status']}\n"
                f"Владелец: {data['owner_id'] or 'Будет привязан при первом поиске'}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_lk_keyboard(lang, is_admin=True)
            )
            logger.info(f"Admin {update.effective_user.id} updated/inserted order {data['track_code']}")
        else:
            raise Exception("admin_upsert_order вернула False")
            
    except Exception as e:
        logger.error(f"Не удалось сохранить админский заказ: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ <b>Ошибка!</b> Не удалось сохранить заказ <code>{data['track_code']}</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_lk_keyboard(lang, is_admin=True)
        )
        
    return LK_MENU

async def admin_add_order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('admin_order_data', None)
    lang = context.user_data.get('lang', 'ru')
    
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=get_lk_keyboard(lang, is_admin=True)
    )
    return LK_MENU

def get_admin_conv_handler() -> ConversationHandler:
    
    cancel_filter = filters.Regex(f"^(/cancel)$")
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("addorder", admin_add_order_start)
        ],
        states={
            ADMIN_AWAIT_ORDER_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_order_get_code)
            ],
            ADMIN_AWAIT_ORDER_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_order_get_status)
            ],
            ADMIN_AWAIT_ORDER_DATE_YIWU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_order_get_date_yiwu)
            ],
            ADMIN_AWAIT_ORDER_DATE_DUSH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_order_get_date_dush_and_save)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", admin_add_order_cancel),
            MessageHandler(cancel_filter, admin_add_order_cancel)
        ],
        map_to_parent={
            LK_MENU: LK_MENU
        }
    )

# =================================================================
# --- 9. ОБРАБОТЧИК ЗАГРУЗКИ EXCEL-ФАЙЛА ---
# =================================================================

def parse_date_safe(date_str):
    """
    Вспомогательная функция: превращает строку в дату.
    Понимает: 01.01.2026, 2026-01-01, 01/01/2026.
    """
    if not date_str or str(date_str).lower() in ['nan', 'nat', 'none', '', '0', 'null']:
        return None
    try:
        # Убираем время, если оно есть (2026-01-01 12:00:00)
        clean_str = str(date_str).strip().split(" ")[0]
        # dayfirst=True важен для формата 01.02.2026 (1 февраля, а не 2 января)
        dt = pd.to_datetime(clean_str, dayfirst=True, errors='coerce')
        return dt.date() if pd.notna(dt) else None
    except:
        return None

async def process_excel_to_db(file_path: str) -> dict:
    """
    ВЕРСИЯ: СТРОГАЯ ЛОГИКА (5 КОЛОНОК)
    Формат: [Трек] [Дата Иу] [Статус Иу] [Дата Душанбе] [Статус Душанбе]
    """
    stats = {'total': 0, 'updated': 0, 'failed': 0, 'linked': 0}
    
    try:
        logger.info(f"--- НАЧАЛО ЗАГРУЗКИ (СТРОГИЙ РЕЖИМ): {file_path} ---")
        
        try:
            # Читаем файл. header=0 означает, что первая строка - это заголовки (мы их пропустим)
            df = pd.read_excel(file_path, header=0, dtype=str)
        except:
            df = pd.read_csv(file_path, header=0, dtype=str, sep=None, engine='python')

        df = df.dropna(how='all')
        
        # Проверяем, что в файле достаточно колонок
        if len(df.columns) < 2:
            return {'error': 'В файле слишком мало колонок! Нужно минимум 3: Трек, Дата Иу, Статус.'}

        logger.info(f"Колонки (по порядку): {list(df.columns)}")

        excel_data = []
        
        for idx, row in df.iterrows():
            # ==========================================
            # 1. ТРЕК-КОД (Колонка №1 / индекс 0)
            # ==========================================
            raw_track = row.iloc[0] 
            if pd.isna(raw_track) or str(raw_track).strip() == '': continue
            
            track_code = str(raw_track).strip().upper()
            if len(track_code) < 3: continue # Пропускаем мусор

            # ==========================================
            # 2. ИУ (Колонка №2 - Дата, №3 - Статус)
            # ==========================================
            date_yiwu = None
            status_yiwu = "Иу" # По умолчанию (если ячейка пустая)

            # Дата Иу (индекс 1)
            if len(df.columns) > 1:
                date_yiwu = parse_date_safe(row.iloc[1])

            # Статус Иу (индекс 2)
            if len(df.columns) > 2 and pd.notna(row.iloc[2]):
                val = str(row.iloc[2]).strip()
                if val: status_yiwu = val

            # ==========================================
            # 3. ДУШАНБЕ (Колонка №4 - Дата, №5 - Статус)
            # ==========================================
            date_dushanbe = None
            status_dushanbe = None
            status_delivered = None
            date_delivered = None

            # Дата Душанбе (индекс 3)
            if len(df.columns) > 3:
                date_dushanbe = parse_date_safe(row.iloc[3])
            
            # Статус Душанбе (индекс 4)
            if len(df.columns) > 4 and pd.notna(row.iloc[4]):
                val_status = str(row.iloc[4]).strip()
                val_lower = val_status.lower()
                
                if val_status:
                    if any(x in val_lower for x in ['доставлен', 'выдан', 'delivered']):
                        # Если написано "Доставлен"
                        status_delivered = "Доставлен"
                        date_delivered = date_dushanbe # Дата выдачи = Дата Душанбе
                        status_dushanbe = "Душанбе" # Оставляем историю
                    elif any(x in val_lower for x in ['душанбе', 'прибыл', 'dushanbe']):
                        # Если написано "Душанбе"
                        status_dushanbe = "Душанбе"
                    else:
                        # Любой другой текст
                        status_dushanbe = val_status
            
            # АВТО-СТАТУС: Если даты Душанбе нет, но дата Иу есть -> Статус Иу
            # Если дата Душанбе есть, а статус пустой -> Ставим "Душанбе"
            if date_dushanbe and not status_dushanbe:
                status_dushanbe = "Душанбе"

            # Собираем данные
            excel_data.append({
                'track_code': track_code, 
                'status_yiwu': status_yiwu, 
                'date_yiwu': date_yiwu,
                'status_dushanbe': status_dushanbe, 
                'date_dushanbe': date_dushanbe,
                'status_delivered': status_delivered, 
                'date_delivered': date_delivered,
            })

    except Exception as e:
        logger.error(f"❌ ОШИБКА EXCEL: {e}", exc_info=True)
        return {'error': str(e)}

    # Запись в БД
    stats['total'] = len(excel_data)
    for row in excel_data:
        try:
            res = await upsert_order_from_excel(**row)
            if res:
                stats['updated'] += 1
                if res.get('was_unlinked'): stats['linked'] += 1
            else:
                stats['failed'] += 1
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"Ошибка БД для {row.get('track_code')}: {e}")
            
    logger.info(f"--- ИТОГ: {stats} ---")
    return stats

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        logger.warning(f"Не-админ (ID: {user_id}) попытался загрузить файл.")
        return

    doc = update.message.document
    
    # Проверка расширения
    if not doc.file_name or not doc.file_name.lower().endswith(('.xlsx', '.xls', '.csv')):
        logger.info(f"Админ {user_id} загрузил неподдерживаемый файл: {doc.file_name}")
        await update.message.reply_text(
            f"Это не похоже на Excel/CSV-файл. Пожалуйста, отправьте файл с расширением .xlsx, .xls или .csv"
        )
        return

    temp_filename = f"temp_upload_{uuid.uuid4()}{os.path.splitext(doc.file_name)[1]}"
    
    await update.message.reply_text(
        "Файл получен. Обрабатываю..."
    )
    
    try:
        file = await doc.get_file()
        await file.download_to_drive(temp_filename)
        
        await update.message.reply_text(
            f"✅ Файл сохранен. Начинаю импорт (структура: Трек | Дата Иу | Статус Иу | Дата Душ | Статус Душ)..."
        )
        
        stats = await process_excel_to_db(temp_filename)
        
        if 'error' in stats:
            await update.message.reply_text(
                f"❌ <b>Ошибка импорта:</b>\n<code>{stats['error']}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            report = (
                f"<b>✅ Импорт из {doc.file_name} завершен:</b>\n\n"
                f"<b>Всего строк:</b> {stats.get('total', 0)}\n"
                f"<b>Обновлено:</b> {stats.get('updated', 0)}\n"
                f"<b>Привязано к клиентам:</b> {stats.get('linked', 0)}\n"
                f"<b>Ошибок:</b> {stats.get('failed', 0)}"
            )
            await update.message.reply_text(report, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Admin {user_id} failed to process uploaded Excel: {e}", exc_info=True)
        await update.message.reply_text(f"❌ <b>Критическая ошибка:</b> {e}")
        
    finally:
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                logger.info(f"Удален временный файл: {temp_filename}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временный файл: {e}")
