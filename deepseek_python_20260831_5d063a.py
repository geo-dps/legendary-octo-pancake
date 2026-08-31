#!/usr/bin/env python3
"""
🎮 Verifure Game 10.1 — Crocodile Edition
Currency: VRF · Crocodile Game · Marriages · Bears · Admin Panel
Game: Crocodile (word guessing)
Deploy: Railway.app | Set BOT_TOKEN env var
Admin ID: 6254951831
"""

import asyncio
import io
import logging
import math
import os
import random
import threading
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Tuple, List, Dict, Set

import aiosqlite
from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReactionTypeEmoji,
    ReplyKeyboardMarkup,
    ReplyParameters,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DB_PATH: str = os.getenv("DB_PATH", "verifure.db")
WORDS_FILE: str = os.getenv("WORDS_FILE", "words.txt")

STARTING_VRF = 500
DAILY_BONUS_BASE = 100
DAILY_STREAK_BONUS = 10
DAILY_MARRIED_BONUS = 15
GIFT_COST = 75
GIFT_REWARD = 100
GIFT_MARRIED_REWARD = 150
GIFT_COOLDOWN_H = 1
LOVE_REWARD = 15
LOVE_MARRIED_REWARD = 35
LOVE_COOLDOWN_M = 30
MAX_BET = 500
MIN_BET = 10

REFERRAL_BONUS_INVITER = 200
REFERRAL_BONUS_NEW = 150

