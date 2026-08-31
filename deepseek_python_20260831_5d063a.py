#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Поддерживает два формата:
1. @botusername текст @username
2. @botusername текст 123456789 (user_id)
Команда /id показывает ID пользователя.
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
    MessageHandler,
    filters,
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

# ─── Команда /id ──────────────────────────────────────────────────

async def cmd_id(update: Update, context):
    """Показывает ID пользователя."""
    message = update.message
    
    # Если есть реплай — показываем ID того, на кого реплай
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        text = (
            f"🆔 **ID пользователя**\n\n"
            f"👤 {target.first_name}"
            f"{' (@' + target.username + ')' if target.username else ''}\n"
            f"📌 `{target.id}`\n\n"
            f"Используйте этот ID в inline-режиме:\n"
            f"`@{context.bot.username} Привет! {target.id}`"
        )
    else:
        # Показываем ID самого пользователя
        user = message.from_user
        text = (
            f"🆔 **Ваш ID**\n\n"
            f"👤 {user.first_name}"
            f"{' (@' + user.username + ')' if user.username else ''}\n"
            f"📌 `{user.id}`\n\n"
            f"Чтобы отправить эфемерное сообщение:\n"
            f"`@{context.bot.username} Текст {user.id}`"
        )
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

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
                description="@ИмяБота текст @username или ID",
                input_message_content=InputTextMessageContent(
                    "📌 **Форматы:**\n\n"
                    "1️⃣ По username:\n"
                    "`@bot текст @username`\n\n"
                    "2️⃣ По ID:\n"
                    "`@bot текст 123456789`\n\n"
                    "💡 Получить ID: `/id` (ответом на сообщение)"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        ], cache_time=60)
        return
    
    # Ищем все @username
    mentions = re.findall(r"@(\w+)", text)
    
    # Убираем имя бота
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    # Ищем ID (числа в конце)
    # Ищем последнее число в тексте
    numbers = re.findall(r"\b(\d{5,})\b", text)
    user_id = int(numbers[-1]) if numbers else None
    
    # Определяем, что у нас: username или ID
    receiver_username = mentions[-1] if mentions else None
    receiver_id = user_id
    
    # Если ничего не найдено
    if not receiver_username and not receiver_id:
        await query.answer([
            InlineQueryResultArticle(
                id="no_target",
                title="❌ Укажите получателя",
                description="Напишите @username или ID в конце",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username или ID\n\n"
                    "📌 **Форматы:**\n"
                    "`@bot текст @username`\n"
                    "`@bot текст 123456789`\n\n"
                    "💡 Получить ID: `/id`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        ], cache_time=60)
        return
    
    # Извлекаем текст сообщения
    # Если есть username
    if receiver_username:
        pos = text.rfind(f"@{receiver_username}")
        if pos != -1:
            before = text[:pos].strip()
            if before.lower().startswith(f"@{bot_username}"):
                before = before[len(bot_username) + 2:].strip()
            message_text = before if before else f"Привет, @{receiver_username}!"
        else:
            message_text = f"Привет, @{receiver_username}!"
    else:
        # Если есть ID
        pos = text.rfind(str(receiver_id))
        if pos != -1:
            before = text[:pos].strip()
            if before.lower().startswith(f"@{bot_username}"):
                before = before[len(bot_username) + 2:].strip()
            message_text = before if before else f"Привет, пользователь {receiver_id}!"
        else:
            message_text = f"Привет, пользователь {receiver_id}!"
    
    data_id = str(uuid.uuid4())[:8]
    
    _data[data_id] = {
        'username': receiver_username,
        'user_id': receiver_id,
        'text': message_text,
        'chat_id': query.chat_id,
        'from_user_id': query.from_user.id,
    }
    
    # Кнопка
    label = f"@{receiver_username}" if receiver_username else f"ID {receiver_id}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить {label}",
            callback_data=f"send:{data_id}"
        )]
    ])
    
    article = InlineQueryResultArticle(
        id=data_id,
        title=f"📨 Отправить {label}",
        description=f"{message_text[:50]}",
        input_message_content=InputTextMessageContent(
            f"📨 **Эфемерное сообщение для {label}**\n\n"
            f"Текст: {message_text}",
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=kb,
    )
    
    await query.answer([article], cache_time=10)
    log.info(f"Показан результат для {label}")

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
    
    username = saved.get('username')
    user_id = saved.get('user_id')
    text = saved['text']
    
    # Определяем получателя
    target_user = None
    target_id = None
    
    if user_id:
        # Если есть ID — используем его
        target_id = user_id
        log.info(f"Используем ID: {target_id}")
    elif username:
        # Ищем пользователя по username
        target_user = await find_user_by_username(context.bot, username, chat_id)
        if target_user:
            target_id = target_user.id
            log.info(f"Найден пользователь: {target_id} (@{target_user.username})")
    
    if not target_id:
        await query.answer(
            f"❌ Не удалось найти получателя\n\n"
            f"{'Пользователь @' + username + ' не найден в чате' if username else 'ID не указан'}\n\n"
            f"💡 Используйте `/id` чтобы узнать ID пользователя",
            show_alert=True
        )
        return
    
    # Отправляем эфемерное сообщение
    try:
        # Пробуем отправить эфемерное через callback_query
        result = await context.bot.do_api_request(
            "sendMessage",
            api_kwargs={
                "chat_id": chat_id,
                "text": text,
                "receiver_user_id": target_id,
                "parse_mode": ParseMode.HTML,
                "callback_query_id": query.id,
            }
        )
        
        if result and result.get("ephemeral_message_id"):
            await query.answer("✅ Эфемерное сообщение отправлено!", show_alert=False)
            log.info(f"Эфемерное сообщение отправлено {target_id}")
        else:
            # Если не получилось — отправляем обычное и удаляем
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"📨 **Сообщение**\n\n{text}",
                parse_mode=ParseMode.MARKDOWN,
            )
            try:
                await context.bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
            await query.answer("✅ Отправлено!", show_alert=False)
            
    except Exception as e:
        log.error(f"Ошибка: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
    
    _data.pop(data_id, None)

# ─── /start ────────────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Эфемерный бот**\n\n"
        "📌 **Форматы:**\n\n"
        "1️⃣ По username:\n"
        "`@bot Текст @username`\n\n"
        "2️⃣ По ID (рекомендуется):\n"
        "`@bot Текст 123456789`\n\n"
        "💡 **Как узнать ID:**\n"
        "• `/id` — ваш ID\n"
        "• `/id` (ответом на сообщение) — ID пользователя\n\n"
        "⚠️ Бот должен быть **администратором** группы!",
        parse_mode=ParseMode.MARKDOWN
    )

# ─── Запуск ─────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))
    
    log.info("🚀 Бот запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
