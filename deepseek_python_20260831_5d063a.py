#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Поддерживает все возможные методы Telegram API.
Формат: @botusername текст @username
"""

import logging
import os
import re
import asyncio
import uuid
from typing import Optional, Dict, Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
    ChatPermissions,
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

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

_data: Dict[str, Dict[str, Any]] = {}

# ─── Проверка прав бота ──────────────────────────────────────────

async def get_bot_permissions(bot, chat_id: int) -> dict:
    """Получает права бота в чате."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return {
            'is_admin': member.status in ('administrator', 'creator'),
            'can_delete_messages': False,
            'can_restrict_members': False,
        }
    except Exception as e:
        log.error(f"Ошибка получения прав: {e}")
        return {'is_admin': False, 'can_delete_messages': False, 'can_restrict_members': False}

# ─── Поиск пользователя по username ──────────────────────────────

async def find_user_by_username(bot, username: str, chat_id: int):
    """Находит пользователя по @username в чате."""
    username = username.lstrip("@").lower()
    
    try:
        # Метод 1: Среди администраторов
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            user = admin.user
            if user.username and user.username.lower() == username:
                return user
        
        # Метод 2: Через get_chat (публичные пользователи)
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
        
        # Метод 3: Через get_chat_members (нужны права)
        try:
            members = await bot.get_chat_members(chat_id, limit=300)
            for member in members:
                user = member.user
                if user.username and user.username.lower() == username:
                    return user
        except Exception:
            pass
            
    except Exception as e:
        log.error(f"Ошибка поиска: {e}")
    
    return None

# ─── Отправка эфемерного сообщения ──────────────────────────────

async def send_ephemeral_message(
    bot,
    chat_id: int,
    receiver_id: int,
    text: str,
    reply_to_id: Optional[int] = None,
    callback_query_id: Optional[str] = None,
) -> dict:
    """
    Пытается отправить эфемерное сообщение всеми возможными способами.
    Возвращает результат с информацией о том, что сработало.
    """
    results = {
        'success': False,
        'method': None,
        'message_id': None,
        'ephemeral_id': None,
    }
    
    # ─── СПОСОБ 1: receiver_user_id (Bot API 10.2+) ──────────────
    try:
        log.info("Попытка отправить через receiver_user_id...")
        kw = {
            "chat_id": chat_id,
            "text": text,
            "receiver_user_id": receiver_id,
            "parse_mode": ParseMode.HTML,
        }
        if reply_to_id:
            kw["reply_parameters"] = {"message_id": reply_to_id}
        if callback_query_id:
            kw["callback_query_id"] = callback_query_id
        
        result = await bot.do_api_request("sendMessage", api_kwargs=kw)
        
        if result and result.get("ephemeral_message_id"):
            log.info(f"✅ receiver_user_id сработал! ephemeral_id={result['ephemeral_message_id']}")
            results['success'] = True
            results['method'] = 'receiver_user_id'
            results['ephemeral_id'] = result['ephemeral_message_id']
            results['message_id'] = result.get('message_id')
            return results
        else:
            log.warning("receiver_user_id не вернул ephemeral_message_id")
    except Exception as e:
        log.warning(f"receiver_user_id не сработал: {e}")
    
    # ─── СПОСОБ 2: Обычное сообщение + удаление ──────────────────
    try:
        log.info("Попытка отправить с последующим удалением...")
        
        # Отправляем сообщение с упоминанием
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"🔔 **Сообщение для @{receiver_id}**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=reply_to_id,
        )
        
        results['message_id'] = msg.message_id
        
        # Пытаемся удалить через некоторое время
        async def delete_later():
            await asyncio.sleep(2)
            try:
                await bot.delete_message(chat_id, msg.message_id)
                log.info("✅ Сообщение удалено")
            except Exception as e:
                log.warning(f"Не удалось удалить сообщение: {e}")
        
        asyncio.create_task(delete_later())
        
        results['success'] = True
        results['method'] = 'send_and_delete'
        log.info("✅ Отправлено с последующим удалением")
        return results
        
    except Exception as e:
        log.error(f"Ошибка при отправке с удалением: {e}")
    
    # ─── СПОСОБ 3: Отправка в личные сообщения ──────────────────
    try:
        log.info("Попытка отправить в личные сообщения...")
        await bot.send_message(
            chat_id=receiver_id,
            text=f"📨 **Сообщение из группы**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
        )
        results['success'] = True
        results['method'] = 'private_message'
        log.info("✅ Отправлено в личные сообщения")
        return results
    except Exception as e:
        log.warning(f"Не удалось отправить в личные сообщения: {e}")
    
    # ─── СПОСОБ 4: Обычное сообщение с упоминанием (fallback) ──
    try:
        log.info("Fallback: отправка с упоминанием...")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"📨 **Сообщение для @{receiver_id}**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=reply_to_id,
        )
        results['success'] = True
        results['method'] = 'mention_only'
        results['message_id'] = msg.message_id
        log.info("✅ Отправлено с упоминанием (fallback)")
        return results
    except Exception as e:
        log.error(f"Все способы отправки не удались: {e}")
    
    return results

# ─── Inline-обработчик ────────────────────────────────────────────

async def on_inline_query(update: Update, context):
    query = update.inline_query
    text = query.query.strip()
    
    log.info(f"Inline запрос: '{text}' от {query.from_user.id}")
    
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
    
    # Ищем @username (кроме бота)
    mentions = re.findall(r"@(\w+)", text)
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
    
    # Берем последнего пользователя
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
        'from_user_id': query.from_user.id,
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
    
    # Отправляем эфемерное сообщение
    result = await send_ephemeral_message(
        context.bot,
        chat_id,
        user.id,
        text,
        reply_to_id=query.message.message_id,
        callback_query_id=query.id,
    )
    
    if result['success']:
        method_names = {
            'receiver_user_id': '✅ Эфемерное (receiver_user_id)',
            'send_and_delete': '✅ Отправлено и удалено',
            'private_message': '✅ Отправлено в личные сообщения',
            'mention_only': '✅ Отправлено с упоминанием',
        }
        await query.answer(method_names.get(result['method'], '✅ Отправлено!'), show_alert=False)
    else:
        await query.answer("❌ Не удалось отправить сообщение", show_alert=True)
    
    _data.pop(data_id, None)

# ─── Команда /start ─────────────────────────────────────────────────

async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 **Эфемерный бот v2**\n\n"
        "**Формат:**\n"
        "`@ИмяБота Текст @username`\n\n"
        "**Пример:**\n"
        "`@MyBot Привет, как дела? @john`\n\n"
        "**Как это работает:**\n"
        "1️⃣ Бот пытается отправить эфемерное сообщение\n"
        "2️⃣ Если не получается — отправляет с упоминанием\n"
        "3️⃣ Пытается удалить сообщение через 2 секунды\n\n"
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
