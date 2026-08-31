#!/usr/bin/env python3
"""
Игра Крокодил для Telegram
Пользователь загадывает слово через @botname слово
Остальные отгадывают, бот следит за правильным ответом
"""

import logging
import os
import re
import random
import string
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Хранилище игр: chat_id -> game_data
games: Dict[int, dict] = {}

# Списки слов для подсказок
WORD_CATEGORIES = {
    "животные": ["слон", "жираф", "крокодил", "тигр", "лев", "обезьяна", "заяц", "волк", "лиса", "медведь", "панда", "кенгуру"],
    "еда": ["пицца", "бургер", "суши", "мороженое", "шоколад", "торт", "печенье", "молоко", "сыр", "колбаса", "арбуз", "апельсин"],
    "профессии": ["врач", "учитель", "инженер", "программист", "дизайнер", "архитектор", "пилот", "водитель", "повар", "строитель", "юрист", "журналист"],
    "спорт": ["футбол", "баскетбол", "теннис", "хоккей", "волейбол", "плавание", "бокс", "шахматы", "гольф", "лыжи", "коньки", "скейтборд"],
    "музыка": ["гитара", "фортепиано", "скрипка", "барабан", "флейта", "труба", "виолончель", "арфа", "саксофон", "кларнет", "пианино", "контрабас"],
}

# Интересные слова
ALL_WORDS = sum(WORD_CATEGORIES.values(), [])

def get_random_word(category: str = None) -> tuple:
    """Возвращает случайное слово и его категорию"""
    if category and category in WORD_CATEGORIES:
        word = random.choice(WORD_CATEGORIES[category])
        return word, category
    else:
        # Случайная категория
        cat = random.choice(list(WORD_CATEGORIES.keys()))
        word = random.choice(WORD_CATEGORIES[cat])
        return word, cat