ADMIN_IDS: list[int] = [6254951831] + [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# ── Crocodile game config ─────────────────────────────
CROCODILE_ROUND_TIME = 60          # seconds to guess
CROCODILE_REWARD = 20              # VRF for guessing correctly
CROCODILE_PASS_COST = 5            # VRF cost to pass (optional)
CROCODILE_MAX_PASSES = 3           # max passes per round

# ══════════════════════════════════════════════════════
#  EMOJI
# ══════════════════════════════════════════════════════

E_ACCEPT = "✅"
E_DECLINE = "❌"
E_STARS = "⭐️"
E_WIN1 = "🏆"
E_WIN2 = "🥈"
E_RING = "💍"
E_LOVE = "❤️"
E_ALERT = "⚠️"
E_BEAR = "🐻"
E_WARN = "⚠️"
E_BOOM = "💥"
E_VRF = "💎"
E_WAIT = "⏳"
E_FIRST = "🥇"
E_SECOND = "🥈"
E_BONUS = "⭐"

# ══════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("verifure")

# ══════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════

async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER,
                chat_id      INTEGER,
                username     TEXT    DEFAULT '',
                first_name   TEXT    DEFAULT '',
                vrf          INTEGER DEFAULT 500,
                experience   INTEGER DEFAULT 0,
                level        INTEGER DEFAULT 1,
                wins         INTEGER DEFAULT 0,
                losses       INTEGER DEFAULT 0,
                draws        INTEGER DEFAULT 0,
                total_games  INTEGER DEFAULT 0,
                win_streak   INTEGER DEFAULT 0,
                max_streak   INTEGER DEFAULT 0,
                bears        INTEGER DEFAULT 0,
                last_xp      TEXT    DEFAULT NULL,
                last_daily   TEXT    DEFAULT NULL,
                daily_streak INTEGER DEFAULT 0,
                last_gift    TEXT    DEFAULT NULL,
                last_love    TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS marriages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id   INTEGER NOT NULL,
                user2_id   INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                married_at TEXT    NOT NULL,
                UNIQUE (user1_id, chat_id),
                UNIQUE (user2_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS proposals (
                proposer_id INTEGER NOT NULL,
                target_id   INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL,
                PRIMARY KEY (proposer_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT    DEFAULT '',
                first_name TEXT    DEFAULT '',
                added_by   INTEGER,
                added_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_activity (
                date     TEXT    NOT NULL,
                chat_id  INTEGER NOT NULL,
                messages INTEGER DEFAULT 0,
                games    INTEGER DEFAULT 0,
                PRIMARY KEY (date, chat_id)
            );

            CREATE TABLE IF NOT EXISTS mutes (
                user_id  INTEGER NOT NULL,
                chat_id  INTEGER NOT NULL,
                muted_by INTEGER NOT NULL,
                muted_at TEXT    NOT NULL,
                until    TEXT    DEFAULT NULL,
                reason   TEXT    DEFAULT '',
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS warns (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                warned_by INTEGER NOT NULL,
                warned_at TEXT    NOT NULL,
                reason    TEXT    DEFAULT '',
                active    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS referrals (
                user_id       INTEGER PRIMARY KEY,
                inviter_id    INTEGER NOT NULL,
                claimed_at    TEXT    NOT NULL,
                new_user_paid INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS achievements (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                key         TEXT    NOT NULL,
                unlocked_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id, key)
            );

            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id           INTEGER PRIMARY KEY,
                welcome_text      TEXT    DEFAULT NULL,
                welcome_enabled   INTEGER DEFAULT 1,
                antiflood_enabled INTEGER DEFAULT 1,
                rules_text        TEXT    DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS banned_words (
                chat_id INTEGER NOT NULL,
                word    TEXT    NOT NULL,
                PRIMARY KEY (chat_id, word)
            );

            CREATE TABLE IF NOT EXISTS clans (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       INTEGER NOT NULL,
                name          TEXT    NOT NULL,
                leader_id     INTEGER NOT NULL,
                treasury      REAL    DEFAULT 0,
                defense_level INTEGER DEFAULT 1,
                created_at    TEXT    NOT NULL,
                UNIQUE (chat_id, name)
            );

            CREATE TABLE IF NOT EXISTS clan_members (
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                clan_id   INTEGER NOT NULL,
                role      TEXT    DEFAULT 'member',
                joined_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS clan_applications (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                clan_id    INTEGER NOT NULL,
                applied_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS attack_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                attacker_id INTEGER NOT NULL,
                target_type TEXT    NOT NULL,
                target_id   INTEGER NOT NULL,
                success     INTEGER NOT NULL,
                amount      REAL    DEFAULT 0,
                ts          TEXT    NOT NULL
            );

            -- Crocodile statistics
            CREATE TABLE IF NOT EXISTS crocodile_stats (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                games_played INTEGER DEFAULT 0,
                words_guessed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            );
        """)
        await db.commit()
        # Migrations for users table
        for col_sql in (
            "ALTER TABLE users ADD COLUMN last_bio_bonus TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN referral_by    INTEGER DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_active     TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN last_attack     TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN last_farm       TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN attacks_won     INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN defenses_won    INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN transfers_sent  INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_wheel      TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN last_clicker_claim TEXT DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN clicker_claimed_today INTEGER DEFAULT 0",
        ):
            try:
                await db.execute(col_sql)
                await db.commit()
            except Exception:
                pass

    log.info("Database initialised at %s", DB_PATH)


async def db_ensure_user(uid: int, cid: int, username: str, first_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, chat_id, username, first_name, vrf)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                 username=excluded.username, first_name=excluded.first_name""",
            (uid, cid, username or "", first_name or "", STARTING_VRF),
        )
        await db.commit()


async def db_get_user(uid: int, cid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id=? AND chat_id=?", (uid, cid)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_add_vrf(uid: int, cid: int, amount: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vrf=vrf+? WHERE user_id=? AND chat_id=?",
            (amount, uid, cid),
        )
        await db.commit()
        async with db.execute(
            "SELECT vrf FROM users WHERE user_id=? AND chat_id=?", (uid, cid)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def db_deduct_vrf(uid: int, cid: int, amount: int) -> bool:
    u = await db_get_user(uid, cid)
    if not u or u["vrf"] < amount:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vrf=vrf-? WHERE user_id=? AND chat_id=?",
            (amount, uid, cid),
        )
        await db.commit()
    return True


async def db_add_xp(uid: int, cid: int, amount: int) -> Tuple[int, bool]:
    u = await db_get_user(uid, cid)
    if not u:
        return 1, False
    old_lvl = get_level(u["experience"])
    new_xp = u["experience"] + amount
    new_lvl = get_level(new_xp)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET experience=?, level=?, last_xp=? WHERE user_id=? AND chat_id=?",
            (new_xp, new_lvl, _now(), uid, cid),
        )
        await db.commit()
    return new_lvl, new_lvl > old_lvl


async def db_record_game(uid: int, cid: int, won: bool, draw: bool = False, streak_reset: bool = True) -> None:
    u = await db_get_user(uid, cid)
    if not u:
        return
    streak = u["win_streak"]
    max_s = u["max_streak"]
    if won:
        streak += 1
        max_s = max(max_s, streak)
    elif not draw and streak_reset:
        streak = 0

    async with aiosqlite.connect(DB_PATH) as db:
        if won:
            await db.execute(
                """UPDATE users SET wins=wins+1, total_games=total_games+1,
                   win_streak=?, max_streak=? WHERE user_id=? AND chat_id=?""",
                (streak, max_s, uid, cid),
            )
        elif draw:
            await db.execute(
                "UPDATE users SET draws=draws+1, total_games=total_games+1 WHERE user_id=? AND chat_id=?",
                (uid, cid),
            )
        else:
            await db.execute(
                """UPDATE users SET losses=losses+1, total_games=total_games+1,
                   win_streak=0 WHERE user_id=? AND chat_id=?""",
                (uid, cid),
            )
        await db.commit()

    if won and u["wins"] % 10 == 0:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET bears=bears+1 WHERE user_id=? AND chat_id=?",
                (uid, cid),
            )
            await db.commit()

    if won:
        await db_log_activity(cid, gms=1)


async def db_log_activity(cid: int, msgs: int = 0, gms: int = 0) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO daily_activity (date, chat_id, messages, games)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date, chat_id) DO UPDATE SET
                   messages = messages + excluded.messages,
                   games    = games    + excluded.games""",
            (today, cid, msgs, gms),
        )
        await db.commit()


async def db_get_activity(cid: int, days: int = 30) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT date, messages, games
               FROM daily_activity
               WHERE chat_id = ?
                 AND date >= date('now', ? || ' days')
               ORDER BY date""",
            (cid, f"-{days}"),
        ) as cur:
            return await cur.fetchall()


# ── Level / Rank ──────────────────────────────────────

def xp_for_level(n: int) -> int:
    return 0 if n <= 1 else 50 * n * (n - 1)


def get_level(xp: int) -> int:
    if xp <= 0:
        return 1
    n = int((1 + math.sqrt(1 + 4 * xp / 50)) / 2)
    while n < 100 and xp_for_level(n + 1) <= xp:
        n += 1
    return max(1, min(n, 100))


def get_rank(level: int) -> str:
    RANKS = [
        (1,  "🌱 Новичок"), (5,  "📖 Ученик"), (10, "⚡ Игрок"),
        (15, "🌟 Про"), (20, "💎 Знаток"), (25, "🔥 Ветеран"),
        (30, "👑 Авторитет"), (40, "🏆 Легенда"), (50, "🌙 Мастер"),
        (75, "🚀 Сенсей"), (100, "⚜️ Бог игры"),
    ]
    for lvl, name in RANKS:
        if level >= lvl:
            return name
    return RANKS[0][1]


# ── Crocodile stats ──────────────────────────────────

async def db_croc_stats(uid: int, cid: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT games_played, words_guessed FROM crocodile_stats WHERE user_id=? AND chat_id=?",
            (uid, cid),
        ) as cur:
            row = await cur.fetchone()
    if row:
        return dict(row)
    return {"games_played": 0, "words_guessed": 0}


async def db_croc_stats_update(uid: int, cid: int, games: int = 0, guessed: int = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO crocodile_stats (user_id, chat_id, games_played, words_guessed)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   games_played = games_played + ?,
                   words_guessed = words_guessed + ?""",
            (uid, cid, games, guessed, games, guessed),
        )
        await db.commit()


# ── Admin / etc ───────────────────────────────────────

async def db_add_admin(uid: int, username: str, first_name: str, added_by: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins(user_id,username,first_name,added_by,added_at) VALUES(?,?,?,?,?)",
            (uid, username or "", first_name or "", added_by, _now()),
        )
        await db.commit()


async def db_remove_admin(uid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM admins WHERE user_id=?", (uid,))
        await db.commit()
        return cur.rowcount > 0


async def db_list_admins() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admins ORDER BY added_at") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def is_bot_admin(uid: int) -> bool:
    if uid in ADMIN_IDS:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)) as cur:
            return bool(await cur.fetchone())


async def is_group_or_bot_admin(update: Update) -> bool:
    uid = update.effective_user.id
    if await is_bot_admin(uid):
        return True
    try:
        member = await update.effective_chat.get_member(uid)
        return member.status in ("administrator", "creator")
    except TelegramError:
        return False


# ── Marriage helpers ──────────────────────────────────

async def db_get_marriage(uid: int, cid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM marriages WHERE (user1_id=? OR user2_id=?) AND chat_id=?",
            (uid, uid, cid),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_get_proposal_to(target_id: int, cid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM proposals WHERE target_id=? AND chat_id=?", (target_id, cid)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_create_marriage(uid1: int, uid2: int, cid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO marriages (user1_id,user2_id,chat_id,married_at) VALUES(?,?,?,?)",
            (uid1, uid2, cid, _now()),
        )
        await db.execute(
            "DELETE FROM proposals WHERE chat_id=? AND (proposer_id IN(?,?) OR target_id IN(?,?))",
            (cid, uid1, uid2, uid1, uid2),
        )
        await db.commit()


async def db_delete_marriage(mid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM marriages WHERE id=?", (mid,))
        await db.commit()


async def db_all_marriages(cid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM marriages WHERE chat_id=? ORDER BY married_at DESC", (cid,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Referral ──────────────────────────────────────────

async def db_claim_referral(new_uid: int, inviter_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO referrals (user_id, inviter_id, claimed_at) VALUES (?,?,?)",
                (new_uid, inviter_id, _now()),
            )
            await db.commit()
            return True
        except Exception:
            return False


# ── Clan ──────────────────────────────────────────────

CLAN_CREATE_COST = 1000
CLAN_NAME_MIN, CLAN_NAME_MAX = 3, 24
CLAN_ROLES = {
    "raider": {"emoji": "⚔️", "label": "Налётчик", "desc": "+15% к шансу атак"},
    "defender": {"emoji": "🛡", "label": "Страж", "desc": "Усиливает защиту казны"},
    "treasurer": {"emoji": "💰", "label": "Казначей", "desc": "Может выводить VRF"},
    "member": {"emoji": "👤", "label": "Житель", "desc": "Без особых бонусов"},
}
CLAN_MAX_MEMBERS = 30
CLAN_RAID_COOLDOWN_MIN = 90
CLAN_RAID_BASE_CHANCE = 0.40
CLAN_RAID_STEAL_PCT = 0.12
CLAN_RAID_MIN_TREASURY = 200
CLAN_DEFENSE_BASE_COST = 500
CLAN_MAX_DEFENSE_LVL = 10

async def db_create_clan(cid: int, name: str, leader_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO clans (chat_id, name, leader_id, treasury, defense_level, created_at) "
                "VALUES (?,?,?,0,1,?)",
                (cid, name, leader_id, _now()),
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, chat_id, clan_id, role, joined_at) VALUES (?,?,?,?,?)",
                (leader_id, cid, cur.lastrowid, "leader", _now()),
            )
            await db.commit()
            return cur.lastrowid
        except Exception:
            return None


async def db_get_clan(clan_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM clans WHERE id=?", (clan_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_get_user_clan(uid: int, cid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.*, m.role AS my_role, lu.first_name AS leader_name FROM clan_members m
               JOIN clans c ON c.id = m.clan_id
               LEFT JOIN users lu ON lu.user_id = c.leader_id AND lu.chat_id = c.chat_id
               WHERE m.user_id=? AND m.chat_id=?""",
            (uid, cid),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def db_list_clans(cid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.*, COUNT(m.user_id) AS member_count FROM clans c
               LEFT JOIN clan_members m ON m.clan_id = c.id
               WHERE c.chat_id=? GROUP BY c.id ORDER BY c.treasury DESC""",
            (cid,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_clan_members(clan_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT m.*, u.first_name, u.username, u.vrf FROM clan_members m
               JOIN users u ON u.user_id = m.user_id AND u.chat_id = m.chat_id
               WHERE m.clan_id=? ORDER BY
                 CASE m.role WHEN 'leader' THEN 0 ELSE 1 END, m.joined_at""",
            (clan_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_add_clan_member(uid: int, cid: int, clan_id: int, role: str = "member") -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO clan_members (user_id, chat_id, clan_id, role, joined_at) "
            "VALUES (?,?,?,?,?)",
            (uid, cid, clan_id, role, _now()),
        )
        await db.commit()


async def db_remove_clan_member(uid: int, cid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM clan_members WHERE user_id=? AND chat_id=?", (uid, cid))
        await db.commit()


async def db_apply_to_clan(uid: int, cid: int, clan_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO clan_applications (user_id, chat_id, clan_id, applied_at) VALUES (?,?,?,?)",
                (uid, cid, clan_id, _now()),
            )
            await db.commit()
            return True
        except Exception:
            return False


async def db_get_clan_applications(clan_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT a.*, u.first_name, u.username FROM clan_applications a
               JOIN users u ON u.user_id=a.user_id AND u.chat_id=a.chat_id
               WHERE a.clan_id=? ORDER BY a.applied_at""",
            (clan_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_remove_application(uid: int, cid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM clan_applications WHERE user_id=? AND chat_id=?", (uid, cid))
        await db.commit()


# ── Helpers ──────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat()


def mention(uid: int, name: str) -> str:
    safe = str(name).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={uid}">{safe}</a>'


def fmt(n) -> str:
    n = int(round(n))
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}".replace(",", " ")


def fmt_cd(seconds: int) -> str:
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def days_ago(dt_str: str) -> int:
    return (datetime.now() - datetime.fromisoformat(dt_str)).days


def partner_id(m: dict, uid: int) -> int:
    return m["user2_id"] if m["user1_id"] == uid else m["user1_id"]


# ── Rich message helpers ─────────────────────────────

async def send_rich(
    bot,
    chat_id: int,
    markdown: str = "",
    fallback_html: str = "",
    reply_to_id: int = None,
    reply_markup=None,
    html: str = "",
    blocks: list = None,
    media: list = None,
) -> bool:
    fb_text = fallback_html or html or markdown
    rich_msg = {}
    if blocks:
        rich_msg["blocks"] = blocks
    elif html:
        rich_msg["html"] = html
    else:
        rich_msg["markdown"] = markdown or " "
    if media:
        rich_msg["media"] = media

    kw = {"chat_id": chat_id, "rich_message": rich_msg}
    if reply_to_id:
        kw["reply_parameters"] = {"message_id": reply_to_id}
    if reply_markup:
        try:
            kw["reply_markup"] = reply_markup.to_dict()
        except Exception:
            pass
    try:
        await bot.do_api_request("sendRichMessage", api_kwargs=kw)
        return True
    except Exception:
        pass

    msg_kw = {"chat_id": chat_id, "text": fb_text, "parse_mode": ParseMode.HTML}
    if reply_to_id:
        msg_kw["reply_parameters"] = {"message_id": reply_to_id}
    if reply_markup:
        msg_kw["reply_markup"] = reply_markup
    try:
        await bot.send_message(**msg_kw)
        return False
    except Exception:
        pass

    import re as _re
    plain = _re.sub(r"<[^>]+>", "", fb_text)[:4096].strip()
    if plain:
        try:
            p_kw = {"chat_id": chat_id, "text": plain}
            if reply_markup:
                p_kw["reply_markup"] = reply_markup
            await bot.send_message(**p_kw)
        except Exception:
            pass
    return False


# ── Ephemeral messages ───────────────────────────────

async def is_bot_chat_admin(bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def send_ephemeral(
    bot, chat_id: int, receiver_user_id: int, text: str,
    reply_markup=None, reply_to_id: int = None, parse_mode=ParseMode.HTML,
    callback_query_id: str = None, ephemeral_reply_message_id: int = None,
    bot_is_admin: bool = None,
) -> Optional[dict]:
    if bot_is_admin is None and not callback_query_id and not ephemeral_reply_message_id:
        bot_is_admin = await is_bot_chat_admin(bot, chat_id)

    if not (callback_query_id or ephemeral_reply_message_id or bot_is_admin):
        return None

    kw = {
        "chat_id": chat_id, "text": text,
        "receiver_user_id": receiver_user_id, "parse_mode": parse_mode,
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
        return None
    except Exception:
        return None


async def send_ephemeral_or_normal(
    bot, chat_id: int, receiver_user_id: int, text: str,
    reply_markup=None, reply_to_id: int = None, parse_mode=ParseMode.HTML,
    callback_query_id: str = None, ephemeral_reply_message_id: int = None,
    bot_is_admin: bool = None,
):
    result = await send_ephemeral(
        bot, chat_id, receiver_user_id, text,
        reply_markup=reply_markup, reply_to_id=reply_to_id, parse_mode=parse_mode,
        callback_query_id=callback_query_id,
        ephemeral_reply_message_id=ephemeral_reply_message_id,
        bot_is_admin=bot_is_admin,
    )
    if result is not None:
        return result
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode,
            reply_markup=reply_markup,
            reply_parameters={"message_id": reply_to_id} if reply_to_id else None,
        )
    except Exception:
        return None


# ── Only groups decorator ────────────────────────────

def only_groups(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("❌ Эта команда работает только в групповых чатах.")
            return
        return await func(update, context)
    return wrapper


# ── Activity image generation ────────────────────────

def _activity_chart_sync(rows: list) -> Optional[bytes]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from datetime import datetime as _dt, timedelta as _td
    except ImportError:
        return None

    if not rows:
        return None

    all_dates = {}
    if rows:
        start = _dt.strptime(rows[0][0], "%Y-%m-%d")
        end = _dt.strptime(rows[-1][0], "%Y-%m-%d")
        cur = start
        while cur <= end:
            all_dates[cur.strftime("%Y-%m-%d")] = [0, 0]
            cur += _td(days=1)
    for date_s, msg, gm in rows:
        all_dates[date_s] = [int(msg), int(gm)]

    sorted_dates = sorted(all_dates)
    messages = [all_dates[d][0] for d in sorted_dates]
    games = [all_dates[d][1] for d in sorted_dates]
    labels = [d[8:10] + "." + d[5:7] for d in sorted_dates]
    n = len(sorted_dates)
    x = np.arange(n)
    bar_w = 0.40

    fig, ax = plt.subplots(figsize=(13, 5.5))
    fig.patch.set_facecolor("#f4f4f4")
    ax.set_facecolor("#f4f4f4")

    ax.bar(x - bar_w / 2, messages, bar_w, color="#b5e61d", zorder=3, label="Сообщения")
    ax.bar(x + bar_w / 2, games, bar_w, color="#f07030", zorder=3, label="Игры")

    step = max(1, n // 15)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(labels[::step], fontsize=9, color="#444444")
    ax.tick_params(axis="x", bottom=False, top=False)
    ax.set_xlim(-0.7, n - 0.3)

    ax.tick_params(axis="y", labelsize=9, labelcolor="#444444", left=True, right=False)
    ax.set_ylim(bottom=0)

    ax2 = ax.twinx()
    ax2.set_ylim(ax.get_ylim())
    yticks = ax.get_yticks()
    ax2.set_yticks(yticks)
    ax2.set_yticklabels(
        [str(int(t)) if t >= 0 and t == int(t) else "" for t in yticks],
        fontsize=9, color="#3344cc",
    )
    ax2.set_ylabel("Сообщения", fontsize=9, color="#3344cc", rotation=90, labelpad=8)
    ax2.tick_params(axis="y", colors="#3344cc", right=True, width=0.5)
    ax2.spines["right"].set_color("#3344cc")
    ax2.spines["right"].set_linewidth(0.8)

    ax.yaxis.grid(True, color="#cccccc", linestyle="-", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)

    for sp in ("top", "right", "left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)

    ax.set_title("Статистика активности", fontsize=13, color="#333333", pad=10)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.7, frameon=True)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=130, bbox_inches="tight", facecolor="#f4f4f4", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════
#  CROCODILE GAME 🐊
# ══════════════════════════════════════════════════════

# In-memory games: chat_id -> game data
crocodile_games: Dict[int, dict] = {}
# Word list loaded from file
crocodile_words: List[str] = []


def load_words() -> List[str]:
    """Load words from WORDS_FILE or use a default list."""
    try:
        if os.path.exists(WORDS_FILE):
            with open(WORDS_FILE, "r", encoding="utf-8") as f:
                words = [w.strip().lower() for w in f.readlines() if w.strip()]
            if words:
                log.info("Loaded %d words from %s", len(words), WORDS_FILE)
                return words
    except Exception as e:
        log.warning("Failed to load words: %s", e)

    # Default small dictionary
    default_words = [
        "апельсин", "банан", "вишня", "груша", "дыня",
        "ежевика", "жираф", "заяц", "индюк", "кот",
        "леопард", "медведь", "носорог", "обезьяна", "панда",
        "тигр", "улитка", "фламинго", "хищник", "цапля",
        "часы", "шляпа", "щенок", "эскимо", "юла",
        "яблоко", "автомобиль", "билет", "велосипед", "газета",
        "дерево", "еда", "журнал", "зонт", "игрушка",
        "йогурт", "компьютер", "лампа", "мебель", "носок",
        "одеяло", "печенье", "река", "солнце", "телефон",
        "учебник", "фонарь", "хлеб", "цветок", "шоколад"
    ]
    log.info("Using default word list (%d words)", len(default_words))
    return default_words


def get_random_word() -> str:
    if not crocodile_words:
        return "крокодил"
    return random.choice(crocodile_words)


def _croc_kb(chat_id: int, show_pass: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if show_pass:
        buttons.append(InlineKeyboardButton("Пропустить (5 VRF)", callback_data=f"croc_pass:{chat_id}"))
    buttons.append(InlineKeyboardButton("Завершить", callback_data=f"croc_end:{chat_id}"))
    return InlineKeyboardMarkup([buttons])


@only_groups
async def cmd_crocodile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a crocodile game in the group."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    await db_ensure_user(user.id, chat_id, user.username or "", user.first_name)

    if chat_id in crocodile_games:
        await update.message.reply_text("🐊 В этом чате уже идёт игра! Дождись окончания.")
        return

    word = get_random_word()

    # Pick a player to show the word (the one who started)
    show_user = user

    # Try to DM the word to the show user
    try:
        await context.bot.send_message(
            chat_id=show_user.id,
            text=f"🐊 <b>Ты показываешь!</b>\n\nСлово: <code>{word.upper()}</code>\n"
                 f"Объясняй его в группе, не называя само слово!",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        await update.message.reply_text(
            f"❌ {mention(show_user.id, show_user.first_name)}, я не могу написать тебе в ЛС. "
            f"Напиши мне /start в личку и попробуй снова.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Store game
    crocodile_games[chat_id] = {
        "word": word,
        "show_user_id": show_user.id,
        "start_time": datetime.now(),
        "end_time": datetime.now() + timedelta(seconds=CROCODILE_ROUND_TIME),
        "guessed": False,
        "passes": 0,
        "max_passes": CROCODILE_MAX_PASSES,
        "active": True,
    }

    # Announce in group
    msg = await update.message.reply_text(
        f"🐊 <b>Игра КРОКОДИЛ началась!</b>\n\n"
        f"👤 Показывает: {mention(show_user.id, show_user.first_name)}\n"
        f"⏱ У вас {CROCODILE_ROUND_TIME} секунд, чтобы угадать слово!\n"
        f"📝 Пишите свои варианты в чат.\n"
        f"💎 За правильный ответ: <b>{CROCODILE_REWARD} VRF</b>\n\n"
        f"Удачи! 🎯",
        parse_mode=ParseMode.HTML,
        reply_markup=_croc_kb(chat_id, show_pass=True),
    )

    # Start timeout task
    context.application.create_task(_croc_timeout(context.bot, chat_id, msg.message_id))


async def _croc_timeout(bot, chat_id: int, msg_id: int) -> None:
    """Auto-end game after timeout."""
    await asyncio.sleep(CROCODILE_ROUND_TIME)
    game = crocodile_games.get(chat_id)
    if not game or not game["active"] or game["guessed"]:
        return

    # Time's up
    game["active"] = False
    word = game["word"]
    del crocodile_games[chat_id]

    try:
        await bot.edit_message_text(
            f"⏰ <b>Время вышло!</b>\n\n"
            f"Загаданное слово: <code>{word.upper()}</code>\n"
            f"Никто не угадал 😢",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        await bot.send_message(
            chat_id,
            f"⏰ <b>Время вышло!</b>\nЗагаданное слово: <code>{word.upper()}</code>",
            parse_mode=ParseMode.HTML,
        )


@only_groups
async def cmd_croc_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pass the current word (only for the show user)."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    game = crocodile_games.get(chat_id)

    if not game or not game["active"]:
        await update.message.reply_text("❌ В этом чате нет активной игры.")
        return

    if user.id != game["show_user_id"]:
        await update.message.reply_text("❌ Только показывающий может пропустить слово!")
        return

    if game["passes"] >= game["max_passes"]:
        await update.message.reply_text(f"❌ Достигнут лимит пропусков ({game['max_passes']}).")
        return

    # Deduct cost
    if not await db_deduct_vrf(user.id, chat_id, CROCODILE_PASS_COST):
        await update.message.reply_text(f"❌ Недостаточно VRF! Нужно {CROCODILE_PASS_COST} VRF для пропуска.")
        return

    # Get new word
    new_word = get_random_word()
    game["word"] = new_word
    game["passes"] += 1
    game["end_time"] = datetime.now() + timedelta(seconds=CROCODILE_ROUND_TIME)

    # Notify show user in DM
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"🔄 <b>Пропуск!</b>\n\nНовое слово: <code>{new_word.upper()}</code>\n"
                 f"Осталось пропусков: {game['max_passes'] - game['passes']}",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass

    await update.message.reply_text(
        f"🔄 <b>Пропуск!</b> Загадано новое слово.\n"
        f"⏱ У вас осталось {CROCODILE_ROUND_TIME} секунд.",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_croc_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force end the game (admin or show user)."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    game = crocodile_games.get(chat_id)

    if not game or not game["active"]:
        await update.message.reply_text("❌ В этом чате нет активной игры.")
        return

    if user.id != game["show_user_id"] and not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Только показывающий или админ может завершить игру.")
        return

    game["active"] = False
    word = game["word"]
    del crocodile_games[chat_id]

    await update.message.reply_text(
        f"🏁 <b>Игра завершена досрочно.</b>\nЗагаданное слово: <code>{word.upper()}</code>",
        parse_mode=ParseMode.HTML,
    )


async def _handle_croc_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process messages in groups to check for correct guesses."""
    if not update.message or not update.effective_user:
        return
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip().lower()

    if not text or chat_id not in crocodile_games:
        return

    game = crocodile_games[chat_id]
    if not game["active"] or game["guessed"]:
        return

    # Ignore messages from the show user (they know the word)
    if user.id == game["show_user_id"]:
        return

    # Check if the guess matches the word (exact match, case-insensitive)
    if text == game["word"]:
        # Correct guess!
        game["guessed"] = True
        game["active"] = False

        # Reward the guesser
        await db_add_vrf(user.id, chat_id, CROCODILE_REWARD)
        await db_add_xp(user.id, chat_id, 20)
        await db_record_game(user.id, chat_id, won=True)
        await db_croc_stats_update(user.id, chat_id, games=0, guessed=1)
        await db_croc_stats_update(game["show_user_id"], chat_id, games=1, guessed=0)

        # Remove game
        del crocodile_games[chat_id]

        # Announce
        show_user = await context.bot.get_chat(game["show_user_id"])
        show_name = show_user.first_name if show_user else "Показывающий"

        await update.message.reply_text(
            f"🎉 <b>ПРАВИЛЬНО!</b> 🎉\n\n"
            f"@{user.username or user.first_name} угадал(а) слово <code>{game['word'].upper()}</code>!\n"
            f"💎 +{CROCODILE_REWARD} VRF\n\n"
            f"👏 Отличная работа!",
            parse_mode=ParseMode.HTML,
        )

        # React to the guess message
        try:
            await update.message.react([ReactionTypeEmoji(emoji="🎉")])
        except TelegramError:
            pass

        return


# ══════════════════════════════════════════════════════
#  BASE COMMANDS
# ══════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id

    if update.effective_chat.type == "private":
        # Handle referral
        if context.args:
            arg = context.args[0]
            if arg.startswith("ref_"):
                inviter_id = None
                try:
                    inviter_id = int(arg[4:])
                except ValueError:
                    pass
                if inviter_id and inviter_id != u.id:
                    claimed = await db_claim_referral(u.id, inviter_id)
                    if claimed:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE users SET vrf=vrf+?, referral_count=referral_count+1 "
                                "WHERE user_id=?",
                                (REFERRAL_BONUS_INVITER, inviter_id),
                            )
                            await db.commit()
                            async with db.execute(
                                "SELECT COUNT(*) FROM users WHERE user_id=?", (u.id,)
                            ) as cur:
                                has_rows = (await cur.fetchone())[0] > 0

                        new_user_msg = (
                            f"🎉 <b>Реферальный бонус!</b>\n\n"
                            f"Ты зарегистрировался по ссылке от друга!\n"
                        )
                        if has_rows:
                            async with aiosqlite.connect(DB_PATH) as db:
                                await db.execute(
                                    "UPDATE users SET vrf=vrf+? WHERE user_id=?",
                                    (REFERRAL_BONUS_NEW, u.id),
                                )
                                await db.execute(
                                    "UPDATE referrals SET new_user_paid=1 WHERE user_id=?",
                                    (u.id,),
                                )
                                await db.commit()
                            new_user_msg += f"💎 +{fmt(REFERRAL_BONUS_NEW)} VRF тебе на счёт!"
                        else:
                            new_user_msg += (
                                f"💎 +{fmt(REFERRAL_BONUS_NEW)} VRF зачислятся, как только "
                                f"напишешь что-нибудь в группе с ботом!"
                            )

                        try:
                            await context.bot.send_message(
                                inviter_id,
                                f"🎉 <b>Реферальный бонус!</b>\n\n"
                                f"👤 {u.first_name} зарегистрировался по твоей ссылке!\n"
                                f"💎 +{fmt(REFERRAL_BONUS_INVITER)} VRF",
                                parse_mode=ParseMode.HTML,
                            )
                        except TelegramError:
                            pass
                        await update.message.reply_text(new_user_msg, parse_mode=ParseMode.HTML)

        await update.message.reply_text(
            f"👋 <b>Привет! Я Verifure Game</b>\n\n"
            f"💎 Стартовый баланс: <b>{STARTING_VRF} VRF</b>\n\n"
            f"🐊 Игра Крокодил: /crocodile\n"
            f"💒 Браки: /marry\n"
            f"🎁 Подарки: /gift\n"
            f"📊 Профиль: /profile\n"
            f"📖 Помощь: /help\n\n"
            f"📌 Добавь меня в группу и начни игру!",
            parse_mode=ParseMode.HTML,
        )
        return

    await db_ensure_user(u.id, cid, u.username or "", u.first_name)
    uu = await db_get_user(u.id, cid)
    bal = uu["vrf"] if uu else STARTING_VRF

    await update.message.reply_text(
        f"👋 Привет, {mention(u.id, u.first_name)}!\n\n"
        f"💎 Баланс: <b>{fmt(bal)} VRF</b>\n\n"
        f"🐊 /crocodile — начать игру Крокодил\n"
        f"📊 /profile — мой профиль\n"
        f"📖 /help — все команды",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cid = update.effective_chat.id
    help_text = (
        "📖 <b>Verifure Game — Помощь</b>\n\n"
        "<b>👤 Профиль и экономика</b>\n"
        "/profile — мой профиль\n"
        "/top — топ игроков\n"
        "/stats — статистика чата\n"
        "/daily — ежедневный бонус\n"
        "/bonus — статус бонусов\n"
        "/ref — реферальная ссылка\n"
        "/achievements — достижения\n"
        "/wheel — колесо фортуны\n\n"

        "<b>🐊 Игры</b>\n"
        "/crocodile — начать игру Крокодил\n\n"

        "<b>💒 Браки</b>\n"
        "/marry — предложение\n"
        "/accept — принять предложение\n"
        "/reject — отклонить\n"
        "/divorce — развод\n"
        "/marriage — карточка брака\n"
        "/marriages — все пары чата\n\n"

        "<b>🎁 Активности</b>\n"
        "/gift — подарить VRF (ответом)\n"
        "/love — любовь (ответом)\n\n"

        "<b>🏰 Кланы</b>\n"
        "/clan — управление кланом\n\n"

        "<b>🛡️ Администрирование</b>\n"
        "/admin — панель администратора\n"
        "/givevrf — выдать VRF\n"
        "/takevrf — забрать VRF\n"
        "/addadmin — добавить бот-админа\n"
        "/removeadmin — удалить бот-админа\n"
        "/listadmins — список админов\n\n"

        "<b>🛡️ Модерация</b>\n"
        "/mute, /unmute, /kick, /ban, /unban, /warn, /unwarn, /clearwarns, /warnlist, /mutelist\n\n"

        f"💎 Старт: <b>{STARTING_VRF} VRF</b> · Бонус: <b>{DAILY_BONUS_BASE} VRF/день</b>"
    )
    await send_rich(context.bot, cid, html=help_text, fallback_html=help_text,
                    reply_to_id=update.message.message_id)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.reply_to_message and not update.message.reply_to_message.from_user.is_bot:
        target = update.message.reply_to_message.from_user
    else:
        target = update.effective_user

    cid = update.effective_chat.id
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)
    u = await db_get_user(target.id, cid)
    if not u:
        return

    lvl = get_level(u["experience"])
    rank_nm = get_rank(lvl)
    pos = await db_rank_pos(target.id, cid)
    wr = round(u["wins"] / max(1, u["total_games"]) * 100, 1)

    m = await db_get_marriage(target.id, cid)
    if m:
        pid = partner_id(m, target.id)
        pu = await db_get_user(pid, cid)
        pname = pu["first_name"] if pu else "Партнёр"
        d = days_ago(m["married_at"])
        m_line = f"💍 {mention(pid, pname)} · {d} дн."
    else:
        m_line = "💔 Свободен(а)"

    croc_stats = await db_croc_stats(target.id, cid)

    text = (
        f"👤 <b>{target.first_name}</b>\n\n"
        f"🏅 Ур. <b>{lvl}</b> — {rank_nm}\n"
        f"💎 VRF: <b>{fmt(u['vrf'])}</b>  🏆 #{pos}\n\n"
        f"🎮 Игр: <b>{u['total_games']}</b>  ✅ <b>{u['wins']}</b> ({wr}%)  ❌ <b>{u['losses']}</b>\n"
        f"🔥 Серия: <b>{u['win_streak']}</b> (макс. {u['max_streak']})  🐻 <b>{u['bears']}</b>\n\n"
        f"🐊 <b>Крокодил:</b> игр: {croc_stats['games_played']}, угадано: {croc_stats['words_guessed']}\n\n"
        f"{m_line}"
    )
    result = await send_ephemeral_or_normal(
        context.bot, cid, update.effective_user.id, text,
        reply_to_id=update.message.message_id,
    )
    if isinstance(result, dict) and result.get("ephemeral_message_id"):
        try:
            await update.message.react([ReactionTypeEmoji(emoji="👀")])
        except TelegramError:
            pass


async def db_rank_pos(uid: int, cid: int, col: str = "vrf") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT COUNT(*)+1 FROM users "
            f"WHERE chat_id=? AND {col}>(SELECT {col} FROM users WHERE user_id=? AND chat_id=?)",
            (cid, uid, cid),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 1


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cid = update.effective_chat.id
    await _show_top(update, context, cid, "vrf")


async def _show_top(update_or_query, context, cid: int, sort: str, edit: bool = False) -> None:
    users = await db_top(cid, sort, 10)
    titles = {"vrf": "💎 VRF", "level": "⭐ Уровень", "wins": "🏆 Победы"}
    title = titles.get(sort, "VRF")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💎 VRF", callback_data=f"top:vrf:{cid}"),
        InlineKeyboardButton("⭐ Уровень", callback_data=f"top:level:{cid}"),
        InlineKeyboardButton("🏆 Победы", callback_data=f"top:wins:{cid}"),
    ]])

    col_hdr = {"vrf": "VRF", "level": "Уровень / XP", "wins": "Побед"}.get(sort, "VRF")

    fb_rows = [f"🏆 <b>Топ-10 — {title}</b>\n"]
    for i, u in enumerate(users):
        lvl = get_level(u["experience"])
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        name = u["first_name"]
        uid = u["user_id"]
        if sort == "wins":
            val = f"{u['wins']} побед"
        elif sort == "level":
            val = f"Ур.{lvl}"
        else:
            val = f"{fmt(u['vrf'])} VRF"
        fb_rows.append(f"{medal} {mention(uid, name)} — {val}")

    if edit:
        await update_or_query.edit_message_text("\n".join(fb_rows), parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await send_rich(context.bot, cid, fallback_html="\n".join(fb_rows),
                        reply_to_id=update_or_query.message.message_id, reply_markup=kb)


async def db_top(cid: int, sort: str = "vrf", limit: int = 10) -> list:
    col = {"vrf": "vrf", "level": "experience", "wins": "wins"}.get(sort, "vrf")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT * FROM users WHERE chat_id=? ORDER BY {col} DESC LIMIT ?",
            (cid, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cid = update.effective_chat.id
    total = await db_count_users(cid)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM marriages WHERE chat_id=?", (cid,)) as cur:
            marriages = (await cur.fetchone())[0]
        async with db.execute("SELECT SUM(total_games) FROM users WHERE chat_id=?", (cid,)) as cur:
            total_games = (await cur.fetchone())[0] or 0
        async with db.execute("SELECT SUM(vrf) FROM users WHERE chat_id=?", (cid,)) as cur:
            total_vrf = (await cur.fetchone())[0] or 0

    chat_title = update.effective_chat.title or "Чат"
    text = (
        f"📊 <b>Статистика чата — {chat_title}</b>\n\n"
        f"👥 Игроков: <b>{total}</b>\n"
        f"🎮 Сыграно: <b>{fmt(total_games)}</b>\n"
        f"💎 VRF в обороте: <b>{fmt(total_vrf)}</b>\n"
        f"💒 Браков: <b>{marriages}</b>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def db_count_users(cid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE chat_id=?", (cid,)) as cur:
            return (await cur.fetchone())[0]


@only_groups
async def cmd_statsimg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cid = update.effective_chat.id
    days = 30
    if context.args:
        try:
            days = min(90, max(7, int(context.args[0])))
        except ValueError:
            pass

    rows = await db_get_activity(cid, days)
    if not rows:
        await update.message.reply_text(
            "📊 <b>Данных пока нет</b>\n\nАктивность начнёт отслеживаться с этого момента.",
            parse_mode=ParseMode.HTML,
        )
        return

    loop = asyncio.get_running_loop()
    img_bytes = await loop.run_in_executor(None, _activity_chart_sync, list(rows))

    if img_bytes is None:
        await update.message.reply_text(
            "❌ Установи matplotlib:\n<code>pip install matplotlib</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    total_msgs = sum(r[1] for r in rows)
    total_games = sum(r[2] for r in rows)
    await context.bot.send_photo(
        chat_id=cid,
        photo=io.BytesIO(img_bytes),
        caption=(
            f"📈 <b>Активность чата — последние {days} дн.</b>\n\n"
            f"💬 Сообщений: <b>{fmt(total_msgs)}</b>\n"
            f"🎮 Игр сыграно: <b>{fmt(total_games)}</b>"
        ),
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_statsimg(update, context)


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u_obj = update.effective_user
    cid = update.effective_chat.id
    await db_ensure_user(u_obj.id, cid, u_obj.username or "", u_obj.first_name)
    u = await db_get_user(u_obj.id, cid)
    now = datetime.now()
    cd = 20 * 3600

    if u["last_daily"]:
        elapsed = (now - datetime.fromisoformat(u["last_daily"])).total_seconds()
        if elapsed < cd:
            rem = int(cd - elapsed)
            await update.message.reply_text(
                f"⏰ Следующий бонус через <b>{fmt_cd(rem)}</b>",
                parse_mode=ParseMode.HTML,
            )
            return

    streak = u.get("daily_streak") or 0
    last_streak = u.get("last_daily")
    if last_streak:
        diff = (now.date() - datetime.fromisoformat(last_streak).date()).days
        streak = streak + 1 if diff == 1 else 1
    else:
        streak = 1

    streak_bonus = min(streak - 1, 6) * DAILY_STREAK_BONUS
    m = await db_get_marriage(u_obj.id, cid)
    marry_bonus = DAILY_MARRIED_BONUS if m else 0
    total = DAILY_BONUS_BASE + streak_bonus + marry_bonus

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_daily=?, daily_streak=? WHERE user_id=? AND chat_id=?",
            (_now(), streak, u_obj.id, cid),
        )
        await db.commit()

    new_bal = await db_add_vrf(u_obj.id, cid, total)
    new_lvl, leveled_up = await db_add_xp(u_obj.id, cid, XP_PER_GAME)

    text = f"⚡ <b>Ежедневный бонус!</b>\n\n├ База: +{DAILY_BONUS_BASE} VRF"
    if streak_bonus:
        text += f"\n├ 🔥 Стрик {streak} дн.: +{streak_bonus} VRF"
    if marry_bonus:
        text += f"\n├ 💍 Бонус брака: +{marry_bonus} VRF"
    text += f"\n└ Итого: <b>+{total} VRF</b>\n\n💎 Баланс: <b>{fmt(new_bal)} VRF</b>"
    if leveled_up:
        text += f"\n🎉 Новый уровень: <b>{new_lvl}!</b> {get_rank(new_lvl)}"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u_obj = update.effective_user
    cid = update.effective_chat.id
    await db_ensure_user(u_obj.id, cid, u_obj.username or "", u_obj.first_name)
    u = await db_get_user(u_obj.id, cid)

    daily_txt = "✅ Доступен"
    if u["last_daily"]:
        elapsed = (datetime.now() - datetime.fromisoformat(u["last_daily"])).total_seconds()
        rem = int(20 * 3600 - elapsed)
        if rem > 0:
            daily_txt = f"⏰ {fmt_cd(rem)}"

    def cd_txt(last_field: str, secs: int) -> str:
        last = u.get(last_field)
        if not last:
            return "✅ Доступен"
        rem = int(secs - (datetime.now() - datetime.fromisoformat(last)).total_seconds())
        return f"⏰ {fmt_cd(rem)}" if rem > 0 else "✅ Доступен"

    bio_bonus_txt = cd_txt("last_bio_bonus", 20 * 3600)
    m = await db_get_marriage(u_obj.id, cid)

    text = (
        f"🎁 <b>Бонусы: {mention(u_obj.id, u_obj.first_name)}</b>\n\n"
        f"💎 VRF: <b>{fmt(u['vrf'])}</b>\n\n"
        f"📅 Ежедневный: {daily_txt}\n"
        f"🎁 Промо @VerifureGift: {bio_bonus_txt}\n"
        f"🔥 Стрик: {u.get('daily_streak', 0)} дн.\n"
        f"💑 Брак: {'✅ +15 VRF к бонусу' if m else '❌ Нет'}\n"
        f"🎀 Подарок /gift: {cd_txt('last_gift', GIFT_COOLDOWN_H * 3600)}\n"
        f"💕 Любовь /love: {cd_txt('last_love', LOVE_COOLDOWN_M * 60)}\n\n"
        f"🐻 Медведей: <b>{u['bears']}</b>\n"
        f"🏆 Побед: <b>{u['wins']}</b> · 🎮 Игр: <b>{u['total_games']}</b>"
    )
    result = await send_ephemeral_or_normal(
        context.bot, cid, u_obj.id, text, reply_to_id=update.message.message_id,
    )
    if isinstance(result, dict) and result.get("ephemeral_message_id"):
        try:
            await update.message.react([ReactionTypeEmoji(emoji="👀")])
        except TelegramError:
            pass


async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id
    await db_ensure_user(u.id, cid, u.username or "", u.first_name)
    uu = await db_get_user(u.id, cid)

    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{u.id}"

    ref_count = uu.get("referral_count") or 0
    earned = ref_count * REFERRAL_BONUS_INVITER

    text = (
        f"🔗 <b>Реферальная ссылка</b>\n\n"
        f"Поделись ссылкой — получите бонус оба:\n"
        f"💎 Ты получишь: <b>+{fmt(REFERRAL_BONUS_INVITER)} VRF</b> за каждого\n"
        f"💎 Друг получит: <b>+{fmt(REFERRAL_BONUS_NEW)} VRF</b>\n\n"
        f"📊 Приглашено: <b>{ref_count}</b> чел. · Заработано: <b>{fmt(earned)} VRF</b>\n\n"
        f"<code>{ref_link}</code>"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"ref {u.id}"),
        ]]),
    )


@only_groups
async def cmd_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    cid = update.effective_chat.id

    if not update.message.reply_to_message or update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text("❌ Ответь на сообщение получателя!")
        return

    target = update.message.reply_to_message.from_user
    if target.id == sender.id:
        await update.message.reply_text("🎁 Нельзя дарить себе!")
        return

    await db_ensure_user(sender.id, cid, sender.username or "", sender.first_name)
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)

    su = await db_get_user(sender.id, cid)
    if su["vrf"] < GIFT_COST:
        await update.message.reply_text(f"❌ Нужно {GIFT_COST} VRF · Есть: {su['vrf']} VRF")
        return

    last_gift = su.get("last_gift")
    if last_gift:
        elapsed = (datetime.now() - datetime.fromisoformat(last_gift)).total_seconds()
        if elapsed < GIFT_COOLDOWN_H * 3600:
            rem = int(GIFT_COOLDOWN_H * 3600 - elapsed)
            await update.message.reply_text(f"⏰ Следующий подарок через {fmt_cd(rem)}")
            return

    m = await db_get_marriage(sender.id, cid)
    reward = GIFT_MARRIED_REWARD if (m and partner_id(m, sender.id) == target.id) else GIFT_REWARD

    if not await db_deduct_vrf(sender.id, cid, GIFT_COST):
        await update.message.reply_text("❌ Недостаточно VRF")
        return

    new_bal = await db_add_vrf(target.id, cid, reward)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_gift=? WHERE user_id=? AND chat_id=?",
                         (_now(), sender.id, cid))
        await db.commit()

    partner_mark = " 💍 (бонус партнёра)" if reward == GIFT_MARRIED_REWARD else ""
    await update.message.reply_text(
        f"🎁 {mention(sender.id, sender.first_name)} дарит VRF!\n"
        f"→ {mention(target.id, target.first_name)}\n"
        f"💎 +{reward} VRF{partner_mark}\n"
        f"Баланс: {fmt(new_bal)} VRF",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_love(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    cid = update.effective_chat.id

    if not update.message.reply_to_message or update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text("❌ Ответь на сообщение получателя!")
        return

    target = update.message.reply_to_message.from_user
    if target.id == sender.id:
        await update.message.reply_text("💘 Начни любить других, а не только себя!")
        return

    await db_ensure_user(sender.id, cid, sender.username or "", sender.first_name)
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)

    su = await db_get_user(sender.id, cid)
    last_love = su.get("last_love")
    if last_love:
        elapsed = (datetime.now() - datetime.fromisoformat(last_love)).total_seconds()
        if elapsed < LOVE_COOLDOWN_M * 60:
            rem = int(LOVE_COOLDOWN_M * 60 - elapsed)
            await update.message.reply_text(f"⏰ Любовь можно слать через {fmt_cd(rem)}")
            return

    m = await db_get_marriage(sender.id, cid)
    is_partner = m and partner_id(m, sender.id) == target.id
    s_reward = LOVE_MARRIED_REWARD if is_partner else LOVE_REWARD
    r_reward = LOVE_MARRIED_REWARD if is_partner else LOVE_REWARD

    await db_add_vrf(sender.id, cid, s_reward)
    new_bal = await db_add_vrf(target.id, cid, r_reward)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_love=? WHERE user_id=? AND chat_id=?",
                         (_now(), sender.id, cid))
        await db.commit()

    actions = ["шлёт поцелуй 💋", "обнимает 🤗", "дарит цветок 🌸", "признаётся в любви 💌"]
    if is_partner:
        actions = ["целует свою половинку 💋", "обнимает любимого(ую) 🤗", "дарит красную розу 🌹"]

    await update.message.reply_text(
        f"{E_LOVE} {mention(sender.id, sender.first_name)} {random.choice(actions)}\n"
        f"→ {mention(target.id, target.first_name)}\n"
        f"💎 Оба получают +{r_reward} VRF"
        + (" 💍" if is_partner else ""),
        parse_mode=ParseMode.HTML,
    )
    try:
        await update.message.react([ReactionTypeEmoji(emoji="❤️")])
    except TelegramError:
        pass


