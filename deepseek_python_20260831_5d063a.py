#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
НЕ требует прав администратора!
Использует упоминание вместо эфемерного режима.
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

_data = {}

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
                description="@ИмяБота @username текст",
                input_message_content=InputTextMessageContent(
                    "Пример: @ИмяБота @john Привет!"
                ),
            )
        ], cache_time=60)
        return
    
    # Ищем @username
    mentions = re.findall(r"@(\w+)", text)
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    if not mentions:
        await query.answer([
            InlineQueryResultArticle(
                id="no_mention",
                title="❌ Укажите получателя",
                description="Напишите @username",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username\n\n"
                    "Формат: @ИмяБота @username Текст"
                ),
            )
        ], cache_time=60)
        return
    
    username = mentions[0]
    
    # Извлекаем текст
    pos = text.find(f"@{username}")
    if pos != -1:
        msg = text[pos + len(username) + 1:].strip()
        message_text = msg if msg else f"Привет, @{username}!"
    else:
        message_text = f"Привет, @{username}!"
    
    data_id = str(uuid.uuid4())[:8]
    
    _data[data_id] = {
        'username': username,
        'text': message_text,
        'chat_id': query.chat_id,
    }
    
    # Кнопка для отправки
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
    
    # Отправляем сообщение с упоминанием
    # Это НЕ эфемерное, но его увидят все, 
    # но упоминание подсветит нужного пользователя
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📨 **Сообщение для @{username}**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=query.message.message_id,
        )
        
        await query.answer("✅ Отправлено!", show_alert=False)
        log.info(f"Сообщение отправлено с упоминанием @{username}")
            
    except Exception as e:
        log.error(f"Ошибка: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
    
    _data.pop(data_id, None)

# ─── /start ────────────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Бот для упоминаний**\n\n"
        "**Как использовать:**\n"
        "1️⃣ В поле ввода начните писать:\n"
        "   `@ИмяБота @username текст`\n"
        "2️⃣ Выберите появившуюся кнопку\n"
        "3️⃣ Сообщение отправится с упоминанием @username\n\n"
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
