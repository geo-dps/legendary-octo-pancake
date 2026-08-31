#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Работает как все остальные боты — через удаление.
Формат: @botusername текст @username
"""

import logging
import os
import re
import asyncio
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

_data = {}

# ─── Поиск пользователя по username ──────────────────────────────

async def find_user_by_username(bot, username: str, chat_id: int):
    """Находит пользователя по @username в чате."""
    username = username.lstrip("@").lower()
    
    try:
        # Ищем среди администраторов
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            user = admin.user
            if user.username and user.username.lower() == username:
                return user
        
        # Через get_chat (для публичных)
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                try:
                    member = await bot.get_chat_member(chat_id, chat.id)
                    if member:
                        return member.user
                except Exception:
                    pass
        except Exception:
            pass
        
        # Через get_chat_members (нужны права)
        try:
            members = await bot.get_chat_members(chat_id, limit=200)
            for member in members:
                user = member.user
                if user.username and user.username.lower() == username:
                    return user
        except Exception:
            pass
            
    except Exception as e:
        log.error(f"Ошибка поиска: {e}")
    
    return None

# ─── Inline-обработчик ────────────────────────────────────────────

async def on_inline_query(update: Update, context):
    query = update.inline_query
    text = query.query.strip()
    
    log.info(f"Inline запрос: '{text}'")
    
    if not text:
        await query.answer([
            InlineQueryResultArticle(
                id="help",
                title="📨 Как использовать",
                description="@ИмяБота текст @username",
                input_message_content=InputTextMessageContent(
                    "Пример: @MyBot Привет! @john"
                ),
            )
        ], cache_time=60)
        return
    
    # Ищем все @username
    mentions = re.findall(r"@(\w+)", text)
    
    # Убираем имя бота
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    if not mentions:
        await query.answer([
            InlineQueryResultArticle(
                id="no_mention",
                title="❌ Укажите получателя",
                description="Напишите @username в конце",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username\n\n"
                    "Формат: @ИмяБота Текст @username"
                ),
            )
        ], cache_time=60)
        return
    
    # Берем ПОСЛЕДНЕГО пользователя
    username = mentions[-1]
    
    # Извлекаем текст
    pos = text.rfind(f"@{username}")
    if pos != -1:
        before = text[:pos].strip()
        if before.lower().startswith(f"@{bot_username}"):
            before = before[len(bot_username) + 2:].strip()
        message_text = before if before else f"Привет, @{username}!"
    else:
        message_text = f"Привет, @{username}!"
    
    data_id = str(uuid.uuid4())[:8]
    
    _data[data_id] = {
        'username': username,
        'text': message_text,
        'chat_id': query.chat_id,
    }
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить @{username}",
            callback_data=f"send:{data_id}"
        )]
    ])
    
    article = InlineQueryResultArticle(
        id=data_id,
        title=f"📨 Отправить @{username}",
        description=f"{message_text[:50]}",
        input_message_content=InputTextMessageContent(
            f"📨 **Сообщение для @{username}**\n\n"
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
    
    # Ищем пользователя
    user = await find_user_by_username(context.bot, username, chat_id)
    
    if not user:
        await query.answer(
            f"❌ Пользователь @{username} не найден в чате",
            show_alert=True
        )
        return
    
    log.info(f"Найден пользователь: {user.id} (@{user.username})")
    
    # Отправляем сообщение с упоминанием
    try:
        # Отправляем сообщение
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"📨 **Сообщение для @{username}**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
        )
        
        # Пытаемся удалить сообщение бота (если есть права)
        try:
            await context.bot.delete_message(chat_id, msg.message_id)
            log.info("Сообщение бота удалено")
        except Exception as e:
            log.debug(f"Не удалось удалить сообщение бота: {e}")
        
        # Отвечаем на callback
        await query.answer("✅ Отправлено!", show_alert=False)
        log.info(f"Сообщение отправлено с упоминанием @{username}")
            
    except Exception as e:
        log.error(f"Ошибка: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
    
    _data.pop(data_id, None)

# ─── Команда /start ─────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот для приватных сообщений**\n\n"
        "**Формат:**\n"
        "`@ИмяБота Текст @username`\n\n"
        "**Пример:**\n"
        "`@MyBot Привет, как дела? @john`\n\n"
        "📌 Сообщение увидят все, но с упоминанием @username",
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
