#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Работает только если бот администратор группы.
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
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
)

# ─── Конфиг ─────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не задан")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("ephemeral_bot")

# Хранилище данных для Inline-запросов
_ephemeral_data: dict = {}

# ─── Вспомогательные функции ──────────────────────────────────────

async def is_bot_admin(bot, chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        log.error(f"Ошибка проверки админа: {e}")
        return False

async def get_user_id_by_username(bot, username: str, chat_id: int) -> Optional[int]:
    """
    Пытается найти user_id по username в чате.
    """
    username = username.lstrip("@").lower()
    
    try:
        # Получаем всех участников чата (только если бот админ)
        # Это ограничение Telegram — без админа нельзя получить список участников
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            user = admin.user
            if user.username and user.username.lower() == username:
                return user.id
        
        # Если не нашли среди админов, пробуем получить chat по username
        # Работает только если пользователь публичный
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                # Проверяем, есть ли этот пользователь в чате
                try:
                    member = await bot.get_chat_member(chat_id, chat.id)
                    if member:
                        return chat.id
                except Exception:
                    pass
        except Exception:
            pass
            
    except Exception as e:
        log.error(f"Ошибка поиска пользователя {username}: {e}")
    
    return None

# ─── Обработчик Inline-запросов ──────────────────────────────────

async def on_inline_query(update: Update, context) -> None:
    """
    Обрабатывает inline-запросы.
    Формат: @ИмяБота @username текст
    """
    query = update.inline_query
    q_text = query.query.strip()
    
    log.info(f"Inline запрос: '{q_text}' от {query.from_user.id}")
    
    # Если запрос пустой — показываем справку
    if not q_text:
        await query.answer([
            InlineQueryResultArticle(
                id="help",
                title="📨 Как использовать",
                description="@ИмяБота @username текст сообщения",
                input_message_content=InputTextMessageContent(
                    "Пример использования:\n"
                    "`@ИмяБота @john Привет!`\n\n"
                    "После выбора этого сообщения начните ввод заново."
                ),
            )
        ], cache_time=60, is_personal=True)
        return
    
    # Ищем @username в запросе
    # Ищем любые слова, начинающиеся с @
    mentions = re.findall(r"@(\w+)", q_text)
    
    # Убираем имя самого бота из списка
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username.lower()
    mentions = [m for m in mentions if m.lower() != bot_username]
    
    if not mentions:
        # Нет упоминаний пользователей — показываем подсказку
        await query.answer([
            InlineQueryResultArticle(
                id="no_mention",
                title="❌ Укажите получателя",
                description="Напишите @username в запросе",
                input_message_content=InputTextMessageContent(
                    "❌ Не найден @username в запросе.\n\n"
                    "Правильный формат:\n"
                    "`@ИмяБота @john Привет!`"
                ),
            )
        ], cache_time=60, is_personal=True)
        return
    
    # Берем первого найденного пользователя
    username = mentions[0]
    
    # Получаем текст сообщения (всё после @username)
    # Находим позицию первого упоминания
    pos = q_text.find(f"@{username}")
    if pos != -1:
        # Берем текст после упоминания
        # Убираем само упоминание и пробелы после него
        rest = q_text[pos + len(username) + 1:].strip()
        if rest:
            msg_text = rest
        else:
            msg_text = f"Привет, @{username}!"
    else:
        msg_text = f"Привет, @{username}!"
    
    # Создаем уникальный ID
    result_id = str(uuid.uuid4())[:8]
    
    # Сохраняем данные
    _ephemeral_data[result_id] = {
        'username': username,
        'text': msg_text,
        'chat_id': query.chat_id,
    }
    
    # Создаем кнопку для отправки
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить @{username}",
            callback_data=f"send:{result_id}"
        )]
    ])
    
    # Создаем результат
    article = InlineQueryResultArticle(
        id=result_id,
        title=f"📨 Отправить @{username}",
        description=f"Только для @{username}: {msg_text[:50]}",
        input_message_content=InputTextMessageContent(
            f"📨 Нажмите кнопку, чтобы отправить сообщение **@{username}**\n\n"
            f"Сообщение: {msg_text}",
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=kb,
    )
    
    await query.answer([article], cache_time=10, is_personal=True)
    log.info(f"Показан результат для @{username}")

# ─── Обработчик Callback ──────────────────────────────────────────

async def on_callback(update: Update, context) -> None:
    """Обрабатывает нажатие на кнопку."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    
    log.info(f"Callback: {data} от {query.from_user.id}")
    
    if not data.startswith("send:"):
        await query.answer()
        return
    
    result_id = data.split(":", 1)[1]
    data_dict = _ephemeral_data.get(result_id)
    
    if not data_dict:
        await query.answer("❌ Данные устарели", show_alert=True)
        return
    
    username = data_dict['username']
    text = data_dict['text']
    original_chat_id = data_dict['chat_id']
    
    # Проверяем чат
    if original_chat_id != chat_id:
        await query.answer("❌ Запрос из другого чата", show_alert=True)
        return
    
    # Проверяем, админ ли бот
    if not await is_bot_admin(context.bot, chat_id):
        await query.answer(
            "❌ Бот должен быть администратором чата!\n"
            "Добавьте бота в администраторы и попробуйте снова.",
            show_alert=True
        )
        return
    
    # Ищем user_id по username
    user_id = await get_user_id_by_username(context.bot, username, chat_id)
    
    if not user_id:
        await query.answer(
            f"❌ Не найден @{username} в этом чате",
            show_alert=True
        )
        return
    
    # Отправляем эфемерное сообщение
    try:
        # Используем прямой запрос к API с receiver_user_id
        result = await context.bot.do_api_request(
            "sendMessage",
            api_kwargs={
                "chat_id": chat_id,
                "text": text,
                "receiver_user_id": user_id,
                "parse_mode": ParseMode.HTML,
                "callback_query_id": query.id,
            }
        )
        
        if result and result.get("ephemeral_message_id"):
            await query.answer("✅ Сообщение отправлено!", show_alert=False)
            log.info(f"Эфемерное сообщение отправлено {user_id}")
        else:
            await query.answer(
                "⚠️ Сообщение отправлено, но сервер не подтвердил эфемерный режим.\n"
                "Возможно, функция ещё не активна.",
                show_alert=True
            )
            
    except Exception as e:
        log.error(f"Ошибка отправки: {e}")
        await query.answer(
            f"❌ Ошибка: {str(e)[:100]}",
            show_alert=True
        )
    
    # Удаляем данные
    _ephemeral_data.pop(result_id, None)

# ─── Команда /start ─────────────────────────────────────────────────

async def cmd_start(update: Update, context) -> None:
    """Приветственное сообщение."""
    await update.message.reply_text(
        "👋 **Эфемерный бот**\n\n"
        "Отправляйте эфемерные сообщения в группах!\n\n"
        "**Как использовать:**\n"
        "1️⃣ В поле ввода напишите:\n"
        "   `@ИмяБота @username текст`\n"
        "2️⃣ Выберите появившуюся кнопку\n"
        "3️⃣ Сообщение увидят только вы и @username\n\n"
        "⚠️ **Важно:**\n"
        "• Бот должен быть **администратором** группы\n"
        "• Получатель должен быть в группе\n"
        "• Работает только в группах, не в личке\n\n"
        "📌 Пример:\n"
        "`@MyBot @john Привет, как дела?`",
        parse_mode=ParseMode.MARKDOWN
    )

# ─── Запуск ─────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))
    
    log.info("🚀 Бот запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
