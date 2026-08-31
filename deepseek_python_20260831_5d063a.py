#!/usr/bin/env python3
"""
Эфемерный бот v2
- /id (ответом) → показывает ID пользователя (сообщение удаляется через 5 сек)
- Inline: @bot текст @username или @bot текст 123456789
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
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_data = {}

# ─── Поиск пользователя ──────────────────────────────────────────

async def find_user_by_username(bot, username: str, chat_id: int):
    """Находит пользователя по @username в чате."""
    username = username.lstrip("@").lower()
    
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            user = admin.user
            if user.username and user.username.lower() == username:
                return user
        
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

# ─── Отправка эфемерного сообщения (через удаление) ─────────────

async def send_ephemeral(bot, chat_id, text, reply_to_id=None, delete_after=5):
    """
    Отправляет сообщение и удаляет его через delete_after секунд.
    Это эмуляция эфемерного сообщения.
    """
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_to_id,
        )
        
        # Запускаем таймер на удаление
        async def delete_later():
            await asyncio.sleep(delete_after)
            try:
                await bot.delete_message(chat_id, msg.message_id)
                log.info(f"Сообщение {msg.message_id} удалено")
            except Exception as e:
                log.debug(f"Не удалось удалить: {e}")
        
        asyncio.create_task(delete_later())
        return msg
    except Exception as e:
        log.error(f"Ошибка отправки: {e}")
        return None

# ─── Команда /id ──────────────────────────────────────────────────

async def cmd_id(update: Update, context):
    """Показывает ID пользователя (ответом или своего)."""
    msg = update.message
    chat_id = msg.chat_id
    
    # Если есть реплай — показываем ID того, на кого ответили
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
        user_id = target.id
        name = target.full_name or target.username or "Пользователь"
        text = f"🆔 ID пользователя <b>{name}</b>:\n<code>{user_id}</code>"
    else:
        # Иначе показываем ID отправителя
        user = msg.from_user
        user_id = user.id
        name = user.full_name or user.username or "Вы"
        text = f"🆔 Ваш ID:\n<code>{user_id}</code>"
    
    # Отправляем эфемерно (удаляется через 10 секунд)
    await send_ephemeral(context.bot, chat_id, text, reply_to_id=msg.message_id, delete_after=10)

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
                    "Примеры:\n"
                    "@MyBot Привет! @john\n"
                    "@MyBot Привет! 123456789"
                ),
            )
        ], cache_time=60)
        return
    
    # Ищем все @username и числа (ID)
    mentions = re.findall(r"@(\w+)", text)
    ids = re.findall(r"(?<!\d)(\d{5,})(?!\d)", text)  # числа от 5 цифр
    
    # Убираем имя бота из mentions
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    # Определяем получателя: сначала ID, потом username
    target_id = None
    target_username = None
    
    if ids:
        target_id = int(ids[-1])  # берем последнее число
    elif mentions:
        target_username = mentions[-1]
    else:
        await query.answer([
            InlineQueryResultArticle(
                id="no_target",
                title="❌ Укажите получателя",
                description="Напишите @username или ID в конце",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username или ID\n\n"
                    "Формат: @ИмяБота Текст @username\n"
                    "Или: @ИмяБота Текст 123456789"
                ),
            )
        ], cache_time=60)
        return
    
    # Извлекаем текст сообщения
    # Находим позицию последнего упоминания или ID
    if target_username:
        pos = text.rfind(f"@{target_username}")
    else:
        pos = text.rfind(str(target_id))
    
    if pos != -1:
        before = text[:pos].strip()
        if before.lower().startswith(f"@{bot_username}"):
            before = before[len(bot_username) + 2:].strip()
        message_text = before if before else "Привет!"
    else:
        message_text = "Привет!"
    
    data_id = str(uuid.uuid4())[:8]
    
    _data[data_id] = {
        'target_id': target_id,
        'target_username': target_username,
        'text': message_text,
        'chat_id': query.chat_id,
        'from_user_id': query.from_user.id,
    }
    
    # Кнопка
    label = f"@{target_username}" if target_username else f"ID {target_id}"
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
    
    target_id = saved.get('target_id')
    target_username = saved.get('target_username')
    text = saved['text']
    
    # Определяем получателя
    user = None
    if target_id:
        # Пробуем получить пользователя по ID
        try:
            user = await context.bot.get_chat(target_id)
        except Exception:
            pass
    elif target_username:
        user = await find_user_by_username(context.bot, target_username, chat_id)
    
    if not user:
        label = f"@{target_username}" if target_username else f"ID {target_id}"
        await query.answer(
            f"❌ Получатель {label} не найден в чате",
            show_alert=True
        )
        return
    
    user_id = user.id
    username = user.username or str(user_id)
    log.info(f"Отправка пользователю: {user_id} (@{username})")
    
    # Отправляем эфемерное сообщение (удаляется через 10 секунд)
    await send_ephemeral(
        context.bot,
        chat_id,
        f"📨 **Сообщение для @{username}**\n\n{text}",
        reply_to_id=query.message.message_id,
        delete_after=10
    )
    
    await query.answer("✅ Отправлено!", show_alert=False)
    _data.pop(data_id, None)

# ─── /start ────────────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Эфемерный бот v2**\n\n"
        "**Команды:**\n"
        "`/id` — показать свой ID (ответом на сообщение — ID того пользователя)\n\n"
        "**Inline-режим:**\n"
        "`@ИмяБота Текст @username`\n"
        "`@ИмяБота Текст 123456789`\n\n"
        "📌 Сообщения автоматически удаляются через 5-10 секунд",
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
