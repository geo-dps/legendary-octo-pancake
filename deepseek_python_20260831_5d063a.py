#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Пользователь вводит @ИмяБота @username текст → появляется кнопка.
При нажатии → эфемерное сообщение в группе видит только @username.
"""

import logging
import os
import re
import uuid
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
    filters,
)

# ─── Конфиг ─────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан")

# ─── Логирование ────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("ephemeral_bot")

# Хранилище данных для Inline-запросов
_ephemeral_data: dict = {}

# ─── Эфемерные сообщения ──────────────────────────────────────────

async def is_bot_chat_admin(bot, chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

async def send_ephemeral(
    bot,
    chat_id: int,
    receiver_user_id: int,
    text: str,
    reply_markup=None,
    reply_to_id: int = None,
    parse_mode=ParseMode.HTML,
    callback_query_id: str = None,
) -> Optional[dict]:
    """
    Отправить эфемерное сообщение (видно только receiver_user_id).
    """
    # Проверяем, админ ли бот
    bot_is_admin = await is_bot_chat_admin(bot, chat_id)
    if not bot_is_admin and not callback_query_id:
        log.debug("Бот не админ и нет callback_query_id")
        return None

    kw = {
        "chat_id": chat_id,
        "text": text,
        "receiver_user_id": receiver_user_id,
        "parse_mode": parse_mode,
    }
    if callback_query_id:
        kw["callback_query_id"] = callback_query_id
    if reply_to_id:
        kw["reply_parameters"] = {"message_id": reply_to_id}
    if reply_markup:
        try:
            kw["reply_markup"] = reply_markup.to_dict()
        except Exception:
            pass

    try:
        result = await bot.do_api_request("sendMessage", api_kwargs=kw)
        if isinstance(result, dict) and result.get("ephemeral_message_id"):
            log.info(f"Эфемерное сообщение отправлено: {result.get('ephemeral_message_id')}")
            return result
        log.debug("Сервер не вернул ephemeral_message_id")
        return None
    except Exception as e:
        log.debug(f"send_ephemeral не удался: {e}")
        return None

# ─── Поиск пользователя по username ──────────────────────────────

async def resolve_username(bot, username: str, chat_id: int) -> Optional[int]:
    """
    Пытается найти user_id по username в чате.
    """
    # Убираем @ если есть
    username = username.lstrip("@")
    
    try:
        # Пробуем получить участника по username через get_chat_member
        # Это работает только если пользователь есть в чате
        members = await bot.get_chat_administrators(chat_id)
        for member in members:
            user = member.user
            if user.username and user.username.lower() == username.lower():
                return user.id
        
        # Если не нашли среди админов, пробуем через get_chat
        # (не работает для обычных пользователей)
        # Вместо этого попробуем через get_chat_member с username?
        # Нет, get_chat_member требует user_id.
        
        # Последний способ: используем get_chat для публичных пользователей
        # Но это не всегда работает
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                return chat.id
        except Exception:
            pass
            
    except Exception as e:
        log.debug(f"resolve_username ошибка: {e}")
    
    return None

# ─── Inline-обработчик ─────────────────────────────────────────────

async def on_inline_query(update: Update, context) -> None:
    """
    При inline-запросе @BotName текст анализируется.
    Если найдено упоминание пользователя (@username), показываем кнопку.
    """
    query = update.inline_query
    q_text = (query.query or "").strip()
    
    # Если запрос пустой — ничего не показываем
    if not q_text:
        await query.answer([], cache_time=60, is_personal=True)
        return

    log.info(f"Inline-запрос: {q_text} от {query.from_user.id} в чате {query.chat_id}")

    # Ищем упоминание: @username
    mention_match = re.search(r"@(\w+)", q_text)
    username = mention_match.group(1) if mention_match else None

    # Если есть @username, но это имя самого бота — игнорируем
    if username:
        bot_info = await context.bot.get_me()
        if username.lower() == bot_info.username.lower():
            # Пользователь упомянул бота, но не указал получателя
            # Показываем подсказку
            article = InlineQueryResultArticle(
                id="help",
                title="📨 Укажите получателя",
                description="Напишите: @ИмяБота @username текст",
                input_message_content=InputTextMessageContent(
                    "Пример использования:\n"
                    "`@ИмяБота @username Привет!`\n\n"
                    "После выбора этой подсказки введите правильный запрос.",
                    parse_mode=ParseMode.MARKDOWN,
                ),
            )
            await query.answer([article], cache_time=60, is_personal=True)
            return

    if not username:
        # Если нет @username, не показываем результат
        await query.answer([], cache_time=60, is_personal=True)
        return

    # Получаем текст сообщения (всё, что после @username)
    pos = q_text.find(f"@{username}")
    if pos != -1:
        msg_text = q_text[pos + len(username) + 1:].strip()
    else:
        msg_text = q_text

    if not msg_text:
        msg_text = "Привет! Это эфемерное сообщение."

    # Создаём уникальный ID для этого запроса
    result_id = str(uuid.uuid4())[:8]

    # Сохраняем данные
    _ephemeral_data[result_id] = {
        'receiver_username': username,
        'text': msg_text,
        'chat_id': query.chat_id,
        'from_user_id': query.from_user.id,
    }

    # Кнопка для отправки
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить @{username}",
            callback_data=f"ephem_send:{result_id}"
        )]
    ])

    # Создаём статью с результатом
    article = InlineQueryResultArticle(
        id=result_id,
        title=f"📨 Отправить эфемерное сообщение @{username}",
        description=f"Только для @{username}",
        input_message_content=InputTextMessageContent(
            f"📨 Нажмите кнопку, чтобы отправить сообщение **@{username}**\n\n"
            f"Сообщение: {msg_text[:100]}{'...' if len(msg_text) > 100 else ''}",
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=kb,
    )

    await query.answer([article], cache_time=10, is_personal=True)
    log.info(f"Inline-результат показан для {username}")

# ─── Callback-обработчик ───────────────────────────────────────────

async def on_callback(update: Update, context) -> None:
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    from_user = query.from_user

    log.info(f"Callback: {data} от {from_user.id}")

    if not data.startswith("ephem_send:"):
        await query.answer()
        return

    result_id = data.split(":", 1)[1]
    data_dict = _ephemeral_data.get(result_id)
    
    if not data_dict:
        await query.answer("❌ Данные устарели, попробуйте снова.", show_alert=True)
        return

    receiver_username = data_dict.get('receiver_username')
    text = data_dict.get('text', "Привет!")
    original_chat_id = data_dict.get('chat_id')

    # Проверяем, что чат совпадает
    if original_chat_id != chat_id:
        await query.answer("❌ Этот запрос был сделан в другом чате.", show_alert=True)
        return

    # Находим user_id по username
    receiver_id = await resolve_username(context.bot, receiver_username, chat_id)
    
    if not receiver_id:
        await query.answer(
            f"❌ Не удалось найти пользователя @{receiver_username} в этом чате.\n"
            f"Убедитесь, что он есть в чате.",
            show_alert=True
        )
        return

    # Проверяем, админ ли бот
    bot_is_admin = await is_bot_chat_admin(context.bot, chat_id)
    if not bot_is_admin:
        await query.answer(
            "❌ Бот должен быть администратором чата для отправки эфемерных сообщений.",
            show_alert=True
        )
        return

    # Отправляем эфемерное сообщение
    result = await send_ephemeral(
        context.bot,
        chat_id,
        receiver_id,
        text,
        reply_to_id=query.message.message_id,
        parse_mode=ParseMode.HTML,
        callback_query_id=query.id,
    )

    if result:
        await query.answer("✅ Сообщение отправлено!", show_alert=False)
        # Удаляем данные из памяти
        _ephemeral_data.pop(result_id, None)
    else:
        await query.answer(
            "❌ Не удалось отправить эфемерное сообщение.\n"
            "Возможно, функция не поддерживается сервером Telegram.",
            show_alert=True
        )

# ─── Команда /start ─────────────────────────────────────────────────

async def cmd_start(update: Update, context) -> None:
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Используй меня в группе через Inline-режим:\n"
        "1️⃣ Напиши в поле ввода: `@secretnobot @username текст`\n"
        "2️⃣ Выбери появившуюся кнопку\n"
        "3️⃣ Я отправлю эфемерное сообщение только указанному пользователю\n\n"
        "⚠️ Бот должен быть **администратором** группы!\n"
        "📌 Пример: `@secretnobot @Verifure Привет, как дела?`"
    )

# ─── Запуск ─────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("🚀 Бот запущен. Ожидаем inline-запросы...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
