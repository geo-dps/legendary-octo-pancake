#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Простая и рабочая версия.
"""

import logging
import os
import re
import uuid

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Хранилище данных
_data = {}

# ─── Проверка админа ──────────────────────────────────────────────

async def is_bot_admin(bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

# ─── Поиск пользователя ───────────────────────────────────────────

async def find_user_by_username(bot, username: str, chat_id: int):
    """Находит пользователя по @username в чате."""
    username = username.lstrip("@").lower()
    
    try:
        # Пробуем найти среди участников
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.username and admin.user.username.lower() == username:
                return admin.user
        
        # Пробуем получить по username (работает для публичных пользователей)
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                # Проверяем, есть ли в чате
                try:
                    member = await bot.get_chat_member(chat_id, chat.id)
                    if member:
                        return member.user
                except Exception:
                    pass
        except Exception:
            pass
    except Exception as e:
        log.error(f"Ошибка поиска: {e}")
    
    return None

# ─── Inline-обработчик ────────────────────────────────────────────

async def on_inline_query(update: Update, context):
    query = update.inline_query
    text = query.query.strip()
    
    log.info(f"Inline запрос: '{text}' от {query.from_user.id}")
    
    # Если запрос пустой — показываем справку
    if not text:
        await query.answer([
            InlineQueryResultArticle(
                id="help",
                title="📨 Как использовать",
                description="@ИмяБота @username текст",
                input_message_content=InputTextMessageContent(
                    "Пример: @ИмяБота @john Привет!\n\n"
                    "После выбора этого сообщения начните ввод заново."
                ),
            )
        ], cache_time=60)
        return
    
    # Ищем все @username в тексте
    mentions = re.findall(r"@(\w+)", text)
    
    # Убираем имя бота
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    if not mentions:
        # Нет упоминаний
        await query.answer([
            InlineQueryResultArticle(
                id="no_mention",
                title="❌ Укажите получателя",
                description="Напишите @username в запросе",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username\n\n"
                    "Правильный формат:\n"
                    "@ИмяБота @username Текст"
                ),
            )
        ], cache_time=60)
        return
    
    # Берем первого пользователя
    username = mentions[0]
    
    # Извлекаем текст сообщения
    # Находим позицию первого упоминания пользователя
    for mention in mentions:
        pos = text.find(f"@{mention}")
        if pos != -1:
            # Текст после упоминания
            msg = text[pos + len(mention) + 1:].strip()
            if msg:
                message_text = msg
                break
    else:
        message_text = f"Привет, @{username}!"
    
    # Создаем уникальный ID
    data_id = str(uuid.uuid4())[:8]
    
    # Сохраняем данные
    _data[data_id] = {
        'username': username,
        'text': message_text,
        'chat_id': query.chat_id,
        'from_user': query.from_user.id,
    }
    
    # Создаем кнопку
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить @{username}",
            callback_data=f"send:{data_id}"
        )]
    ])
    
    # Создаем результат
    article = InlineQueryResultArticle(
        id=data_id,
        title=f"📨 Отправить @{username}",
        description=f"{message_text[:50]}",
        input_message_content=InputTextMessageContent(
            f"📨 **Эфемерное сообщение для @{username}**\n\n"
            f"Текст: {message_text}",
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=kb,
    )
    
    await query.answer([article], cache_time=10)
    log.info(f"Показан результат для @{username}")

# ─── Callback-обработчик ──────────────────────────────────────────

async def on_callback(update: Update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    
    log.info(f"Callback: {data}")
    
    if not data.startswith("send:"):
        await query.answer()
        return
    
    data_id = data.split(":", 1)[1]
    saved = _data.get(data_id)
    
    if not saved:
        await query.answer("❌ Данные устарели", show_alert=True)
        return
    
    username = saved['username']
    text = saved['text']
    
    # Проверяем админа
    if not await is_bot_admin(context.bot, chat_id):
        await query.answer(
            "❌ Бот должен быть администратором!\n"
            "Добавьте бота в админы и попробуйте снова.",
            show_alert=True
        )
        return
    
    # Ищем пользователя
    user = await find_user_by_username(context.bot, username, chat_id)
    
    if not user:
        await query.answer(
            f"❌ Пользователь @{username} не найден в чате",
            show_alert=True
        )
        return
    
    # Отправляем эфемерное сообщение
    try:
        result = await context.bot.do_api_request(
            "sendMessage",
            api_kwargs={
                "chat_id": chat_id,
                "text": text,
                "receiver_user_id": user.id,
                "parse_mode": ParseMode.HTML,
                "callback_query_id": query.id,
            }
        )
        
        if result and result.get("ephemeral_message_id"):
            await query.answer("✅ Отправлено!", show_alert=False)
            log.info(f"Эфемерное сообщение отправлено {user.id}")
        else:
            await query.answer(
                "⚠️ Отправлено, но без эфемерного режима",
                show_alert=True
            )
            
    except Exception as e:
        log.error(f"Ошибка: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
    
    _data.pop(data_id, None)

# ─── /start ────────────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Эфемерный бот**\n\n"
        "**Как использовать:**\n"
        "1️⃣ В поле ввода начните писать:\n"
        "   `@ИмяБота @username текст`\n"
        "2️⃣ Выберите появившуюся кнопку\n"
        "3️⃣ Сообщение увидят только вы и @username\n\n"
        "⚠️ Бот должен быть **администратором** группы!\n\n"
        "📌 Пример:\n"
        "`@MyBot @john Привет!`",
        parse_mode=ParseMode.MARKDOWN
    )

# ─── Запуск ─────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))
    
    log.info("🚀 Бот запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
