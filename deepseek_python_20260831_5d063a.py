#!/usr/bin/env python3
"""
Эфемерные сообщения через Inline-режим.
Пользователь вводит @ИмяБота @username текст → появляется кнопка.
При нажатии → эфемерное сообщение в группе видит только @username.
"""

import logging
import os
import re
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
    TypeHandler,
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

# ─── Эфемерные сообщения ──────────────────────────────────────────
async def is_bot_chat_admin(bot, chat_id: int) -> bool:
    """Проверяет, является ли бот администратором чата (нужно для эфемерных сообщений)."""
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
    ephemeral_reply_message_id: int = None,
    bot_is_admin: bool = None,
) -> Optional[dict]:
    """
    Отправить эфемерное сообщение (видно только receiver_user_id).
    Возвращает Message (dict) при успехе, иначе None.
    """
    if bot_is_admin is None and not callback_query_id and not ephemeral_reply_message_id:
        bot_is_admin = await is_bot_chat_admin(bot, chat_id)

    if not (callback_query_id or ephemeral_reply_message_id or bot_is_admin):
        log.debug("Нет условий для эфемерного сообщения — пропускаем")
        return None

    kw = {
        "chat_id": chat_id,
        "text": text,
        "receiver_user_id": receiver_user_id,
        "parse_mode": parse_mode,
    }
    if callback_query_id:
        kw["callback_query_id"] = callback_query_id
    if ephemeral_reply_message_id:
        kw["reply_parameters"] = {"ephemeral_message_id": ephemeral_reply_message_id}
    elif reply_to_id:
        kw["reply_parameters"] = {"message_id": reply_to_id}
    if reply_markup:
        try:
            kw["reply_markup"] = reply_markup.to_dict()
        except Exception:
            pass

    try:
        result = await bot.do_api_request("sendMessage", api_kwargs=kw)
        if isinstance(result, dict) and result.get("ephemeral_message_id"):
            return result
        log.debug("Сервер не вернул ephemeral_message_id — функция не активна")
        return None
    except Exception as e:
        log.debug("send_ephemeral не удался: %s", e)
        return None

# ─── Inline-обработчик ─────────────────────────────────────────────
async def on_inline_query(update: Update, context) -> None:
    """
    При inline-запросе @BotName текст анализируется.
    Если найдено упоминание пользователя (@username или числовой ID),
    показываем кнопку для отправки эфемерного сообщения.
    """
    query = update.inline_query
    q_text = (query.query or "").strip()

    # Ищем упоминание: @username или числовой ID (цифры)
    mention_match = re.search(r"@(\w+)", q_text)
    user_id_match = re.search(r"\b(\d{5,})\b", q_text)  # ID пользователя (число)
    username = mention_match.group(1) if mention_match else None
    user_id = int(user_id_match.group(1)) if user_id_match else None

    if not username and not user_id:
        # Если нет упоминания, ничего не показываем
        await query.answer([], cache_time=60, is_personal=True)
        return

    # Сохраняем данные в контексте запроса (для callback'а)
    # Мы не можем передать user_id напрямую в callback_data из inline-результата,
    # поэтому мы передадим информацию через callback_data.
    # Создаём уникальный ID для этого результата.
    import uuid
    result_id = str(uuid.uuid4())[:8]

    # Текст сообщения, которое будет отправлено
    # Можно использовать текст, введённый пользователем, но лучше убрать упоминание бота.
    # Оставим только сообщение после упоминания.
    # Удалим из q_text всё до @username или ID
    if username:
        # Найдём позицию @username и возьмём текст после него
        pos = q_text.find(f"@{username}")
        if pos != -1:
            msg_text = q_text[pos + len(username) + 1:].strip()
        else:
            msg_text = q_text
    else:
        # для числового ID
        pos = q_text.find(str(user_id))
        if pos != -1:
            msg_text = q_text[pos + len(str(user_id)):].strip()
        else:
            msg_text = q_text

    if not msg_text:
        msg_text = "Привет! Это эфемерное сообщение."

    # Создаём результат с кнопкой
    # При клике на кнопку будет вызван callback с данными.
    # В callback_data закодируем: тип действия, chat_id (откуда запрос), receiver, текст.
    # Но chat_id мы получим из callback'а (query.message.chat.id), а receiver и текст передадим.
    # Так как текст может быть длинным, лучше передать его в callback_data? Ограничение 64 байта.
    # Поэтому мы сохраним сообщение в памяти по ключу, а в callback_data передадим ключ.
    # Создадим словарь для хранения данных по ключу result_id
    if not hasattr(context, 'ephemeral_data'):
        context.ephemeral_data = {}
    context.ephemeral_data[result_id] = {
        'receiver_username': username,
        'receiver_id': user_id,
        'text': msg_text,
        'chat_id': query.chat_id,  # чат, откуда запрос (группа)
    }

    # Кнопка с callback_data, содержащей result_id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📨 Отправить эфемерное сообщение",
            callback_data=f"ephem_send:{result_id}"
        )]
    ])

    # Создаём статью
    article = InlineQueryResultArticle(
        id=result_id,
        title=f"Отправить эфемерное сообщение",
        description=f"Только для {'@' + username if username else 'ID ' + str(user_id)}",
        input_message_content=InputTextMessageContent(
            "Нажмите кнопку, чтобы отправить эфемерное сообщение.",
            parse_mode=ParseMode.HTML,
        ),
        reply_markup=kb,
    )

    await query.answer([article], cache_time=5, is_personal=True)