# ── Marriage commands ──────────────────────────────────

@only_groups
async def cmd_marry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    proposer = update.effective_user
    cid = update.effective_chat.id

    target, err = await _resolve_target(update, context, cid)
    if err:
        await update.message.reply_text(err)
        return
    if not target:
        await update.message.reply_text("❌ Укажи пользователя через ответ или @username")
        return
    if target.id == proposer.id:
        await update.message.reply_text("💘 Жениться на себе нельзя!")
        return
    if await db_get_marriage(proposer.id, cid):
        await update.message.reply_text("💍 Ты уже в браке! Сначала /divorce")
        return
    if await db_get_marriage(target.id, cid):
        await update.message.reply_text(f"💔 {mention(target.id, target.first_name)} уже в браке!", parse_mode=ParseMode.HTML)
        return

    await db_ensure_user(proposer.id, cid, proposer.username or "", proposer.first_name)
    await db_ensure_user(target.id, cid, getattr(target, "username", "") or "", target.first_name)

    prop = await db_get_proposal_to(proposer.id, cid)
    if prop and prop["proposer_id"] == target.id:
        await db_create_marriage(proposer.id, target.id, cid)
        await update.message.reply_text(
            f"{E_RING} <b>Взаимная любовь — Свадьба!</b>\n\n"
            f"💑 {mention(proposer.id, proposer.first_name)} ❤️ {mention(target.id, target.first_name)}\n\n"
            f"🎊 Поздравляем! Бонус к /daily активирован!",
            parse_mode=ParseMode.HTML,
        )
        try:
            await update.message.react([ReactionTypeEmoji(emoji="🎊")])
        except TelegramError:
            pass
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO proposals(proposer_id,target_id,chat_id,created_at) VALUES(?,?,?,?)",
            (proposer.id, target.id, cid, _now()),
        )
        await db.commit()

    phrase = random.choice(["делает предложение", "встаёт на одно колено перед", "хочет связать жизнь с"])
    await update.message.reply_text(
        f"{E_RING} {mention(proposer.id, proposer.first_name)} {phrase} {mention(target.id, target.first_name)}!\n\nПримешь предложение?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Да! 💍", callback_data=f"ma:{proposer.id}:{target.id}"),
            InlineKeyboardButton("Нет 💔", callback_data=f"mr:{proposer.id}:{target.id}"),
        ]]),
    )