async def is_bot_admin(bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

# ─── Команды ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐊 **Игра Крокодил**\n\n"
        "**Как играть:**\n"
        "1️⃣ В поле ввода напишите:\n"
        "   `@ИмяБота слово` - загадать слово\n"
        "2️⃣ Бот выберет случайное слово или вы можете указать своё\n"
        "3️⃣ Остальные игроки пишут варианты в чат\n"
        "4️⃣ Кто первый угадает - тот победил!\n\n"
        "**Команды:**\n"
        "/start - показать это сообщение\n"
        "/stop - остановить текущую игру\n"
        "/word - подсказка (категория слова)\n"
        "/hint - показать первую букву\n\n"
        "**Пример:**\n"
        "`@MyBot крокодил`\n"
        "Игроки пишут: `крокодил` - и угадывают!\n\n"
        "🆓 Игра абсолютно бесплатна!",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        del games[chat_id]
        await update.message.reply_text("❌ Игра остановлена!")
    else:
        await update.message.reply_text("ℹ️ Нет активной игры.")

async def cmd_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает категорию загаданного слова"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("ℹ️ Нет активной игры. Загадайте слово через @бота")
        return
    
    game = games[chat_id]
    if not game.get('category'):
        await update.message.reply_text("ℹ️ Категория не указана")
        return
    
    await update.message.reply_text(f"📂 **Категория:** {game['category'].capitalize()}", parse_mode=ParseMode.MARKDOWN)

async def cmd_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает первую букву загаданного слова"""
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("ℹ️ Нет активной игры.")
        return
    
    game = games[chat_id]
    word = game.get('word', '')
    if not word:
        await update.message.reply_text("ℹ️ Слово не загадано")
        return
    
    # Показываем первую букву и количество букв
    first_letter = word[0].upper()
    word_len = len(word)
    hint = first_letter + "".join("_" for _ in range(word_len - 1))
    
    await update.message.reply_text(f"💡 **Подсказка:** {hint}\n📏 **Букв:** {word_len}", parse_mode=ParseMode.MARKDOWN)

# ─── Inline-обработчик (загадывание слова) ──────────────────────

async def on_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    text = query.query.strip()
    chat_id = query.chat_id
    
    log.info(f"Inline запрос: '{text}' от {query.from_user.id}")
    
    if not text:
        # Показываем справку со случайным словом
        word, category = get_random_word()
        await query.answer([
            InlineQueryResultArticle(
                id="help",
                title="🐊 Как играть",
                description="Напишите @бота слово для загадывания",
                input_message_content=InputTextMessageContent(
                    f"**Пример:** `@{context.bot.username} крокодил`\n\n"
                    f"**Случайное слово:** `{word}` (категория: {category})",
                    parse_mode=ParseMode.MARKDOWN,
                ),
            )
        ], cache_time=60)
        return
    
    # Если уже есть игра - отменяем старую
    if chat_id in games:
        # Не удаляем, а предупреждаем
        await query.answer([
            InlineQueryResultArticle(
                id="warning",
                title="⚠️ Игра уже идет!",
                description="Сначала завершите текущую игру",
                input_message_content=InputTextMessageContent(
                    "⚠️ В этом чате уже идет игра!\n"
                    "Дождитесь завершения или используйте /stop",
                    parse_mode=ParseMode.MARKDOWN,
                ),
            )
        ], cache_time=5)
        return
    
    # Проверяем, если пользователь ввел своё слово
    # Разбиваем на слова, берем первое как слово
    words = text.split()
    if words:
        guessed_word = words[0].lower()
    else:
        await query.answer([
            InlineQueryResultArticle(
                id="error",
                title="❌ Введите слово",
                description="Напишите слово для загадывания",
                input_message_content=InputTextMessageContent("❌ Введите слово для загадывания"),
            )
        ], cache_time=5)
        return
    
    # Проверяем слово на длину
    if len(guessed_word) < 2:
        await query.answer([
            InlineQueryResultArticle(
                id="short",
                title="❌ Слово слишком короткое",
                description="Минимум 2 буквы",
                input_message_content=InputTextMessageContent("❌ Слово должно быть минимум 2 буквы"),
            )
        ], cache_time=5)
        return
    
    # Создаем игру
    word_data = {
        'word': guessed_word,
        'guessed_by': None,
        'start_time': datetime.now(),
        'chat_id': chat_id,
        'from_user': query.from_user,
        'tries': 0,
        'category': None,  # можно определить категорию, если нужно
    }
    
    # Пытаемся определить категорию
    for cat, words_list in WORD_CATEGORIES.items():
        if guessed_word in words_list:
            word_data['category'] = cat
            break
    
    # Сохраняем игру
    games[chat_id] = word_data
    
    # Кнопки для управления игрой
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Подсказка", callback_data="crocodile:hint"),
         InlineKeyboardButton("📂 Категория", callback_data="crocodile:category")],
        [InlineKeyboardButton("❌ Завершить игру", callback_data="crocodile:stop")]
    ])
    
    # Создаем результат
    result_text = (
        f"🐊 **Игра Крокодил!**\n\n"
        f"Загадано слово: {len(guessed_word)} букв\n"
        f"Категория: {word_data['category'] or 'Не определена'}\n\n"
        f"Игроки, пишите свои варианты в чат!\n"
        f"Первый, кто угадает слово - победил! 🎉\n\n"
        f"📌 Слово загадал: {query.from_user.first_name}"
    )
    
    article = InlineQueryResultArticle(
        id="crocodile",
        title="🐊 Загадать слово",
        description=f"{guessed_word} ({len(guessed_word)} букв)",
        input_message_content=InputTextMessageContent(
            result_text,
            parse_mode=ParseMode.MARKDOWN,
        ),
        reply_markup=kb,
    )
    
    await query.answer([article], cache_time=5)
    log.info(f"Загадано слово: {guessed_word} в чате {chat_id}")

# ─── Обработчик сообщений (проверка ответов) ─────────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    
    if not message or not message.text:
        return
    
    text = message.text.strip().lower()
    user = message.from_user
    
    # Проверяем, есть ли игра
    if chat_id not in games:
        return
    
    game = games[chat_id]
    word = game.get('word', '').lower()
    
    # Игнорируем сообщения от бота
    if user.is_bot:
        return
    
    # Если пользователь уже угадал слово - игнорируем
    if game.get('guessed_by'):
        return
    
    # Проверяем, совпадает ли слово
    if text == word:
        # Правильно угадали!
        game['guessed_by'] = user.id
        
        # Время игры
        elapsed = datetime.now() - game['start_time']
        minutes = elapsed.seconds // 60
        seconds = elapsed.seconds % 60
        time_str = f"{minutes} мин {seconds} сек" if minutes > 0 else f"{seconds} сек"
        
        # Сообщение о победе
        win_text = (
            f"🎉 **ПОБЕДА!** 🎉\n\n"
            f"{user.first_name} угадал слово **{word.upper()}**!\n"
            f"⏱ Время: {time_str}\n"
            f"📊 Попыток: {game.get('tries', 0) + 1}\n\n"
            f"Загадал: {game['from_user'].first_name}"
        )
        
        await message.reply_text(win_text, parse_mode=ParseMode.MARKDOWN)
        
        # Удаляем игру
        del games[chat_id]
    else:
        # Не угадали, увеличиваем счетчик
        game['tries'] = game.get('tries', 0) + 1
        
        # Случайные реакции на неправильный ответ
        reactions = ["❌ Нет", "❌ Не угадал", "❌ Попробуй еще", "❌ Не то", "❌ Мимо", "❌ Почти!", "❌ Еще раз"]
        if game['tries'] % 3 == 0:
            # Подсказка
            await message.reply_text(f"💡 Подсказка: слово начинается на **{word[0].upper()}**")
        elif game['tries'] % 5 == 0:
            # Еще подсказка
            if len(word) <= 5:
                hint = word[:2] + "*" * (len(word) - 2)
                await message.reply_text(f"💡 Еще подсказка: **{hint}**")
            else:
                hint = word[:3] + "*" * (len(word) - 3)
                await message.reply_text(f"💡 Еще подсказка: **{hint}**")

# ─── Callback-обработчик ──────────────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    
    await query.answer()
    
    if data == "crocodile:hint":
        if chat_id not in games:
            await query.edit_message_text("ℹ️ Игра уже завершена")
            return
        
        game = games[chat_id]
        word = game.get('word', '')
        if not word:
            await query.edit_message_text("ℹ️ Слово не найдено")
            return
        
        # Показываем первую букву
        await query.edit_message_text(
            f"💡 **Подсказка:** первая буква **{word[0].upper()}**\n"
            f"Всего букв: {len(word)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к игре", callback_data="crocodile:back")]
            ])
        )
        
    elif data == "crocodile:category":
        if chat_id not in games:
            await query.edit_message_text("ℹ️ Игра уже завершена")
            return
        
        game = games[chat_id]
        category = game.get('category')
        if not category:
            await query.edit_message_text("ℹ️ Категория не определена")
            return
        
        await query.edit_message_text(
            f"📂 **Категория:** {category.capitalize()}\n\n"
            f"Слово относится к категории: **{category}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к игре", callback_data="crocodile:back")]
            ])
        )
        
    elif data == "crocodile:stop":
        if chat_id in games:
            del games[chat_id]
            await query.edit_message_text("❌ Игра остановлена")
        else:
            await query.edit_message_text("ℹ️ Нет активной игры")
            
    elif data == "crocodile:back":
        if chat_id not in games:
            await query.edit_message_text("ℹ️ Игра уже завершена")
            return
        
        game = games[chat_id]
        word = game.get('word', '')
        
        result_text = (
            f"🐊 **Игра Крокодил!**\n\n"
            f"Загадано слово: {len(word)} букв\n"
            f"Категория: {game.get('category') or 'Не определена'}\n\n"
            f"Игроки, пишите свои варианты в чат!\n"
            f"Первый, кто угадает слово - победил! 🎉"
        )
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Подсказка", callback_data="crocodile:hint"),
             InlineKeyboardButton("📂 Категория", callback_data="crocodile:category")],
            [InlineKeyboardButton("❌ Завершить игру", callback_data="crocodile:stop")]
        ])
        
        await query.edit_message_text(
            result_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb
        )

# ─── Команда /help ─────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐊 **Помощь по игре Крокодил**\n\n"
        "**Как играть:**\n"
        "1️⃣ Загадайте слово: `@ИмяБота слово`\n"
        "2️⃣ Игроки пишут свои варианты в чат\n"
        "3️⃣ Кто угадает - тот победил!\n\n"
        "**Команды:**\n"
        "/start - начать (показать правила)\n"
        "/stop - остановить текущую игру\n"
        "/word - показать категорию слова\n"
        "/hint - показать первую букву\n\n"
        "**Советы:**\n"
        "• Играйте с друзьями в группе\n"
        "• Используйте подсказки, если сложно\n"
        "• Загадывайте слова любой сложности",
        parse_mode=ParseMode.MARKDOWN
    )

# ─── Запуск ─────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("word", cmd_word))
    app.add_handler(CommandHandler("hint", cmd_hint))
    
    # Обработчики
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    
    log.info("🚀 Бот Крокодил запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