# ─── Callback-обработчик ───────────────────────────────────────────
async def on_callback(update: Update, context) -> None:
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    from_user = query.from_user

    if data.startswith("ephem_send:"):
        result_id = data.split(":", 1)[1]
        # Получаем сохранённые данные
        ephemeral_data = getattr(context, 'ephemeral_data', {})
        data_dict = ephemeral_data.get(result_id)
        if not data_dict:
            await query.answer("❌ Данные устарели, попробуйте снова.", show_alert=True)
            return

        receiver_username = data_dict.get('receiver_username')
        receiver_id = data_dict.get('receiver_id')
        text = data_dict.get('text', "Привет! Это эфемерное сообщение.")
        original_chat_id = data_dict.get('chat_id')

        # Проверяем, что чат совпадает (чтобы нельзя было использовать из другого чата)
        if original_chat_id != chat_id:
            await query.answer("❌ Этот запрос был сделан в другом чате.", show_alert=True)
            return

        # Определяем receiver_user_id
        if receiver_id:
            receiver = receiver_id
        elif receiver_username:
            # Попробуем найти пользователя по username в этом чате
            try:
                # Используем get_chat_member, но нам нужен user_id
                # Проще: попробуем получить пользователя через get_chat
                # Но get_chat по username не возвращает ID, если это не публичный канал.
                # Лучше использовать resolve_username? Но нет такого метода.
                # Вместо этого можно попросить пользователя указать ID.
                await query.answer("❌ Укажите числовой ID пользователя или @username, который я могу разрешить.", show_alert=True)
                return
            except Exception:
                await query.answer("❌ Не удалось найти пользователя.", show_alert=True)
                return
        else:
            await query.answer("❌ Не указан получатель.", show_alert=True)
            return

        # Проверяем, является ли бот админом (для эфемерных сообщений)
        bot_is_admin = await is_bot_chat_admin(context.bot, chat_id)
        if not bot_is_admin:
            await query.answer("❌ Бот должен быть администратором чата для отправки эфемерных сообщений.", show_alert=True)
            return

        # Отправляем эфемерное сообщение
        result = await send_ephemeral(
            context.bot,
            chat_id,
            receiver,
            text,
            reply_to_id=query.message.message_id,
            parse_mode=ParseMode.HTML,
            callback_query_id=query.id,
            bot_is_admin=True,  # мы уже проверили
        )

        if result:
            await query.answer("✅ Сообщение отправлено!", show_alert=False)
            # Можно удалить данные из памяти
            ephemeral_data.pop(result_id, None)
        else:
            await query.answer("❌ Не удалось отправить эфемерное сообщение. Возможно, функция не поддерживается сервером.", show_alert=True)

    else:
        await query.answer()

# ─── Команда /start ─────────────────────────────────────────────────
async def cmd_start(update: Update, context) -> None:
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Используй меня в группе через Inline-режим:\n"
        "Напиши в поле ввода @ИмяБота @username текст\n"
        "Нажми на появившуюся кнопку, и я отправлю эфемерное сообщение "
        "только указанному пользователю.\n\n"
        "Бот должен быть администратором группы."
    )

# ─── Запуск ─────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("Бот запущен. Ожидаем inline-запросы...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()