@only_groups
async def cmd_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id
    prop = await db_get_proposal_to(u.id, cid)
    if not prop:
        await update.message.reply_text("❌ У тебя нет входящих предложений")
        return
    if await db_get_marriage(u.id, cid) or await db_get_marriage(prop["proposer_id"], cid):
        await update.message.reply_text("❌ Один из вас уже в браке!")
        return
    pu = await db_get_user(prop["proposer_id"], cid)
    pname = pu["first_name"] if pu else "Партнёр"
    await db_create_marriage(prop["proposer_id"], u.id, cid)
    await update.message.reply_text(
        f"💒 <b>Поздравляем с бракосочетанием!</b>\n\n"
        f"💑 {mention(prop['proposer_id'], pname)} ❤️ {mention(u.id, u.first_name)}\n\n"
        f"🎊 Бонус к /daily активирован!",
        parse_mode=ParseMode.HTML,
    )
    try:
        await update.message.react([ReactionTypeEmoji(emoji="🎊")])
    except TelegramError:
        pass


@only_groups
async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id
    prop = await db_get_proposal_to(u.id, cid)
    if not prop:
        await update.message.reply_text("❌ У тебя нет входящих предложений")
        return
    pu = await db_get_user(prop["proposer_id"], cid)
    pname = pu["first_name"] if pu else "Пользователь"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM proposals WHERE target_id=? AND chat_id=?", (u.id, cid))
        await db.commit()
    await update.message.reply_text(
        f"💔 {mention(u.id, u.first_name)} отклонил(а) предложение от {mention(prop['proposer_id'], pname)}",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_divorce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id
    m = await db_get_marriage(u.id, cid)
    if not m:
        await update.message.reply_text("💔 Ты не в браке")
        return
    pid = partner_id(m, u.id)
    pu = await db_get_user(pid, cid)
    pname = pu["first_name"] if pu else "Партнёр"
    d = days_ago(m["married_at"])
    await db_delete_marriage(m["id"])
    await update.message.reply_text(
        f"💔 <b>Развод оформлен</b>\n\nПосле {d} дней вместе...\n"
        f"{mention(u.id, u.first_name)} и {mention(pid, pname)} расстались.",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_marriage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cid = update.effective_chat.id
    await db_ensure_user(u.id, cid, u.username or "", u.first_name)
    m = await db_get_marriage(u.id, cid)
    if not m:
        prop = await db_get_proposal_to(u.id, cid)
        if prop:
            pu = await db_get_user(prop["proposer_id"], cid)
            pname = pu["first_name"] if pu else "Кто-то"
            await update.message.reply_text(
                f"{E_RING} Предложение от {mention(prop['proposer_id'], pname)}!\n"
                f"💍 /accept — принять · 💔 /reject — отклонить",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text("💔 Ты не в браке.\n\n/marry @username — найди пару!")
        return
    pid = partner_id(m, u.id)
    pu = await db_get_user(pid, cid)
    pname = pu["first_name"] if pu else "Партнёр"
    since = datetime.fromisoformat(m["married_at"])
    delta = datetime.now() - since
    await update.message.reply_text(
        f"💑 <b>Ваш брак</b>\n\n"
        f"  {mention(u.id, u.first_name)}\n  ❤️\n  {mention(pid, pname)}\n\n"
        f"⏰ Вместе: <b>{delta.days} дн. {delta.seconds//3600} ч.</b>\n"
        f"📅 С: <b>{since.strftime('%d.%m.%Y')}</b>\n\n"
        f"🎁 Бонус: +{DAILY_MARRIED_BONUS} VRF к /daily",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_marriages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cid = update.effective_chat.id
    all_m = await db_all_marriages(cid)
    if not all_m:
        await update.message.reply_text("💔 В чате пока нет пар.\n\n/marry — найди свою половинку!")
        return
    lines = [f"💑 <b>Пары чата ({len(all_m)})</b>\n"]
    shown = 0
    for m in all_m:
        u1 = await db_get_user(m["user1_id"], cid)
        u2 = await db_get_user(m["user2_id"], cid)
        if not u1 or not u2:
            continue
        shown += 1
        lines.append(
            f"{shown}. {mention(m['user1_id'], u1['first_name'])} ❤️ "
            f"{mention(m['user2_id'], u2['first_name'])} · {days_ago(m['married_at'])} дн."
        )
        if shown >= 15:
            break
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Clan commands ──────────────────────────────────────

@only_groups
async def cmd_clan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u, cid = update.effective_user, update.effective_chat.id
    await db_ensure_user(u.id, cid, u.username or "", u.first_name)
    text, kb = await _clan_hub_text(u.id, cid)
    result = await send_ephemeral_or_normal(
        context.bot, cid, u.id, text, reply_markup=kb,
        reply_to_id=update.message.message_id,
    )
    if isinstance(result, dict) and result.get("ephemeral_message_id"):
        try:
            await update.message.react([ReactionTypeEmoji(emoji="🏰")])
        except TelegramError:
            pass


async def _clan_hub_text(uid: int, cid: int) -> Tuple[str, InlineKeyboardMarkup]:
    clan = await db_get_user_clan(uid, cid)
    if not clan:
        text = (
            "🏰 <b>Кланы</b>\n\n"
            "Ты пока не состоишь ни в одном клане.\n\n"
            f"➕ Создать свой — <b>{fmt(CLAN_CREATE_COST)} VRF</b>\n"
            f"📋 Или вступи в существующий"
        )
        return text, _clan_kb_hub(False, False, False)

    role = CLAN_ROLES.get(clan["my_role"], CLAN_ROLES["member"])
    is_leader = clan["my_role"] == "leader"
    role_line = "👑 <b>Лидер</b>" if is_leader else f"{role['emoji']} <b>{role['label']}</b>"
    apps = await db_get_clan_applications(clan["id"]) if is_leader else []
    members = await db_get_clan_members(clan["id"])

    text = (
        f"🏰 <b>{clan['name']}</b>\n\n"
        f"👑 Лидер: {mention(clan['leader_id'], clan.get('leader_name') or 'Лидер')}\n"
        f"💰 Казна: <b>{fmt(clan['treasury'])} VRF</b>\n"
        f"🛡 Защита: уровень <b>{clan['defense_level']}</b>/{CLAN_MAX_DEFENSE_LVL}\n"
        f"👥 Участников: <b>{len(members)}</b>\n"
        f"🎭 Твоя роль: {role_line}\n"
    )
    if is_leader and apps:
        text += f"\n📨 Заявок на вступление: <b>{len(apps)}</b>"
    return text, _clan_kb_hub(True, is_leader, bool(apps))


def _clan_kb_hub(has_clan: bool, is_leader: bool, has_apps: bool) -> InlineKeyboardMarkup:
    if not has_clan:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать клан", callback_data="cl:create")],
            [InlineKeyboardButton("📋 Список кланов", callback_data="cl:browse")],
            [InlineKeyboardButton("🏆 Топ кланов", callback_data="cl:top")],
        ])
    rows = [
        [InlineKeyboardButton("👥 Участники", callback_data="cl:members"),
         InlineKeyboardButton("🎭 Моя роль", callback_data="cl:roles")],
        [InlineKeyboardButton("💰 Казна", callback_data="cl:treasury"),
         InlineKeyboardButton("🛡 Защита", callback_data="cl:defense")],
        [InlineKeyboardButton("⚔️ Рейд на клан", callback_data="cl:raid_list"),
         InlineKeyboardButton("📜 История войн", callback_data="cl:warlog")],
        [InlineKeyboardButton("🏆 Топ кланов", callback_data="cl:top")],
    ]
    if is_leader:
        app_label = "📨 Заявки 🔴" if has_apps else "📨 Заявки"
        rows.append([InlineKeyboardButton(app_label, callback_data="cl:apps"),
                    InlineKeyboardButton("👑 Передать лидерство", callback_data="cl:transfer_list")])
        rows.append([InlineKeyboardButton("❌ Расформировать", callback_data="cl:disband")])
    else:
        rows.append([InlineKeyboardButton("🚪 Покинуть клан", callback_data="cl:leave")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════
#  MODERATION COMMANDS
# ══════════════════════════════════════════════════════

_WARN_LIMIT = 3
_WARN_AUTO_MUT = timedelta(hours=24)

_MUTED_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)
_FULL_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
)


async def _is_protected(chat, uid: int) -> bool:
    try:
        m = await chat.get_member(uid)
        return m.status in ("administrator", "creator")
    except TelegramError:
        return False


def _fmt_until(until: Optional[datetime]) -> str:
    if until is None:
        return "навсегда"
    rem = (until - datetime.now()).total_seconds()
    return fmt_cd(int(rem)) if rem > 0 else "истёк"


def _mod_dur(args: list, default: Optional[timedelta] = timedelta(days=7)) -> tuple:
    FOREVER = {"навсегда", "perma", "forever", "перм", "perm", "inf", "∞"}
    SECS = {
        frozenset({"с", "сек", "секунд", "секунды", "sec", "s"}): 1,
        frozenset({"мин", "мин.", "минут", "минуты", "м", "min", "m", "minute", "minutes"}): 60,
        frozenset({"ч", "час", "часа", "часов", "h", "hour", "hours", "hr"}): 3600,
        frozenset({"д", "дн", "день", "дня", "дней", "d", "day", "days"}): 86400,
        frozenset({"н", "нед", "неделя", "недели", "недель", "w", "week", "weeks"}): 604800,
        frozenset({"мес", "месяц", "месяца", "месяцев", "mo", "month", "months"}): 2592000,
    }
    if not args:
        return default, ""

    first = args[0].lower()
    if first in FOREVER:
        return None, " ".join(args[1:])

    if first.isdigit():
        return timedelta(minutes=int(first)), " ".join(args[1:])

    import re as _re
    m = _re.match(r"^(\d+)([а-яёa-z.]+)$", first)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        for unit_set, secs in SECS.items():
            if unit in unit_set:
                return timedelta(seconds=n * secs), " ".join(args[1:])

    return default, " ".join(args)


async def db_log_mute(uid: int, cid: int, by: int, until: Optional[datetime], reason: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO mutes (user_id,chat_id,muted_by,muted_at,until,reason)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id,chat_id) DO UPDATE SET
                   muted_by=excluded.muted_by, muted_at=excluded.muted_at,
                   until=excluded.until, reason=excluded.reason""",
            (uid, cid, by, _now(), until.isoformat() if until else None, reason),
        )
        await db.commit()


async def db_clear_mute(uid: int, cid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM mutes WHERE user_id=? AND chat_id=?", (uid, cid))
        await db.commit()


async def db_get_mutes(cid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM mutes WHERE chat_id=? ORDER BY muted_at DESC", (cid,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_add_warn(uid: int, cid: int, by: int, reason: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warns (user_id,chat_id,warned_by,warned_at,reason) VALUES (?,?,?,?,?)",
            (uid, cid, by, _now(), reason),
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND chat_id=? AND active=1",
            (uid, cid),
        ) as cur:
            return (await cur.fetchone())[0]


async def db_remove_last_warn(uid: int, cid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM warns WHERE user_id=? AND chat_id=? AND active=1 ORDER BY warned_at DESC LIMIT 1",
            (uid, cid),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("UPDATE warns SET active=0 WHERE id=?", (row[0],))
        await db.commit()
        return True


async def db_clear_warns(uid: int, cid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND chat_id=? AND active=1",
            (uid, cid),
        ) as cur:
            count = (await cur.fetchone())[0]
        await db.execute(
            "UPDATE warns SET active=0 WHERE user_id=? AND chat_id=?", (uid, cid)
        )
        await db.commit()
        return count


async def db_get_user_warns(uid: int, cid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warns WHERE user_id=? AND chat_id=? AND active=1 ORDER BY warned_at DESC",
            (uid, cid),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_get_chat_warns(cid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_id, COUNT(*) AS cnt FROM warns
               WHERE chat_id=? AND active=1 GROUP BY user_id ORDER BY cnt DESC LIMIT 20""",
            (cid,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


@only_groups
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    caller = update.effective_user
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text(
            "📌 Ответь на сообщение пользователя:\n"
            "<code>/mute [10m / 2h / 1d / навсегда] [причина]</code>\n"
            "По умолчанию: 7 дней",
            parse_mode=ParseMode.HTML,
        )
        return

    target = msg.reply_to_message.from_user
    if target.id == caller.id:
        await msg.reply_text("❌ Нельзя замутить себя")
        return
    if await _is_protected(update.effective_chat, target.id):
        await msg.reply_text("❌ Нельзя замутить администратора")
        return

    dur, reason = _mod_dur(context.args)
    until_dt = datetime.now() + dur if dur else None

    try:
        await context.bot.restrict_chat_member(
            cid, target.id, _MUTED_PERMS, until_date=until_dt,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    await db_ensure_user(target.id, cid, target.username or "", target.first_name)
    await db_log_mute(target.id, cid, caller.id, until_dt, reason)

    await msg.reply_text(
        f"🔇 {mention(target.id, target.first_name)} — <b>мут</b>\n"
        f"⏱ Срок: <b>{_fmt_until(until_dt)}</b>"
        + (f"\n📝 Причина: {reason}" if reason else ""),
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text("📌 Ответь на сообщение пользователя: <code>/unmute</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    cid = update.effective_chat.id

    try:
        await context.bot.restrict_chat_member(cid, target.id, _FULL_PERMS)
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    await db_clear_mute(target.id, cid)
    await msg.reply_text(
        f"🔊 {mention(target.id, target.first_name)} — <b>мут снят</b>",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text("📌 Ответь на сообщение: <code>/kick [причина]</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    if await _is_protected(update.effective_chat, target.id):
        await msg.reply_text("❌ Нельзя кикнуть администратора")
        return

    reason = " ".join(context.args) if context.args else ""
    try:
        await context.bot.ban_chat_member(cid, target.id)
        await asyncio.sleep(0.3)
        await context.bot.unban_chat_member(cid, target.id)
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    await msg.reply_text(
        f"👢 {mention(target.id, target.first_name)} — <b>исключён</b>"
        + (f"\n📝 {reason}" if reason else ""),
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    caller = update.effective_user
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text(
            "📌 Ответь на сообщение:\n"
            "<code>/ban [срок] [причина]</code>  (без срока = навсегда)",
            parse_mode=ParseMode.HTML,
        )
        return

    target = msg.reply_to_message.from_user
    if await _is_protected(update.effective_chat, target.id):
        await msg.reply_text("❌ Нельзя забанить администратора")
        return

    dur, reason = _mod_dur(context.args, default=None)
    until_dt = datetime.now() + dur if dur else None

    try:
        await context.bot.ban_chat_member(
            cid, target.id, until_date=until_dt, revoke_messages=False,
        )
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    await msg.reply_text(
        f"🚫 {mention(target.id, target.first_name)} — <b>заблокирован</b>\n"
        f"⏱ Срок: <b>{_fmt_until(until_dt)}</b>"
        + (f"\n📝 Причина: {reason}" if reason else ""),
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message

    if not msg.reply_to_message:
        await msg.reply_text("📌 Ответь на сообщение: <code>/unban</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    cid = update.effective_chat.id

    try:
        await context.bot.unban_chat_member(cid, target.id, only_if_banned=True)
    except TelegramError as e:
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    await msg.reply_text(
        f"✅ {mention(target.id, target.first_name)} — <b>разблокирован</b>",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    caller = update.effective_user
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text("📌 Ответь на сообщение: <code>/pred [причина]</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    if await _is_protected(update.effective_chat, target.id):
        await msg.reply_text("❌ Нельзя варнить администратора")
        return

    reason = " ".join(context.args) if context.args else ""
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)
    count = await db_add_warn(target.id, cid, caller.id, reason)

    filled = "⚠️" * count
    empty = "□" * max(0, _WARN_LIMIT - count)
    bar = filled + empty

    text = (
        f"⚠️ {mention(target.id, target.first_name)} — <b>предупреждение</b>\n"
        f"Варнов: <b>{count}/{_WARN_LIMIT}</b>  {bar}"
        + (f"\n📝 Причина: {reason}" if reason else "")
    )

    if count >= _WARN_LIMIT:
        try:
            until_dt = datetime.now() + _WARN_AUTO_MUT
            await context.bot.restrict_chat_member(
                cid, target.id, _MUTED_PERMS, until_date=until_dt,
            )
            await db_log_mute(target.id, cid, caller.id, until_dt, f"Автомут — {count} варнов")
            await db_clear_warns(target.id, cid)
            text += f"\n\n🔇 <b>Лимит!</b> Автомут на {fmt_cd(int(_WARN_AUTO_MUT.total_seconds()))}"
        except TelegramError:
            pass

    await msg.reply_text(text, parse_mode=ParseMode.HTML)


@only_groups
async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text("📌 Ответь на сообщение: <code>/unpred</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    ok = await db_remove_last_warn(target.id, cid)
    if ok:
        remaining = len(await db_get_user_warns(target.id, cid))
        await msg.reply_text(
            f"✅ Последний варн {mention(target.id, target.first_name)} снят. "
            f"Осталось: <b>{remaining}/{_WARN_LIMIT}</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.reply_text(
            f"❌ У {mention(target.id, target.first_name)} нет активных варнов",
            parse_mode=ParseMode.HTML,
        )


@only_groups
async def cmd_clearwarns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    cid = update.effective_chat.id

    if not msg.reply_to_message or msg.reply_to_message.from_user.is_bot:
        await msg.reply_text("📌 Ответь на сообщение: <code>/clearpred</code>",
                             parse_mode=ParseMode.HTML)
        return

    target = msg.reply_to_message.from_user
    count = await db_clear_warns(target.id, cid)
    await msg.reply_text(
        f"✅ Сняты все варны (<b>{count}</b>) у {mention(target.id, target.first_name)}",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_warnlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    msg = update.message
    cid = update.effective_chat.id

    if msg.reply_to_message and not msg.reply_to_message.from_user.is_bot:
        target = msg.reply_to_message.from_user
        warns = await db_get_user_warns(target.id, cid)
        if not warns:
            await msg.reply_text(
                f"✅ У {mention(target.id, target.first_name)} нет варнов",
                parse_mode=ParseMode.HTML,
            )
            return
        lines = [
            f"{i+1}. <code>{w['warned_at'][:10]}</code>"
            + (f" — {w['reason']}" if w.get("reason") else "")
            for i, w in enumerate(warns)
        ]
        await msg.reply_text(
            f"⚠️ Варны {mention(target.id, target.first_name)}: "
            f"<b>{len(warns)}/{_WARN_LIMIT}</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
        return

    rows = await db_get_chat_warns(cid)
    if not rows:
        await msg.reply_text("✅ Нет активных варнов в чате")
        return
    lines = [
        f"• {mention(r['user_id'], 'id'+str(r['user_id']))} — "
        f"<b>{r['cnt']}/{_WARN_LIMIT}</b> варн."
        for r in rows
    ]
    await msg.reply_text(
        f"⚠️ <b>Варны в чате</b>:\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        return
    cid = update.effective_chat.id
    mutes = await db_get_mutes(cid)
    if not mutes:
        await update.message.reply_text("✅ Нет замутенных")
        return
    lines = []
    for m in mutes[:20]:
        until = datetime.fromisoformat(m["until"]) if m.get("until") else None
        r = m.get("reason", "")
        lines.append(
            f"• {mention(m['user_id'], 'id'+str(m['user_id']))} — "
            f"⏱{_fmt_until(until)}"
            + (f" [{r}]" if r else "")
        )
    await update.message.reply_text(
        f"🔇 <b>Замутенные ({len(mutes)})</b>:\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Нет доступа — только для администраторов")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="ap:stats"),
         InlineKeyboardButton("🏆 Топ VRF", callback_data="ap:top")],
        [InlineKeyboardButton("💑 Все браки", callback_data="ap:marriages"),
         InlineKeyboardButton("👮 Бот-админы", callback_data="ap:admins")],
        [InlineKeyboardButton("📋 Все команды", callback_data="ap:cmds"),
         InlineKeyboardButton("ℹ️ Управление", callback_data="ap:manage")],
        [InlineKeyboardButton("🛡️ Модерация", callback_data="ap:mod")],
        [InlineKeyboardButton("Закрыть", callback_data="ap:close")],
    ])
    await update.message.reply_text(
        f"🛡️ <b>Verifure Admin Panel</b>\n\n{E_ALERT} Выбери раздел:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@only_groups
async def cmd_givevrf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Только для администраторов")
        return
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("Использование: /givevrf <сумма> (ответом)")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Укажи сумму: /givevrf 500")
        return
    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)
    new_bal = await db_add_vrf(target.id, cid, amount)
    await update.message.reply_text(
        f"✅ Выдано <b>{fmt(amount)} VRF</b> → {mention(target.id, target.first_name)}\n"
        f"💎 Баланс: {fmt(new_bal)} VRF",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_takevrf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Только для администраторов")
        return
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("Использование: /takevrf <сумма> (ответом)")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Укажи сумму")
        return
    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    u = await db_get_user(target.id, cid)
    if not u:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    new_val = max(0, u["vrf"] - amount)
    await db_set_vrf(target.id, cid, new_val)
    await update.message.reply_text(
        f"✅ Списано <b>{fmt(amount)} VRF</b> у {mention(target.id, target.first_name)}\n"
        f"💎 Баланс: {fmt(new_val)} VRF",
        parse_mode=ParseMode.HTML,
    )


async def db_set_vrf(uid: int, cid: int, amount: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vrf=? WHERE user_id=? AND chat_id=?",
            (max(0, amount), uid, cid),
        )
        await db.commit()
    return max(0, amount)


@only_groups
async def cmd_givebear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Только для администраторов")
        return
    if not update.message.reply_to_message or update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text(
            "📌 Ответь на сообщение пользователя:\n"
            "<code>/givebear [кол-во]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    count = 1
    if context.args:
        try:
            count = int(context.args[0])
        except ValueError:
            pass
    count = max(1, min(count, 1000))

    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET bears=bears+? WHERE user_id=? AND chat_id=?",
            (count, target.id, cid),
        )
        await db.commit()

    u = await db_get_user(target.id, cid)
    await update.message.reply_text(
        f"🐻 {mention(target.id, target.first_name)} получает "
        f"<b>{count}🐻</b>!\n"
        f"Итого медведей: <b>{u['bears']}🐻</b>",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_takebear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Только для администраторов")
        return
    if not update.message.reply_to_message or update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text(
            "📌 Ответь на сообщение пользователя:\n"
            "<code>/takebear [кол-во]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    count = 1
    if context.args:
        try:
            count = int(context.args[0])
        except ValueError:
            pass
    count = max(1, min(count, 1000))

    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    await db_ensure_user(target.id, cid, target.username or "", target.first_name)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET bears=MAX(0, bears-?) WHERE user_id=? AND chat_id=?",
            (count, target.id, cid),
        )
        await db.commit()

    u = await db_get_user(target.id, cid)
    await update.message.reply_text(
        f"🐻 У {mention(target.id, target.first_name)} изъято "
        f"<b>{count}🐻</b>.\n"
        f"Осталось медведей: <b>{u['bears']}🐻</b>",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Нет доступа")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    t = update.message.reply_to_message.from_user
    if t.is_bot:
        await update.message.reply_text("❌ Нельзя добавить бота")
        return
    await db_add_admin(t.id, t.username or "", t.first_name or "", update.effective_user.id)
    await update.message.reply_text(
        f"✅ {mention(t.id, t.first_name)} добавлен как бот-администратор!",
        parse_mode=ParseMode.HTML,
    )


@only_groups
async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Нет доступа")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение пользователя")
        return
    t = update.message.reply_to_message.from_user
    if await db_remove_admin(t.id):
        await update.message.reply_text(f"✅ {mention(t.id, t.first_name)} удалён из бот-администраторов",
                                        parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ {mention(t.id, t.first_name)} не является бот-администратором",
                                        parse_mode=ParseMode.HTML)


@only_groups
async def cmd_listadmins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_group_or_bot_admin(update):
        await update.message.reply_text("❌ Нет доступа")
        return
    admins = await db_list_admins()
    lines = ["👮 <b>Бот-администраторы</b>\n"]
    for a in admins:
        uname = f" @{a['username']}" if a["username"] else ""
        lines.append(f"• {mention(a['user_id'], a['first_name'])}{uname}")
    if ADMIN_IDS:
        lines.append(f"\n🔧 Env ADMIN_IDS: {', '.join(map(str, ADMIN_IDS))}")
    if not admins and not ADMIN_IDS:
        lines.append("Нет бот-администраторов")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════
#  OTHER COMMANDS (clan, etc. – trimmed for brevity)
# ══════════════════════════════════════════════════════

# ── Resolve target helper ─────────────────────────────

async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE, cid: int):
    if update.message.reply_to_message:
        t = update.message.reply_to_message.from_user
        if not t.is_bot:
            return t, None
    if context.args:
        uname = context.args[0].lstrip("@")
        row = await db_find_user_by_username(uname, cid)
        if row:
            class _FakeUser:
                id = row["user_id"]
                first_name = row["first_name"]
                username = row["username"]
                is_bot = False
            return _FakeUser(), None
        return None, f"❌ @{uname} не найден в чате."
    return None, "❌ Укажи пользователя: ответь на его сообщение или /команда @username"


async def db_find_user_by_username(username: str, cid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(username)=? AND chat_id=?",
            (username.lower().lstrip("@"), cid),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ── Cancel command ────────────────────────────────────

@only_groups
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel pending games – only crocodile game for now."""
    uid = update.effective_user.id
    cid = update.effective_chat.id
    cancelled = []

    game = crocodile_games.get(cid)
    if game and game["active"] and game["show_user_id"] == uid:
        game["active"] = False
        del crocodile_games[cid]
        cancelled.append("🐊 Крокодил")

    if cancelled:
        await update.message.reply_text(
            f"✅ <b>Отменено:</b> {', '.join(cancelled)}",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("❌ Нет активных игр для отмены")


# ══════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    cid = query.message.chat_id
    who = query.from_user

    # ── Crocodile pass ──────────────────────────────────
    if data.startswith("croc_pass:"):
        chat_id = int(data.split(":")[1])
        if chat_id != cid:
            await query.answer("❌ Неверный чат", show_alert=True)
            return
        # Reuse the pass command logic
        class FakeUpdate:
            effective_user = who
            effective_chat = query.message.chat
            message = query.message
        await cmd_croc_pass(FakeUpdate(), context)
        await query.answer()
        return

    if data.startswith("croc_end:"):
        chat_id = int(data.split(":")[1])
        if chat_id != cid:
            await query.answer("❌ Неверный чат", show_alert=True)
            return
        class FakeUpdate:
            effective_user = who
            effective_chat = query.message.chat
            message = query.message
        await cmd_croc_end(FakeUpdate(), context)
        await query.answer()
        return

    # ── Marriage ──────────────────────────────────────
    if data.startswith("ma:") or data.startswith("mr:"):
        parts = data.split(":")
        action = parts[0]
        p_id = int(parts[1])
        t_id = int(parts[2])

        if who.id != t_id:
            await query.answer("❌ Это предложение не для тебя!", show_alert=True)
            return
        prop = await db_get_proposal_to(t_id, cid)
        if not prop or prop["proposer_id"] != p_id:
            await query.answer("❌ Предложение уже недействительно", show_alert=True)
            await query.edit_message_reply_markup(None)
            return
        pu = await db_get_user(p_id, cid)
        pname = pu["first_name"] if pu else "Партнёр"

        if action == "ma":
            if await db_get_marriage(p_id, cid) or await db_get_marriage(t_id, cid):
                await query.answer("❌ Один из вас уже в браке!", show_alert=True)
                return
            await db_create_marriage(p_id, t_id, cid)
            await query.answer("💍 Поздравляем!")
            await query.edit_message_text(
                f"💒 <b>СВАДЬБА!</b>\n\n"
                f"💑 {mention(p_id, pname)} ❤️ {mention(t_id, who.first_name)}\n\n"
                f"🎊 Поздравляем! Бонус к /daily активирован!",
                parse_mode=ParseMode.HTML,
            )
        else:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM proposals WHERE target_id=? AND chat_id=?",
                                 (t_id, cid))
                await db.commit()
            await query.answer("💔 Отклонено")
            await query.edit_message_text(
                f"💔 {mention(t_id, who.first_name)} отклонил(а) предложение от {mention(p_id, pname)}",
                parse_mode=ParseMode.HTML,
            )
        return

    # ── Admin panel ──────────────────────────────────────
    if data.startswith("ap:"):
        uid = who.id
        is_adm = await is_bot_admin(uid)
        if not is_adm:
            try:
                member = await query.message.chat.get_member(uid)
                is_adm = member.status in ("administrator", "creator")
            except TelegramError:
                pass
        if not is_adm:
            await query.answer("❌ Нет доступа", show_alert=True)
            return

        action = data[3:]
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="ap:back")]])

        if action == "back":
            await query.answer()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Статистика", callback_data="ap:stats"),
                 InlineKeyboardButton("🏆 Топ VRF", callback_data="ap:top")],
                [InlineKeyboardButton("💑 Все браки", callback_data="ap:marriages"),
                 InlineKeyboardButton("👮 Бот-админы", callback_data="ap:admins")],
                [InlineKeyboardButton("📋 Все команды", callback_data="ap:cmds"),
                 InlineKeyboardButton("ℹ️ Управление", callback_data="ap:manage")],
                [InlineKeyboardButton("🛡️ Модерация", callback_data="ap:mod")],
                [InlineKeyboardButton("Закрыть", callback_data="ap:close")],
            ])
            await query.edit_message_text(
                f"🛡️ <b>Verifure Admin Panel</b>\n\n{E_ALERT} Выбери раздел:",
                parse_mode=ParseMode.HTML, reply_markup=kb,
            )
        elif action == "close":
            await query.answer("Закрыто")
            await query.message.delete()
        elif action == "mod":
            # Simplified mod panel
            await query.answer()
            mod_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 Замутить", callback_data="ap:mod_help_mute"),
                 InlineKeyboardButton("🔊 Размутить", callback_data="ap:mod_help_unmute")],
                [InlineKeyboardButton("⚠️ Варн", callback_data="ap:mod_help_warn"),
                 InlineKeyboardButton("✅ Снять варн", callback_data="ap:mod_help_unwarn")],
                [InlineKeyboardButton("👢 Кик", callback_data="ap:mod_help_kick"),
                 InlineKeyboardButton("🚫 Бан", callback_data="ap:mod_help_ban")],
                [InlineKeyboardButton("◀ Назад", callback_data="ap:back")],
            ])
            await query.edit_message_text(
                f"🛡️ <b>Модерация</b>\n\n"
                f"Команды (ответом на сообщение):\n"
                f"<code>/mute [10m/2h/1d/навсегда] [причина]</code>\n"
                f"<code>/unmute</code>\n"
                f"<code>/pred [причина]</code>  →  лимит {_WARN_LIMIT} → автомут 24ч\n"
                f"<code>/unpred</code>  ·  <code>/clearpred</code>\n"
                f"<code>/predlist</code>  ·  <code>/mutelist</code>\n"
                f"<code>/kick [причина]</code>\n"
                f"<code>/ban [срок] [причина]</code>  ·  <code>/unban</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=mod_kb,
            )
        elif action == "stats":
            await query.answer()
            total = await db_count_users(cid)
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT COUNT(*) FROM marriages WHERE chat_id=?", (cid,)) as cur:
                    marriages = (await cur.fetchone())[0]
                async with db.execute("SELECT SUM(total_games),SUM(vrf),SUM(wins) FROM users WHERE chat_id=?", (cid,)) as cur:
                    row = await cur.fetchone()
                    games, vrf, wins = row[0] or 0, row[1] or 0, row[2] or 0
            await query.edit_message_text(
                f"📊 <b>Статистика чата</b>\n\n"
                f"👥 Игроков: <b>{total}</b>\n"
                f"🎮 Сыграно: <b>{fmt(games)}</b>\n"
                f"🏆 Побед: <b>{fmt(wins)}</b>\n"
                f"💎 VRF в обороте: <b>{fmt(vrf)}</b>\n"
                f"💒 Браков: <b>{marriages}</b>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb,
            )
        elif action == "top":
            await query.answer()
            users = await db_top(cid, "vrf", 10)
            lines = ["💎 <b>Топ-10 VRF</b>\n"]
            for i, u in enumerate(users):
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                lines.append(
                    f"{medal} {mention(u['user_id'], u['first_name'])} — {fmt(u['vrf'])} VRF"
                )
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_kb)
        elif action == "marriages":
            await query.answer()
            all_m = await db_all_marriages(cid)
            lines = [f"💑 <b>Все браки ({len(all_m)})</b>\n"]
            for i, m in enumerate(all_m[:10]):
                u1 = await db_get_user(m["user1_id"], cid)
                u2 = await db_get_user(m["user2_id"], cid)
                n1 = u1["first_name"] if u1 else "?"
                n2 = u2["first_name"] if u2 else "?"
                lines.append(f"{i+1}. {n1} ❤️ {n2} — {days_ago(m['married_at'])} дн.")
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_kb)
        elif action == "admins":
            await query.answer()
            admins = await db_list_admins()
            lines = ["👮 <b>Бот-администраторы</b>\n"]
            for a in admins:
                uname = f" @{a['username']}" if a["username"] else ""
                lines.append(f"• {a['first_name']}{uname}")
            if ADMIN_IDS:
                lines.append(f"\n🔧 Env: {', '.join(map(str, ADMIN_IDS))}")
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_kb)
        elif action == "cmds":
            await query.answer()
            await query.edit_message_text(
                "📋 <b>Все команды</b>\n\n"
                "<b>Игроки:</b>\n"
                "/start /help /profile /top /stats /daily /bonus /ref /achievements\n"
                "/crocodile /croc /pass\n"
                "/marry /accept /reject /divorce /marriage /marriages\n"
                "/gift /love\n"
                "/clan\n\n"
                "<b>Администраторы:</b>\n"
                "/admin /givevrf /takevrf /givebear /takebear\n"
                "/addadmin /removeadmin /listadmins\n"
                "/mute /unmute /kick /ban /unban /warn /unwarn /clearwarns /warnlist /mutelist",
                parse_mode=ParseMode.HTML, reply_markup=back_kb,
            )
        elif action == "manage":
            await query.answer()
            await query.edit_message_text(
                "ℹ️ <b>Управление игроками</b>\n\n"
                "/givevrf &lt;n&gt; — выдать VRF (ответом)\n"
                "/takevrf &lt;n&gt; — забрать VRF (ответом)\n"
                "/givebear — выдать медведя 🐻 (ответом)\n"
                "/takebear — забрать медведя (ответом)\n"
                "/addadmin — сделать бот-админом (ответом)\n"
                "/removeadmin — убрать бот-админа (ответом)",
                parse_mode=ParseMode.HTML, reply_markup=back_kb,
            )
        return

    # ── Top tabs ──────────────────────────────────────
    if data.startswith("top:"):
        _, sort, _ = data.split(":")
        await query.answer()
        await _show_top(query, context, cid, sort, edit=True)
        return

    await query.answer()


# ══════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ══════════════════════════════════════════════════════

async def _touch_active_hook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global hook to track user activity."""
    u = update.effective_user
    c = update.effective_chat
    if not u or not c or u.is_bot or c.type == "private":
        return
    try:
        await db_ensure_user(u.id, c.id, u.username or "", u.first_name)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET last_active=? WHERE user_id=? AND chat_id=?",
                (_now(), u.id, c.id),
            )
            await db.commit()
    except Exception:
        pass


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    u = update.effective_user
    text = (update.message.text or "").strip()
    cid = update.effective_chat.id

    # ── Activity tracking ─────────────────────────────
    if update.effective_chat.type != "private":
        await db_log_activity(cid, msgs=1)

    # ── Crocodile guess handling ──────────────────────
    if text:
        await _handle_croc_guess(update, context)

    # ── Text shortcuts ──────────────────────────────────
    if update.effective_chat.type == "private":
        return

    low = text.lower()
    word = low.split()[0] if low else ""

    # ── Quick shortcuts ────────────────────────────────
    if word in ("б", "баланс", "balance", "bal"):
        uu = await db_get_user(u.id, cid)
        bal = uu["vrf"] if uu else 0
        lvl = get_level(uu["experience"]) if uu else 1
        short = f"💎 <b>{fmt(bal)} VRF</b>  |  🏅 Ур. {lvl}"
        result = await send_ephemeral_or_normal(
            context.bot, cid, u.id, short, reply_to_id=update.message.message_id,
        )
        if isinstance(result, dict) and result.get("ephemeral_message_id"):
            try:
                await update.message.react([ReactionTypeEmoji(emoji="👀")])
            except TelegramError:
                pass
        return

    if word in ("отмена", "стоп", "stop"):
        await cmd_cancel(update, context)
        return

    if word in ("топ", "top", "лидеры"):
        await cmd_top(update, context)
        return

    if word in ("проф", "профиль", "профа", "пр"):
        await cmd_profile(update, context)
        return

    if word in ("бонус", "bonus"):
        await cmd_bonus(update, context)
        return

    if word in ("брак", "свадьба", "marriage"):
        await cmd_marriage(update, context)
        return

    if word in ("помощь", "help", "хелп", "справка"):
        await cmd_help(update, context)
        return

    if word in ("крок", "крокодил", "crocodile", "croc"):
        await cmd_crocodile(update, context)
        return

    if word in ("кланы", "clan", "clans"):
        await cmd_clan(update, context)
        return

    # ── XP from messages ──────────────────────────────
    if update.effective_chat.type != "private":
        await db_log_activity(cid, msgs=1)
        # XP logic (simplified)
        if await db_can_earn_xp(u.id, cid):
            xp = random.randint(2, 8)
            new_lvl, leveled_up = await db_add_xp(u.id, cid, xp)
            if leveled_up:
                await update.message.reply_text(
                    f"🎉 {mention(u.id, u.first_name)} — <b>уровень {new_lvl}!</b> {get_rank(new_lvl)}",
                    parse_mode=ParseMode.HTML,
                )


async def db_can_earn_xp(uid: int, cid: int) -> bool:
    u = await db_get_user(uid, cid)
    if not u or not u["last_xp"]:
        return True
    return (datetime.now() - datetime.fromisoformat(u["last_xp"])).total_seconds() >= 60


# ══════════════════════════════════════════════════════
#  ONBOARDING & STARTUP
# ══════════════════════════════════════════════════════

async def on_startup(app: Application) -> None:
    await db_init()
    global crocodile_words
    crocodile_words = load_words()

    from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault

    cmds = [
        BotCommand("start", "🏠 Старт / Главное меню"),
        BotCommand("profile", "👤 Мой профиль"),
        BotCommand("top", "🏆 Топ игроков"),
        BotCommand("stats", "📊 Статистика чата"),
        BotCommand("statsimg", "📈 График активности"),
        BotCommand("daily", "⚡ Ежедневный бонус"),
        BotCommand("bonus", "📋 Статус бонусов"),
        BotCommand("ref", "🔗 Реферальная ссылка"),
        BotCommand("achievements", "🏅 Достижения"),
        BotCommand("gift", "🎁 Подарить VRF"),
        BotCommand("love", "💝 Любовь"),
        BotCommand("crocodile", "🐊 Крокодил (начать игру)"),
        BotCommand("pass", "🔄 Пропустить слово в Крокодиле"),
        BotCommand("cancel", "🚫 Отменить игру"),
        BotCommand("marry", "💒 Предложение"),
        BotCommand("marriage", "💑 Карточка брака"),
        BotCommand("marriages", "👫 Все пары"),
        BotCommand("divorce", "💔 Развод"),
        BotCommand("clan", "🏰 Кланы"),
        BotCommand("help", "ℹ️ Помощь"),
    ]

    try:
        await app.bot.set_my_commands(cmds, scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(cmds, scope=BotCommandScopeAllGroupChats())
    except Exception:
        pass

    log.info("Verifure Game 10.1 — Crocodile Edition is online!")


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════

def main() -> None:
    if not BOT_TOKEN:
        log.critical("BOT_TOKEN environment variable is not set!")
        raise SystemExit(1)

    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # ── Global activity tracker ──────────────────────
    app.add_handler(TypeHandler(Update, _touch_active_hook), group=-1)

    # ── Core commands ──────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("statsimg", cmd_statsimg))
    app.add_handler(CommandHandler("activity", cmd_activity))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("bonus", cmd_bonus))
    app.add_handler(CommandHandler("ref", cmd_ref))
    app.add_handler(CommandHandler("achievements", cmd_achievements))  # dummy, kept
    app.add_handler(CommandHandler("gift", cmd_gift))
    app.add_handler(CommandHandler("love", cmd_love))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # ── Crocodile ──────────────────────────────────────
    app.add_handler(CommandHandler(["crocodile", "croc"], cmd_crocodile))
    app.add_handler(CommandHandler("pass", cmd_croc_pass))
    app.add_handler(CommandHandler("endcroc", cmd_croc_end))  # optional

    # ── Marriage ──────────────────────────────────────
    app.add_handler(CommandHandler("marry", cmd_marry))
    app.add_handler(CommandHandler("accept", cmd_accept))
    app.add_handler(CommandHandler("reject", cmd_reject))
    app.add_handler(CommandHandler("divorce", cmd_divorce))
    app.add_handler(CommandHandler("marriage", cmd_marriage))
    app.add_handler(CommandHandler("marriages", cmd_marriages))

    # ── Clan ──────────────────────────────────────────
    app.add_handler(CommandHandler(["clan", "clans"], cmd_clan))

    # ── Admin ──────────────────────────────────────────
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("givevrf", cmd_givevrf))
    app.add_handler(CommandHandler("takevrf", cmd_takevrf))
    app.add_handler(CommandHandler("givebear", cmd_givebear))
    app.add_handler(CommandHandler("takebear", cmd_takebear))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("listadmins", cmd_listadmins))

    # ── Moderation ──────────────────────────────────────
    app.add_handler(CommandHandler(["mute", "mut"], cmd_mute))
    app.add_handler(CommandHandler(["unmute", "unmut"], cmd_unmute))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler(["pred", "warn"], cmd_warn))
    app.add_handler(CommandHandler(["unpred", "unwarn"], cmd_unwarn))
    app.add_handler(CommandHandler(["clearpred", "clearwarns"], cmd_clearwarns))
    app.add_handler(CommandHandler(["predlist", "warnlist"], cmd_warnlist))
    app.add_handler(CommandHandler("mutelist", cmd_mutelist))

    # ── Callbacks & messages ──────────────────────────
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Starting polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=[
        "message", "callback_query", "message_reaction",
    ])


# ── Dummy achievement command ─────────────────────────
async def cmd_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🏅 Достижения будут добавлены позже.")


if __name__ == "__main__":
    main()
