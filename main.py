# -*- coding: utf-8 -*-
"""
بوت تيليجرام - python-telegram-bot v20+ مع نظام ربط الحساب (Userbot)
التثبيت: pip install "python-telegram-bot>=20" telethon tzdata
"""

import asyncio
import html
import logging
import os
import random
import re
import sqlite3
import time
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup as Markup,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    AuthKeyUnregisteredError,
    SessionRevokedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
)
from telethon.tl.functions.account import UpdateProfileRequest

# ====================== الإعدادات ======================
TOKEN = "9241142597:AAEhjC43Ea2aIGz-i-tOLztASVIapZEhIGI"
OWNER_ID = 7753146356
ADMINS = [OWNER_ID]
REMOVED_ADMINS = [8664763495]
OWNER_USERNAME = "K000OOO"
TIMEZONE = "Asia/Baghdad"
DB_FILE = "bot.db"
DEV_LINK = "https://t.me/K000OOO"
CHANNEL_LINK = "https://t.me/GTB55"

API_ID = 36444028
API_HASH = "92aac2e192857ff973a9b3ae2a3274ca"

KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
PHONE_RE = re.compile(r"^\+\d{10,14}$")

RULES_MAIN = [
    "البوت يعرض الوقت يم اسمك بالبوت، ويتحدث وحده كل دقيقة بتوقيت بغداد.",
    "تختار تعرض الوقت مع م/ص أو بدونها، وتگدر تحذفه بأي وقت من زر «الوقت».",
    "ربط الحساب يكون برقمك انت فقط، ومسؤوليته عليك.",
    "ممنوع السبام أو الضغط المتكرر على الأزرار بشكل مزعج.",
    "ممنوع محاولة اختراق البوت أو استغلال أي ثغرة فيه.",
]
RULES_END = ["مخالفة أي قانون تعرضك للحظر من البوت بدون إنذار."]
FREE_RULE = "البوت مجاني بالكامل، بدون أي اشتراك مدفوع."

def _rules_sub():
    prices = "، ".join(f"{n} {p}" for n, p, _d in PLANS.values())
    return [
        "تگدر تشارك الاشتراك مع صديقك مجاناً، لكن إذا بعته لأي شخص راح تنحظر من البوت.",
        f"الاشتراك المدفوع بالنجوم: {prices}، وما ينسترجع بعد التفعيل.",
        "لتفعيل الاشتراك لازم تراسل المالك وتبعث النجوم، وبعدها يتفعّل اشتراكك.",
    ]

def build_rules(paid):
    items = RULES_MAIN + (_rules_sub() if paid else [FREE_RULE]) + RULES_END
    body = "\n".join(f"{KEYCAPS[i]} {t}" for i, t in enumerate(items))
    contact = "📩 للاستفسار أو الشحن: " if paid else "📩 للاستفسار: "
    return f"📜 قوانين بوت الوقت يم الاسم\n\n{body}\n\n{contact}@{OWNER_USERNAME}"

def rules_text():
    paid = get_setting("paid_on", "0") == "1"
    custom = get_setting("rules", "")
    if not custom:
        return build_rules(paid)
    if paid:
        custom += "\n\n⭐ قوانين الاشتراك:\n" + "\n".join("▫️ " + t for t in _rules_sub())
    else:
        custom += "\n\n🎁 " + FREE_RULE
    return custom

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("bot")

# ====================== قاعدة البيانات ======================
db = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
db.executescript(
    """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, username TEXT,
    joined TEXT, linked INTEGER DEFAULT 0, phone TEXT, banned INTEGER DEFAULT 0,
    entries INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chats(
    id INTEGER PRIMARY KEY, title TEXT, type TEXT);
CREATE TABLE IF NOT EXISTS fsub(
    chat_id INTEGER PRIMARY KEY, title TEXT, link TEXT);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS moderators(
    id INTEGER PRIMARY KEY, username TEXT, added_by INTEGER);
CREATE TABLE IF NOT EXISTS live(
    user_id INTEGER PRIMARY KEY, chat_id INTEGER, message_id INTEGER, view TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS sub_requests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT, ts INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS telethon_sessions(
    user_id INTEGER PRIMARY KEY, phone TEXT, session_string TEXT, created_at INTEGER);
"""
)
db.commit()

_existing_cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
for _col, _ddl in (
    ("entries", "INTEGER DEFAULT 0"),
    ("show_time", "INTEGER DEFAULT 0"),
    ("ampm", "INTEGER DEFAULT 1"),
    ("sub_until", "INTEGER DEFAULT 0"),
    ("kb_cleared", "INTEGER DEFAULT 0"),
    ("base_first", "TEXT DEFAULT ''"),
    ("base_last", "TEXT DEFAULT ''"),
):
    if _col not in _existing_cols:
        db.execute(f"ALTER TABLE users ADD COLUMN {_col} {_ddl}")
        db.commit()

def q_exec(sql, args=()):
    db.execute(sql, args)
    db.commit()

def q_all(sql, args=()):
    return db.execute(sql, args).fetchall()

def q_one(sql, args=()):
    return db.execute(sql, args).fetchone()

def get_setting(key, default=""):
    r = q_one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default

def set_setting(key, value):
    q_exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))

def is_admin(uid):
    return uid in ADMINS or q_one("SELECT id FROM moderators WHERE id=?", (uid,)) is not None

def add_moderator(uid, username="", added_by=OWNER_ID):
    q_exec("INSERT OR REPLACE INTO moderators(id,username,added_by) VALUES(?,?,?)",
           (uid, username.lstrip("@"), added_by))

for _rid in REMOVED_ADMINS:
    if get_setting(f"removed_admin:{_rid}", "") != "1":
        q_exec("DELETE FROM moderators WHERE id=?", (_rid,))
        set_setting(f"removed_admin:{_rid}", "1")

PLANS = {
    "w": ("أسبوع", 15, 7),
    "m": ("شهر", 40, 30),
    "q": ("3 أشهر", 60, 90),
}

def fmt_ts(ts):
    return datetime.fromtimestamp(ts, ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M")

def has_sub(uid):
    if get_setting("paid_on", "0") != "1" or is_admin(uid):
        return True
    row = q_one("SELECT sub_until FROM users WHERE id=?", (uid,))
    return bool(row and (row["sub_until"] or 0) > time.time())

def activate_sub(uid, plan):
    _name, _price, days = PLANS[plan]
    row = q_one("SELECT sub_until FROM users WHERE id=?", (uid,))
    base = max(int(time.time()), (row["sub_until"] or 0) if row else 0)
    until = base + days * 86400
    q_exec("UPDATE users SET sub_until=? WHERE id=?", (until, uid))
    q_exec("UPDATE sub_requests SET status='done' WHERE user_id=? AND status='pending'", (uid,))
    return until

def pending_plan(uid):
    r = q_one("SELECT plan FROM sub_requests WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid,))
    return r["plan"] if r else None

def pay_url(uid, plan=None):
    if plan in PLANS:
        n, p, _d = PLANS[plan]
        text = f"تم طلب اشتراك سعر {p} نجمة مدة {n}\nايدي العضو: {uid}"
    else:
        text = f"طلب شحن رصيد\nايدي العضو: {uid}"
    return f"https://t.me/{OWNER_USERNAME}?text={quote(text)}"

BLUE, GREEN, RED = "primary", "success", "danger"

EMOJI_KEYS = {
    "link": "حساباتي",
    "rules": "القوانين",
    "time": "الوقت",
    "dev": "المطور",
    "admin": "لوحة الأدمن",
}

def B(text, color=None, key=None, **kw):
    api = {}
    if color and get_setting("colors_on", "1") == "1":
        api["style"] = color
    if key:
        eid = get_setting(f"emoji:{key}", "")
        if eid:
            api["icon_custom_emoji_id"] = eid
    return Btn(text, api_kwargs=api or None, **kw)

DIGIT_STYLES = {
    "normal": ("0123456789", "12:30"),
    "arabic": ("٠١٢٣٤٥٦٧٨٩", "١٢:٣٠"),
    "bold": ("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗", "𝟏𝟐:𝟑𝟎"),
    "circle": ("⓪①②③④⑤⑥⑦⑧⑨", "①②:③⓪"),
    "dark": ("⓿❶❷❸❹❺❻❼❽❾", "❶❷:❸⓿"),
    "mono": ("𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿", "𝟷𝟸:𝟹𝟶"),
}

def deco(text):
    try:
        digits = DIGIT_STYLES.get(get_setting("digit_style", "bold"), DIGIT_STYLES["bold"])[0]
        return "".join(digits[int(ch)] if ch.isdigit() else ch for ch in text)
    except Exception:
        return text

def now_str(ampm=None):
    n = datetime.now(ZoneInfo(TIMEZONE))
    t = deco(f"{n.hour % 12 or 12}:{n.minute:02d}")
    if ampm is None:
        ampm = get_setting("ampm", "1") == "1"
    if ampm:
        t += " " + ("م" if n.hour >= 12 else "ص")
    return t

def date_str():
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

def time_greeting():
    h = datetime.now(ZoneInfo(TIMEZONE)).hour
    if 5 <= h < 12:
        return "🌞 صباح الخير"
    if 12 <= h < 17:
        return "🌤 طاب يومك"
    if 17 <= h < 21:
        return "🌆 مساء الخير"
    return "🌙 طاب مسائك"

def save_user(u):
    if q_one("SELECT id FROM users WHERE id=?", (u.id,)):
        q_exec("UPDATE users SET name=?, username=? WHERE id=?", (u.full_name, u.username, u.id))
        return False
    q_exec("INSERT INTO users(id,name,username,joined,entries) VALUES(?,?,?,?,0)",
           (u.id, u.full_name, u.username, f"{date_str()} {now_str()}"))
    return True

def record_entry(u):
    row = q_one("SELECT entries FROM users WHERE id=?", (u.id,))
    entries = (row["entries"] if row and row["entries"] else 0) + 1
    q_exec("UPDATE users SET entries=? WHERE id=?", (entries, u.id))
    return entries

async def notify(bot, text):
    cid = get_setting("notif_chat", "")
    if not cid:
        return
    try:
        await bot.send_message(int(cid), text, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        log.warning("notify failed: %s", e)

def user_link(u):
    return f'<a href="tg://user?id={u.id}">{html.escape(u.full_name)}</a>'

async def sub_status_rows(bot, uid):
    out = []
    for ch in q_all("SELECT * FROM fsub"):
        try:
            m = await bot.get_chat_member(ch["chat_id"], uid)
            ok = m.status not in ("left", "kicked")
        except TelegramError:
            ok = False
        out.append((ch, ok))
    return out

def main_kb(is_adm=False, uid=None):
    paid = get_setting("paid_on", "0") == "1"
    rows = [
        [B("حساباتي", GREEN, "link", callback_data="accounts")],
        [B("القوانين", BLUE, "rules", callback_data="rules"), B("الوقت", BLUE, "time", callback_data="time")],
    ]
    if paid:
        rows.append([B("💳 شحن رصيد", BLUE, callback_data="sub")])
        if uid:
            rows.append([B("المطور (للشحن)", GREEN, "dev", url=pay_url(uid, pending_plan(uid)))])
        else:
            rows.append([B("المطور", GREEN, "dev", url=DEV_LINK)])
    else:
        rows.append([B("المطور", GREEN, "dev", url=DEV_LINK)])
    if is_adm:
        rows.append([B("لوحة الأدمن", GREEN, "admin", callback_data="adm:main")])
    return Markup(rows)

def back_kb():
    return Markup([[Btn("🔙 رجوع", callback_data="home")]])

def header(user):
    name = f"👤 <b>{html.escape(user.full_name)}</b>"
    row = q_one("SELECT show_time, ampm FROM users WHERE id=?", (user.id,))
    if row and row["show_time"] and has_sub(user.id):
        return f"{name}  |  🕒 <b>{now_str(row['ampm'] != 0)}</b>"
    return name

def sub_line(uid):
    if get_setting("paid_on", "0") != "1":
        return "🎁 هذا بوت <b>مجاني بالكامل</b>، بدون أي اشتراك مدفوع.\n"
    if is_admin(uid):
        return "👑 حالتك: <b>أدمن</b> — بدون قيود.\n"
    row = q_one("SELECT sub_until FROM users WHERE id=?", (uid,))
    until = (row["sub_until"] or 0) if row else 0
    if until > time.time():
        return f"⭐ حالتك: <b>مشترك ✅</b>\n📆 ينتهي: <b>{fmt_ts(until)}</b>\n"
    return "⭐ حالتك: <b>غير مشترك ❌</b>\n🔒 الوقت وربط الحسابات للمشتركين فقط، اضغط 💳 شحن رصيد.\n"

SUB_CACHE = {}

async def home_text(user, bot, use_cache=False):
    if use_cache and user.id in SUB_CACHE:
        sub_block = SUB_CACHE[user.id]
    else:
        status_rows = await sub_status_rows(bot, user.id)
        sub_block = ""
        if status_rows:
            lines = "\n".join(f"{'✅' if ok else '❌'} {html.escape(ch['title'])}" for ch, ok in status_rows)
            sub_block = f"\n\n🔐 <b>حالة الاشتراك:</b>\n{lines}"
        SUB_CACHE[user.id] = sub_block
    free_line = sub_line(user.id)
    return (
        f"{header(user)}\n"
        f"📅 {date_str()}\n"
        f"{time_greeting()} يا {html.escape(user.first_name)} 👋\n\n"
        f"{free_line}"
        "اختار من الأزرار تحت 👇"
        f"{sub_block}\n\n"
        f'👨‍💻 المطور: <a href="{DEV_LINK}">اضغط هنا</a>\n'
        f'📣 القناة: <a href="{CHANNEL_LINK}">اضغط هنا</a>'
    )

def time_screen(user):
    r = q_one("SELECT show_time, ampm FROM users WHERE id=?", (user.id,))
    if r and r["show_time"]:
        on = (r["ampm"] if r["ampm"] is not None else 1) != 0
        text = f"{header(user)}\n📅 {date_str()}\n\n✅ الوقت مفعّل يم اسمك ويتحدث وحده كل دقيقة.\n🌗 م/ص: <b>{'ظاهر' if on else 'مخفي'}</b>"
        kb = Markup([
            [B("⏭ تخطي م/ص" if on else "🌗 إظهار م/ص", BLUE, callback_data="time_ampm")],
            [B("🗑 حذف الوقت", RED, callback_data="time_off")],
            [B("🔙 رجوع", None, callback_data="home")],
        ])
    else:
        text = f"{header(user)}\n📅 {date_str()}\n\n🕒 اختار حتى يظهر الوقت يم اسمك:"
        kb = Markup([
            [B("🌗 مع م/ص", GREEN, callback_data="time_on:1"), B("⏭ تخطي م/ص", BLUE, callback_data="time_on:0")],
            [B("🔙 رجوع", None, callback_data="home")]
        ])
    return text, kb

def sub_screen(user):
    row = q_one("SELECT sub_until FROM users WHERE id=?", (user.id,))
    until = (row["sub_until"] or 0) if row else 0
    if is_admin(user.id):
        status = "👑 انت مشرف، ما تحتاج اشتراك.\n\n"
    elif until > time.time():
        status = f"✅ اشتراكك فعّال لين <b>{fmt_ts(until)}</b>\n\n"
    else:
        status = "🔒 هذه الميزة للمشتركين فقط.\n\n"
    prices = "\n".join(f"▫️ {n} — <b>{p}</b> نجمة" for n, p, _d in PLANS.values())
    text = f"{header(user)}\n\n{status}⭐ <b>أسعار الاشتراك:</b>\n{prices}\n\nاختار الاشتراك اللي تريده 👇"
    rows = [[B(f"⭐ {n} — {p} نجمة", GREEN, callback_data=f"sub_req:{k}")] for k, (n, p, _d) in PLANS.items()]
    rows.append([B("🔙 رجوع", None, callback_data="home")])
    return text, Markup(rows)


# ====================== تحديث اسم الحساب المربوط ======================
TG_CLIENTS = {}
NAME_SEP = " | "

async def get_userbot(uid):
    c = TG_CLIENTS.get(uid)
    if c is not None and c.is_connected():
        return c
    c = TelegramClient(f"session_{uid}", API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        return None
    TG_CLIENTS[uid] = c
    return c

async def drop_userbot(uid):
    c = TG_CLIENTS.pop(uid, None)
    if c is not None:
        try:
            await c.disconnect()
        except Exception:
            pass

def build_name(base_first, ampm):
    suffix = f"{NAME_SEP}{now_str(ampm)}"
    return (base_first or "")[:40] + suffix

async def ensure_base_name(uid):
    """يحفظ الاسم الأصلي للحساب (قبل إضافة الوقت) مرة وحدة."""
    r = q_one("SELECT base_first, base_last FROM users WHERE id=?", (uid,))
    if r and r["base_first"]:
        return r["base_first"], r["base_last"] or ""
    c = await get_userbot(uid)
    if c is None:
        return None
    me = await c.get_me()
    first = me.first_name or ""
    last = me.last_name or ""
    # لو الاسم أصلاً فيه وقت من تشغيل سابق، نشيله
    if NAME_SEP in first:
        first = first.split(NAME_SEP)[0]
    q_exec("UPDATE users SET base_first=?, base_last=? WHERE id=?", (first, last, uid))
    return first, last

_LAST_NAME = {}

async def apply_name(uid, ampm=None):
    base = await ensure_base_name(uid)
    if base is None:
        return False
    if ampm is None:
        r = q_one("SELECT ampm FROM users WHERE id=?", (uid,))
        ampm = (r["ampm"] != 0) if r else True
    c = await get_userbot(uid)
    if c is None:
        return False
    new_first = build_name(base[0], ampm)
    if _LAST_NAME.get(uid) == new_first:
        return True
    try:
        await c(UpdateProfileRequest(first_name=new_first, last_name=base[1]))
    except FloodWaitError as e:
        # إذا الانتظار قصير ننتظر ونعيد المحاولة بالوقت الحالي
        if e.seconds <= 20:
            await asyncio.sleep(e.seconds + 1)
            new_first = build_name(base[0], ampm)
            await c(UpdateProfileRequest(first_name=new_first, last_name=base[1]))
        else:
            raise
    _LAST_NAME[uid] = new_first
    return True

async def restore_name(uid):
    r = q_one("SELECT base_first, base_last FROM users WHERE id=?", (uid,))
    if not r or not r["base_first"]:
        return
    try:
        c = await get_userbot(uid)
        if c is not None:
            await c(UpdateProfileRequest(first_name=r["base_first"], last_name=r["base_last"] or ""))
    except Exception as e:
        log.warning("restore name failed for %s: %s", uid, e)
    q_exec("UPDATE users SET base_first='', base_last='' WHERE id=?", (uid,))

_BAD_SESSION = (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, UserDeactivatedBanError)

async def _name_one(uid, ampm, base_first, sem):
    async with sem:
        if not has_sub(uid):
            if base_first:
                await restore_name(uid)
            return
        try:
            ok = await apply_name(uid, ampm != 0)
            if not ok:
                q_exec("UPDATE users SET linked=0, show_time=0 WHERE id=?", (uid,))
        except FloodWaitError as e:
            log.warning("name flood wait %s: %ss", uid, e.seconds)
        except _BAD_SESSION:
            await drop_userbot(uid)
            q_exec("UPDATE users SET linked=0, show_time=0 WHERE id=?", (uid,))
        except Exception as e:
            log.warning("name update failed for %s: %s", uid, e)

async def name_tick():
    rows = q_all("SELECT id, ampm, base_first FROM users WHERE show_time=1 AND linked=1 AND banned=0")
    sem = asyncio.Semaphore(10)
    await asyncio.gather(*(_name_one(r["id"], r["ampm"], r["base_first"], sem) for r in rows))

LIVE_TTL = 3600

def set_live(uid, chat_id, message_id, view):
    q_exec("INSERT OR REPLACE INTO live(user_id,chat_id,message_id,view,ts) VALUES(?,?,?,?,?)",
           (uid, chat_id, message_id, view, int(time.time())))

def clear_live(uid):
    q_exec("DELETE FROM live WHERE user_id=?", (uid,))

async def live_tick(bot):
    q_exec("DELETE FROM live WHERE ts < ?", (int(time.time()) - LIVE_TTL,))
    rows = q_all("SELECT l.user_id, l.chat_id, l.message_id, l.view, u.name FROM live l JOIN users u ON u.id=l.user_id WHERE u.show_time=1")
    for r in rows:
        name = r["name"] or ""
        u = SimpleNamespace(id=r["user_id"], full_name=name, first_name=(name.split() or [""])[0])
        try:
            if r["view"] == "home":
                text = await home_text(u, bot, use_cache=True)
                kb = main_kb(is_admin(u.id), u.id)
            else:
                text, kb = time_screen(u)
            await bot.edit_message_text(text, chat_id=r["chat_id"], message_id=r["message_id"], parse_mode=ParseMode.HTML, reply_markup=kb)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                clear_live(u.id)
        except TelegramError:
            clear_live(u.id)
        await asyncio.sleep(0.05)

async def live_loop(app):
    while True:
        n = datetime.now(ZoneInfo(TIMEZONE))
        # ننتظر لبداية الدقيقة الجاية بالضبط (مع احتساب الأجزاء من الثانية)
        await asyncio.sleep(60 - n.second - n.microsecond / 1e6 + 0.3)
        # الاسم أولاً وبمهمة مستقلة حتى ما يتأخر بسبب تحديث رسائل البوت
        asyncio.create_task(_safe(name_tick(), "name tick failed"))
        asyncio.create_task(_safe(live_tick(app.bot), "live tick failed"))

async def _safe(coro, msg):
    try:
        await coro
    except Exception:
        log.exception(msg)

async def post_init(app):
    app.bot_data["live_task"] = asyncio.create_task(live_loop(app))

def admin_kb():
    on = get_setting("bot_on", "1") == "1"
    colors = get_setting("colors_on", "1") == "1"
    paid = get_setting("paid_on", "0") == "1"
    sub_rows = [[B("💳 شحن رصيد", GREEN, callback_data="adm:recharge"), B("📋 طلبات الاشتراك", BLUE, callback_data="adm:sub_reqs")]] if paid else []
    return Markup([
        [B("📊 إحصائيات البوت", GREEN, callback_data="adm:stats")],
        [B("➕ إضافة مشرف", BLUE, callback_data="adm:mod_add")],
        [B("🔐 الاشتراك الإجباري", BLUE, callback_data="adm:fsub")],
        [B("📢 إذاعة", GREEN, callback_data="adm:bc")],
        [B("✏️ تعديل القوانين", BLUE, callback_data="adm:rules")],
        [B("🕒 إعدادات الوقت", BLUE, callback_data="adm:time")],
        [B("🔔 قناة الإشعارات", BLUE, callback_data="adm:notif")],
        [B("🖼 الملصق الترحيبي", BLUE, callback_data="adm:sticker")],
        [B("✨ إيموجي مميز للأزرار", GREEN, callback_data="adm:emoji")],
        [B("⭐ الاشتراكات المدفوعة: " + ("شغالة (اضغط للإيقاف)" if paid else "مطفية (اضغط للتفعيل)"), RED if paid else GREEN, callback_data="adm:paid")],
        *sub_rows,
        [B("🎨 ألوان الأزرار: " + ("شغالة (اضغط للإطفاء)" if colors else "مطفية (اضغط للتشغيل)"), RED if colors else GREEN, callback_data="adm:colors")],
        [B("🚫 حظر عضو", RED, callback_data="adm:ban"), B("✅ فك حظر", GREEN, callback_data="adm:unban")],
        [B(("🟢 البوت شغال" if on else "🔴 البوت متوقف") + " (تبديل)", GREEN if on else RED, callback_data="adm:toggle")],
        [B("❌ إغلاق", RED, callback_data="adm:close")],
    ])

def adm_back():
    return Markup([[Btn("🔙 لوحة الأدمن", callback_data="adm:main")]])

def stats_text():
    users = q_one("SELECT COUNT(*) c FROM users")["c"]
    linked = q_one("SELECT COUNT(*) c FROM users WHERE linked=1")["c"]
    banned = q_one("SELECT COUNT(*) c FROM users WHERE banned=1")["c"]
    groups = q_one("SELECT COUNT(*) c FROM chats WHERE type IN ('group','supergroup')")["c"]
    chans = q_one("SELECT COUNT(*) c FROM chats WHERE type='channel'")["c"]
    fs = q_one("SELECT COUNT(*) c FROM fsub")["c"]
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 عدد الأعضاء: <b>{users}</b>\n"
        f"🔗 الحسابات المربوطة: <b>{linked}</b>\n"
        f"🚫 المحظورين: <b>{banned}</b>\n"
        f"👨‍👩‍👧 الكروبات: <b>{groups}</b>\n"
        f"📣 القنوات: <b>{chans}</b>\n"
        f"🔐 قنوات الاشتراك الإجباري: <b>{fs}</b>"
    )

async def not_subscribed(bot, uid):
    status_rows = await sub_status_rows(bot, uid)
    return [ch for ch, ok in status_rows if not ok]

async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if is_admin(user.id):
        return True
    row = q_one("SELECT banned FROM users WHERE id=?", (user.id,))
    send = update.effective_message.reply_text
    if row and row["banned"]:
        await send("🚫 انت محظور من استخدام البوت.")
        return False
    if get_setting("bot_on", "1") != "1":
        await send("🔴 البوت متوقف مؤقتاً، حاول لاحقاً.")
        return False
    status_rows = await sub_status_rows(context.bot, user.id)
    missing = [ch for ch, ok in status_rows if not ok]
    if missing:
        rows = []
        for ch, ok in status_rows:
            if ok:
                rows.append([Btn(f"✅ {ch['title']}", callback_data="noop")])
            elif ch["link"]:
                rows.append([Btn(f"📣 {ch['title']}", url=ch["link"])])
        rows.append([Btn("✅ تحققت من الاشتراك", callback_data="check_sub")])
        await send("🔐 <b>لازم تشترك بالقنوات التالية حتى تستخدم البوت:</b>", parse_mode=ParseMode.HTML, reply_markup=Markup(rows))
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    user = update.effective_user
    is_new = save_user(user)
    entry_no = record_entry(user)
    total = q_one("SELECT COUNT(*) c FROM users")["c"]
    title = "عضو جديد دخل بوتك، يگلبي" if is_new else "عضو دخل بوتك مرة ثانية، يگلبي"
    await notify(context.bot, (
        f"👤 <b>{title}</b>\n\n"
        f"👤 اسم العضو: {user_link(user)}\n"
        f"🆔 ايدي العضو: <code>{user.id}</code>\n"
        f"🔗 يوزر العضو: {'@' + user.username if user.username else 'لا يوجد'}\n"
        f"🔢 رقم عدد الدخول للبوت: <b>{entry_no}</b>"
    ))
    if not await gate(update, context):
        return
    sticker_id = get_setting("welcome_sticker", "")
    if sticker_id:
        try:
            await context.bot.send_sticker(user.id, sticker_id)
        except TelegramError as e:
            log.warning("send welcome sticker failed: %s", e)
    sent = await update.message.reply_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
    set_live(user.id, sent.chat_id, sent.message_id, "home")

async def user_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data
    save_user(user)

    if data == "cancel_link":
        client = context.user_data.pop("tg_client", None)
        if client:
            try:
                await client.disconnect()
            except:
                pass
        context.user_data.pop("state", None)
        context.user_data.pop("pending_phone", None)
        await q.answer("❌ تم إلغاء العملية")
        await q.edit_message_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
        set_live(user.id, q.message.chat_id, q.message.message_id, "home")
        return

    if data == "resend_code":
        phone = context.user_data.get("pending_phone")
        client = context.user_data.get("tg_client")
        if not phone or not client:
            await q.answer("⚠️ انتهت الجلسة، أرسل /start وحاول من جديد.", show_alert=True)
            return
        try:
            await client.send_code_request(phone)
            await q.answer("🔄 تم إعادة إرسال الكود بنجاح، تفقده الآن.", show_alert=True)
        except FloodWaitError as e:
            await q.answer(f"⚠️ محاولات كثيرة، انتظر {e.seconds} ثانية.", show_alert=True)
        except Exception as e:
            await q.answer(f"❌ خطأ: {e}", show_alert=True)
        return

    if data == "check_sub":
        if await not_subscribed(context.bot, user.id) and not is_admin(user.id):
            await q.answer("⚠️ ما اشتركت بكل القنوات بعد!", show_alert=True)
            return
        await q.answer("✅ تم التحقق")
        await q.edit_message_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
        set_live(user.id, q.message.chat_id, q.message.message_id, "home")
        return

    if data == "noop":
        await q.answer("✅ انت مشترك بهذه القناة")
        return

    row = q_one("SELECT banned FROM users WHERE id=?", (user.id,))
    if not is_admin(user.id):
        if row and row["banned"]:
            await q.answer("🚫 انت محظور", show_alert=True)
            return
        if get_setting("bot_on", "1") != "1":
            await q.answer("🔴 البوت متوقف مؤقتاً", show_alert=True)
            return
        if await not_subscribed(context.bot, user.id):
            await q.answer("🔐 اشترك بالقنوات أول، أرسل /start", show_alert=True)
            return

    clear_live(user.id)

    if data in ("time", "time_on:1", "time_on:0"):
        r = q_one("SELECT linked FROM users WHERE id=?", (user.id,))
        if not r or not r["linked"]:
            await q.answer("⚠️ يرجى ربط حسابك أولاً!", show_alert=True)
            text = f"{header(user)}\n\n👥 <b>حساباتي</b>\n\nما عندك حساب مربوط."
            kb = Markup([[B("🔗 ربط حساب", GREEN, callback_data="link")], [B("🔙 رجوع", None, callback_data="home")]])
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

    if (data in ("time", "accounts", "link", "time_ampm") or data.startswith("time_on:")) and not has_sub(user.id):
        await q.answer()
        text, kb = sub_screen(user)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "home":
        await q.answer()
        await q.edit_message_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
        set_live(user.id, q.message.chat_id, q.message.message_id, "home")

    elif data == "time_ampm":
        r = q_one("SELECT show_time, ampm FROM users WHERE id=?", (user.id,))
        if not r or not r["show_time"]:
            await q.answer("⚠️ فعّل الوقت أول", show_alert=True)
            return
        new = 0 if (r["ampm"] if r["ampm"] is not None else 1) != 0 else 1
        q_exec("UPDATE users SET ampm=? WHERE id=?", (new, user.id))
        try:
            await apply_name(user.id, bool(new))
            await q.answer("✅ م/ص ظاهر" if new else "⏭ تم تخطي م/ص")
        except Exception as e:
            log.warning("apply name failed: %s", e)
            await q.answer("⚠️ تغيّر الخيار بس ما گدرت أحدّث اسم الحساب.", show_alert=True)
        text, kb = time_screen(user)
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except BadRequest:
            pass

    elif data in ("time", "time_on:1", "time_on:0", "time_off"):
        if data.startswith("time_on:"):
            q_exec("UPDATE users SET show_time=1, ampm=? WHERE id=?", (int(data[-1]), user.id))
            try:
                await apply_name(user.id, data[-1] == "1")
                await q.answer("✅ تم تفعيل الوقت يم اسم حسابك")
            except Exception as e:
                log.warning("apply name failed: %s", e)
                await q.answer("⚠️ تفعّل الوقت، بس ما گدرت أغيّر اسم الحساب. أعد ربط الحساب.", show_alert=True)
        elif data == "time_off":
            q_exec("UPDATE users SET show_time=0 WHERE id=?", (user.id,))
            await restore_name(user.id)
            await q.answer("🗑 تم حذف الوقت ورجوع اسمك الأصلي")
        else:
            await q.answer()
        
        # هنا التحديث الأهم: بعد التفعيل أو الحذف، نرجع للواجهة الرئيسية
        # ونقوم بتحديث الرسالة فوراً لكي يظهر الوقت في الهيدر
        if data in ("time_on:1", "time_on:0", "time_off"):
            await q.edit_message_text(
                await home_text(user, context.bot), 
                parse_mode=ParseMode.HTML, 
                reply_markup=main_kb(is_admin(user.id), user.id)
            )
            # تثبيت الرسالة الحالية لتحديثها تلقائياً كل دقيقة
            set_live(user.id, q.message.chat_id, q.message.message_id, "home")
        else:
            text, kb = time_screen(user)
            try:
                await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except BadRequest:
                pass

    elif data == "rules":
        await q.answer()
        rules = rules_text()
        await q.edit_message_text(f"{header(user)}\n\n{html.escape(rules)}", parse_mode=ParseMode.HTML, reply_markup=back_kb())

    elif data == "sub":
        await q.answer()
        if get_setting("paid_on", "0") != "1":
            text, kb = f"{header(user)}\n\nالاشتراكات غير مفعّلة حالياً، البوت مجاني 🎁", back_kb()
        else:
            text, kb = sub_screen(user)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data.startswith("sub_req:"):
        plan = data.split(":")[1]
        if plan not in PLANS or get_setting("paid_on", "0") != "1":
            await q.answer("⚠️ غير متاح حالياً", show_alert=True)
            return
        await q.answer()
        n, p, _d = PLANS[plan]
        q_exec("UPDATE sub_requests SET status='replaced' WHERE user_id=? AND status='pending'", (user.id,))
        q_exec("INSERT INTO sub_requests(user_id,plan,ts,status) VALUES(?,?,?,'pending')", (user.id, plan, int(time.time())))
        try:
            await context.bot.send_message(OWNER_ID, f"🔔 <b>تم طلب اشتراك جديد</b>\n\nالعضو: {user_link(user)}\nاليوزر: @{user.username or 'لا يوجد'}\nالايدي: <code>{user.id}</code>\nالخطة: <b>{n}</b> — <b>{p}</b> نجمة\n\nإذا وصلتك النجوم فعّل الاشتراك 👇", parse_mode=ParseMode.HTML, reply_markup=Markup([[B("✅ تفعيل الاشتراك", GREEN, callback_data=f"adm:sub_do:{user.id}:{plan}")], [B("❌ رفض", RED, callback_data=f"adm:sub_rej:{user.id}")]]))
        except TelegramError as e:
            log.warning("notify owner failed: %s", e)
        await q.edit_message_text(f"{header(user)}\n\n✅ <b>تم تسجيل طلب اشتراك</b>\n⭐ {n} — <b>{p}</b> نجمة\n🆔 ايديك: <code>{user.id}</code>\n\n⚠️ <b>يجب عليك مراسلة المالك وإرسال النجوم</b> حتى يتم تفعيل اشتراكك.", parse_mode=ParseMode.HTML, reply_markup=Markup([[B("👨‍💻 مراسلة المالك للشحن", GREEN, url=pay_url(user.id, plan))], [B("🔙 رجوع", None, callback_data="home")]]))

    elif data == "accounts":
        await q.answer()
        r = q_one("SELECT linked, phone FROM users WHERE id=?", (user.id,))
        if r and r["linked"]:
            text = f"{header(user)}\n\n👥 <b>حساباتي</b>\n\n1️⃣ {html.escape(user.full_name)}\n📱 <code>{html.escape(r['phone'] or '-')}</code>"
            kb = Markup([[B("🗑 تنزيل حسابي", RED, callback_data="unlink_ask")], [B("🔙 رجوع", None, callback_data="home")]])
        else:
            text = f"{header(user)}\n\n👥 <b>حساباتي</b>\n\nما عندك حساب مربوط."
            kb = Markup([[B("🔗 ربط حساب", GREEN, callback_data="link")], [B("🔙 رجوع", None, callback_data="home")]])
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "unlink_ask":
        await q.answer()
        kb = Markup([[B("✅ نعم، نزّل حسابي", RED, callback_data="unlink_yes"), B("❌ لا", GREEN, callback_data="accounts")]])
        await q.edit_message_text(f"{header(user)}\n\n⚠️ متأكد تريد تنزيل حسابك من حساباتي؟", parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "unlink_yes":
        await q.answer("🗑 تم تنزيل الحساب")
        await restore_name(user.id)
        c = TG_CLIENTS.pop(user.id, None)
        if c is not None:
            try:
                await c.log_out()
            except Exception:
                try:
                    await c.disconnect()
                except Exception:
                    pass
        q_exec("UPDATE users SET linked=0, phone=NULL, show_time=0 WHERE id=?", (user.id,))
        q_exec("DELETE FROM telethon_sessions WHERE user_id=?", (user.id,))
        await notify(context.bot, f"🗑 <b>تم تنزيل حساب</b>\n\nالعضو: {user_link(user)}\nالايدي: <code>{user.id}</code>")
        await q.edit_message_text(f"{header(user)}\n\n✅ تم تنزيل حسابك من حساباتي.", parse_mode=ParseMode.HTML, reply_markup=Markup([[B("🔗 ربط حساب", GREEN, callback_data="link")], [B("🔙 رجوع", None, callback_data="home")]]))

    elif data == "link":
        await q.answer()
        r = q_one("SELECT linked, phone FROM users WHERE id=?", (user.id,))
        if r and r["linked"]:
            await q.edit_message_text(f"{header(user)}\n\n✅ حسابك مربوط مسبقاً.\n📱 الرقم: <code>{html.escape(r['phone'] or '-')}</code>", parse_mode=ParseMode.HTML, reply_markup=back_kb())
            return
        context.user_data["state"] = "link_phone"
        context.user_data.pop("pending_phone", None)
        context.user_data.pop("tg_client", None)
        
        kb = Markup([[B("🔙 إلغاء", RED, callback_data="cancel_link")]])
        await q.edit_message_text(f"{header(user)}\n\n🔗 <b>ربط حساب</b>\n\nأرسل رقمك مع رمز الدولة بهذه الصيغة:\n<code>+9647xxxxxxxx</code>", parse_mode=ParseMode.HTML, reply_markup=kb)

# ====================== لوحة الأدمن ======================
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE or not is_admin(update.effective_user.id):
        return
    context.user_data.pop("state", None)
    await update.message.reply_text("👑 <b>لوحة تحكم الأدمن</b>\n🎨 الألوان: 🟢 إيجابي / 🔵 إعدادات / 🔴 حساس", parse_mode=ParseMode.HTML, reply_markup=admin_kb())

def fsub_kb():
    rows = []
    for c in q_all("SELECT * FROM fsub"):
        rows.append([Btn(f"🗑 حذف: {c['title']}", callback_data=f"adm:fsub_del:{c['chat_id']}")])
    rows.append([Btn("➕ إضافة قناة", callback_data="adm:fsub_add")])
    rows.append([Btn("🔙 لوحة الأدمن", callback_data="adm:main")])
    return Markup(rows)

def time_settings_text():
    st = get_setting("digit_style", "bold")
    ap = get_setting("ampm", "1") == "1"
    return f"🕒 <b>إعدادات الوقت</b>\n\nالمعاينة: <b>{now_str()}</b>\nم / ص: <b>{'ظاهر ✅' if ap else 'متخطى ⏭'}</b>\nزخرفة الأرقام: <b>{st}</b>"

def time_settings_kb():
    cur = get_setting("digit_style", "bold")
    ap = get_setting("ampm", "1") == "1"
    rows = [[Btn("⏭ تخطي م/ص" if ap else "✅ إظهار م/ص", callback_data="adm:ampm")]]
    items = list(DIGIT_STYLES.items())
    for i in range(0, len(items), 2):
        rows.append([Btn(("✔️ " if k == cur else "") + v[1], callback_data=f"adm:style:{k}") for k, v in items[i : i + 2]])
    rows.append([Btn("🔙 لوحة الأدمن", callback_data="adm:main")])
    return Markup(rows)

def notif_text():
    cid = get_setting("notif_chat", "")
    if cid:
        return f"🔔 <b>قناة الإشعارات</b>\n\n✅ مربوطة\nالايدي: <code>{cid}</code>\n\nتصلها إشعارات: دخول عضو جديد، ربط حساب."
    return "🔔 <b>قناة الإشعارات</b>\n\n❌ غير مربوطة."

def notif_kb():
    rows = [[Btn("🔗 ربط / تغيير القناة", callback_data="adm:notif_set")]]
    if get_setting("notif_chat", ""):
        rows.append([Btn("📨 اختبار", callback_data="adm:notif_test"), Btn("🗑 فك الربط", callback_data="adm:notif_off")])
    rows.append([Btn("🔙 لوحة الأدمن", callback_data="adm:main")])
    return Markup(rows)

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ للأدمن فقط", show_alert=True)
        return
    data = q.data[4:]
    context.user_data.pop("state", None)
    OWNER_ONLY = ("mod_add", "recharge", "sub_reqs", "sub_do:", "sub_rej:")
    if q.from_user.id != OWNER_ID and any(data == k or (k.endswith(":") and data.startswith(k)) for k in OWNER_ONLY):
        await q.answer(f"هذه الخاصية للمالك فقط\nايديك: {q.from_user.id}", show_alert=True)
        return
    await q.answer()

    async def show(text, kb):
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except BadRequest:
            pass

    if data == "main":
        await show("👑 <b>لوحة تحكم الأدمن</b>", admin_kb())
    elif data == "close":
        await q.message.delete()
    elif data == "stats":
        await show(stats_text(), adm_back())
    elif data == "mod_add":
        if q.from_user.id != OWNER_ID:
            return
        context.user_data["state"] = "mod_add"
        await show("➕ أرسل آيدي العضو أو يوزره (@username).", adm_back())
    elif data == "toggle":
        set_setting("bot_on", "0" if get_setting("bot_on", "1") == "1" else "1")
        await show("👑 <b>لوحة تحكم الأدمن</b>", admin_kb())
    elif data == "colors":
        set_setting("colors_on", "0" if get_setting("colors_on", "1") == "1" else "1")
        await show("👑 <b>لوحة تحكم الأدمن</b>", admin_kb())
    elif data == "paid":
        set_setting("paid_on", "0" if get_setting("paid_on", "0") == "1" else "1")
        await show("👑 <b>لوحة تحكم الأدمن</b>", admin_kb())
    elif data == "recharge":
        if q.from_user.id != OWNER_ID:
            return
        if get_setting("paid_on", "0") != "1":
            await show("⚠️ فعّل الاشتراكات المدفوعة أول.", adm_back())
            return
        context.user_data["state"] = "recharge"
        await show("💳 <b>شحن رصيد</b>\n\n📩 أرسل ايدي العضو (أرقام فقط):", adm_back())
    elif data == "sub_reqs":
        if q.from_user.id != OWNER_ID:
            return
        reqs = q_all("SELECT user_id, plan FROM sub_requests WHERE status='pending' ORDER BY id DESC LIMIT 10")
        rows = []
        lines = []
        for r in reqs:
            if r["plan"] not in PLANS:
                continue
            n, p, _d = PLANS[r["plan"]]
            lines.append(f"▫️ <code>{r['user_id']}</code> — {n} ({p} نجمة)")
            rows.append([B(f"✅ تفعيل {r['user_id']} — {n}", GREEN, callback_data=f"adm:sub_do:{r['user_id']}:{r['plan']}")])
        rows.append([B("🔙 لوحة الأدمن", None, callback_data="adm:main")])
        body = "\n".join(lines) if lines else "ما فيه طلبات معلّقة."
        await show(f"📋 <b>طلبات الاشتراك</b>\n\n{body}", Markup(rows))
    elif data.startswith("sub_do:"):
        if q.from_user.id != OWNER_ID:
            return
        _, uid_s, plan = data.split(":")
        uid = int(uid_s)
        if plan not in PLANS or not q_one("SELECT id FROM users WHERE id=?", (uid,)):
            await show("⚠️ العضو أو الخطة غير موجودة.", adm_back())
            return
        n, p, _d = PLANS[plan]
        until = activate_sub(uid, plan)
        try:
            await context.bot.send_message(uid, f"✅ <b>تم تفعيل اشتراكك</b>\n⭐ {n}\n📅 لين: <b>{fmt_ts(until)}</b>\n\nتقدر تستخدم الوقت وحساباتي الحين 🎉", parse_mode=ParseMode.HTML)
        except TelegramError as e:
            log.warning("notify sub user failed: %s", e)
        await show(f"✅ تم تفعيل اشتراك ({n}) للعضو <code>{uid}</code>\n📅 لين: <b>{fmt_ts(until)}</b>", adm_back())
    elif data.startswith("sub_rej:"):
        if q.from_user.id != OWNER_ID:
            return
        uid = int(data.split(":")[1])
        q_exec("UPDATE sub_requests SET status='rejected' WHERE user_id=? AND status='pending'", (uid,))
        await show(f"❌ تم رفض طلب العضو <code>{uid}</code>.", adm_back())
    elif data == "emoji":
        rows = []
        for k, name in EMOJI_KEYS.items():
            mark = "✅" if get_setting(f"emoji:{k}", "") else "➖"
            rows.append([B(f"{mark} {name}", BLUE, callback_data=f"adm:emoji_pick:{k}")])
        rows.append([B("🔙 لوحة الأدمن", None, callback_data="adm:main")])
        await show("✨ <b>إيموجي مميز للأزرار</b>\nاختار الزر اللي تريد تحط عليه إيموجي مميز:", Markup(rows))
    elif data.startswith("emoji_pick:"):
        k = data.split(":")[1]
        context.user_data["state"] = f"emoji_set:{k}"
        rows = [[B("🗑 حذف الإيموجي", RED, callback_data=f"adm:emoji_del:{k}")], [B("🔙 رجوع", None, callback_data="adm:emoji")]]
        await show(f"📩 أرسل <b>ستيكر إيموجي مميز</b> أو رسالة فيها إيموجي مميز للزر: <b>{EMOJI_KEYS.get(k, k)}</b>", Markup(rows))
    elif data.startswith("emoji_del:"):
        k = data.split(":")[1]
        set_setting(f"emoji:{k}", "")
        await show("✅ تم حذف الإيموجي من الزر.", adm_back())
    elif data == "time":
        await show(time_settings_text(), time_settings_kb())
    elif data == "ampm":
        set_setting("ampm", "0" if get_setting("ampm", "1") == "1" else "1")
        await show(time_settings_text(), time_settings_kb())
    elif data.startswith("style:"):
        set_setting("digit_style", data.split(":")[1])
        await show(time_settings_text(), time_settings_kb())
    elif data == "notif":
        await show(notif_text(), notif_kb())
    elif data == "notif_set":
        context.user_data["state"] = "notif_set"
        await show("🔔 أرسل يوزر القناة (@channel) أو ايديها (-100...)\n⚠️ لازم البوت يكون أدمن بالقناة.", adm_back())
    elif data == "notif_off":
        set_setting("notif_chat", "")
        await show(notif_text(), notif_kb())
    elif data == "notif_test":
        await notify(context.bot, "✅ <b>اختبار الإشعارات</b>\nالقناة مربوطة بنجاح 🔔")
        await show(notif_text() + "\n\n📨 تم إرسال رسالة اختبار.", notif_kb())
    elif data == "sticker":
        cur = get_setting("welcome_sticker", "")
        rows = [[Btn("🟢 تغيير / تعيين الملصق", callback_data="adm:sticker_set")]]
        if cur:
            rows.append([Btn("🔴 حذف الملصق", callback_data="adm:sticker_del")])
        rows.append([Btn("🔙 لوحة الأدمن", callback_data="adm:main")])
        text = "🖼 <b>الملصق الترحيبي</b>\n\n" + ("✅ فيه ملصق محدد حالياً." if cur else "❌ ما فيه ملصق محدد حالياً.")
        await show(text, Markup(rows))
    elif data == "sticker_set":
        context.user_data["state"] = "set_sticker"
        await show("📩 أرسل الملصق (الستيكر) اللي تريد يترسل مع رسالة الترحيب:", adm_back())
    elif data == "sticker_del":
        set_setting("welcome_sticker", "")
        await show("✅ تم حذف الملصق.", adm_back())
    elif data == "rules":
        context.user_data["state"] = "edit_rules"
        cur = html.escape(get_setting("rules", "") or build_rules(False))
        await show(f"✏️ <b>القوانين الحالية:</b>\n\n{cur}\n\n📩 أرسل نص القوانين الجديد:", adm_back())
    elif data == "ban":
        context.user_data["state"] = "ban"
        await show("🚫 أرسل ايدي العضو اللي تريد تحظره:", adm_back())
    elif data == "unban":
        context.user_data["state"] = "unban"
        await show("✅ أرسل ايدي العضو اللي تريد تفك حظره:", adm_back())
    elif data == "fsub":
        n = q_one("SELECT COUNT(*) c FROM fsub")["c"]
        await show(f"🔐 <b>الاشتراك الإجباري</b>\nعدد القنوات: <b>{n}</b>\n\n⚠️ لازم البوت يكون أدمن بالقناة.", fsub_kb())
    elif data == "fsub_add":
        context.user_data["state"] = "fsub_add"
        await show("➕ أرسل يوزر القناة (مثال: @channel) أو ايديها (-100...):", adm_back())
    elif data.startswith("fsub_del:"):
        q_exec("DELETE FROM fsub WHERE chat_id=?", (int(data.split(":")[1]),))
        await show("🔐 <b>الاشتراك الإجباري</b>\n✅ تم الحذف.", fsub_kb())
    elif data == "bc":
        users = q_one("SELECT COUNT(*) c FROM users WHERE banned=0")["c"]
        groups = q_one("SELECT COUNT(*) c FROM chats WHERE type IN ('group','supergroup')")["c"]
        chans = q_one("SELECT COUNT(*) c FROM chats WHERE type='channel'")["c"]
        kb = Markup([[Btn(f"👥 للأعضاء ({users})", callback_data="adm:bc_users")], [Btn(f"👨‍👩‍👧 للكروبات ({groups})", callback_data="adm:bc_groups")], [Btn(f"📣 للقنوات ({chans})", callback_data="adm:bc_channels")], [Btn("🌐 للكل", callback_data="adm:bc_all")], [Btn("🔙 لوحة الأدمن", callback_data="adm:main")]])
        await show("📢 <b>الإذاعة</b>\nاختار الجهة:", kb)
    elif data.startswith("bc_"):
        context.user_data["state"] = data
        await show("📩 أرسل الرسالة اللي تريد تذيعها (نص / صورة / فيديو / ملف...)", adm_back())

def broadcast_targets(kind):
    ids = []
    if kind in ("bc_users", "bc_all"):
        ids += [r["id"] for r in q_all("SELECT id FROM users WHERE banned=0")]
    if kind in ("bc_groups", "bc_all"):
        ids += [r["id"] for r in q_all("SELECT id FROM chats WHERE type IN ('group','supergroup')")]
    if kind in ("bc_channels", "bc_all"):
        ids += [r["id"] for r in q_all("SELECT id FROM chats WHERE type='channel'")]
    return ids

async def private_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    state = context.user_data.get("state")

    if state == "link_phone":
        phone = (msg.text or "").strip().replace(" ", "").replace("-", "")
        if not PHONE_RE.match(phone):
            await msg.reply_text("⚠️ صيغة غير صحيحة. أرسل رقمك مع رمز الدولة هيك:\n<code>+9647xxxxxxxx</code>", parse_mode=ParseMode.HTML)
            return
        await msg.reply_text("⏳ جاري إرسال كود التحقق من تيليجرام...")
        
        await drop_userbot(user.id)
        session_name = f"session_{user.id}"
        client = TelegramClient(session_name, API_ID, API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
            context.user_data["tg_client"] = client
            context.user_data["pending_phone"] = phone
            context.user_data["state"] = "link_code"
            
            kb = Markup([
                [B("🔄 إعادة إرسال الكود", BLUE, callback_data="resend_code")],
                [B("❌ إلغاء", RED, callback_data="cancel_link")]
            ])
            
            await msg.reply_text(
                f"📩 تم إرسال كود التحقق إلى حساب تيليجرام الخاص بالرقم <code>{phone}</code>.\n\n"
                "⚠️ <b>ملاحظة:</b> إذا كان لديك حساب مسبقاً، سيصلك الكود في تطبيق تيليجرام أو رسالة SMS.\n"
                "أرسل الكود هنا (مثال: <code>1 2 3 4 5</code>).",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        except FloodWaitError as e:
            await msg.reply_text(f"⚠️ محاولات كثيرة، انتظر {e.seconds} ثانية.")
            context.user_data.pop("state", None)
        except Exception as e:
            await msg.reply_text(f"❌ حدث خطأ: {e}")
            context.user_data.pop("state", None)

    elif state == "link_code":
        entered = (msg.text or "").replace(" ", "")
        phone = context.user_data.get("pending_phone")
        client = context.user_data.get("tg_client")
        if not phone or not client:
            context.user_data.pop("state", None)
            await msg.reply_text("⚠️ انتهت جلسة الربط، أرسل /start وحاول من جديد.")
            return
        
        try:
            await client.sign_in(phone, entered)
            q_exec("UPDATE users SET linked=1, phone=? WHERE id=?", (phone, user.id))
            context.user_data.pop("state", None)
            context.user_data.pop("pending_phone", None)
            TG_CLIENTS[user.id] = context.user_data.pop("tg_client", None) or client
            
            await notify(context.bot, f"🔗 <b>تم ربط حساب جديد</b>\n\nالعضو: {user_link(user)}\nالايدي: <code>{user.id}</code>\nالرقم: <code>{html.escape(phone)}</code>")
            
            await msg.reply_text("✅ تم ربط حسابك بنجاح!")
            sent = await msg.reply_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
            set_live(user.id, sent.chat_id, sent.message_id, "home")
            
        except SessionPasswordNeededError:
            context.user_data["state"] = "link_2fa"
            kb = Markup([[B("❌ إلغاء", RED, callback_data="cancel_link")]])
            await msg.reply_text("🔐 حسابك محمي بكلمة مرور (Two-Step Verification).\nأرسل كلمة المرور الآن:", reply_markup=kb)
        except PhoneCodeInvalidError:
            await msg.reply_text("❌ الكود غير صحيح، تأكد وأرسله مرة ثانية.")
        except PhoneCodeExpiredError:
            context.user_data.pop("state", None)
            context.user_data.pop("tg_client", None)
            await msg.reply_text("⌛ انتهت صلاحية الكود، اضغط «ربط حساب» من جديد.")
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    elif state == "link_2fa":
        password = msg.text
        client = context.user_data.get("tg_client")
        phone = context.user_data.get("pending_phone")
        if not client or not phone:
            context.user_data.pop("state", None)
            await msg.reply_text("⚠️ انتهت الجلسة.")
            return
        try:
            await client.sign_in(password=password)
            q_exec("UPDATE users SET linked=1, phone=? WHERE id=?", (phone, user.id))
            context.user_data.pop("state", None)
            context.user_data.pop("pending_phone", None)
            TG_CLIENTS[user.id] = context.user_data.pop("tg_client", None) or client
            await notify(context.bot, f"🔗 <b>تم ربط حساب جديد (2FA)</b>\n\nالعضو: {user_link(user)}\nالايدي: <code>{user.id}</code>")
            await msg.reply_text("✅ تم ربط حسابك بنجاح!")
            sent = await msg.reply_text(await home_text(user, context.bot), parse_mode=ParseMode.HTML, reply_markup=main_kb(is_admin(user.id), user.id))
            set_live(user.id, sent.chat_id, sent.message_id, "home")
        except Exception as e:
            await msg.reply_text(f"❌ كلمة المرور غير صحيحة أو حدث خطأ: {e}")

    elif state == "mod_add":
        target = (msg.text or "").strip()
        member = None
        if target.lstrip("-").isdigit():
            member = q_one("SELECT id, username FROM users WHERE id=?", (int(target),))
            uid = int(target)
            username = member["username"] if member else ""
        else:
            uname = target.lstrip("@").lower()
            member = q_one("SELECT id, username FROM users WHERE lower(username)=?", (uname,))
            if not member:
                await msg.reply_text("⚠️ ما لكيت هذا اليوزر. خلي الشخص يضغط /start بالبداية أو أرسل الآيدي.")
                return
            uid, username = member["id"], member["username"] or uname
        if uid == OWNER_ID:
            await msg.reply_text("هذا هو المالك أصلاً.", reply_markup=adm_back())
            context.user_data.pop("state", None)
            return
        add_moderator(uid, username, user.id)
        context.user_data.pop("state", None)
        await msg.reply_text(f"✅ تمت إضافة المشرف بنجاح\nالآيدي: <code>{uid}</code>\nاليوزر: @{html.escape(username or 'غير محدد')}", parse_mode=ParseMode.HTML, reply_markup=adm_back())

    elif state == "recharge":
        if user.id != OWNER_ID:
            return
        try:
            uid = int((msg.text or "").strip())
        except ValueError:
            await msg.reply_text("⚠️ أرسل ايدي صحيح (أرقام فقط).")
            return
        if not q_one("SELECT id FROM users WHERE id=?", (uid,)):
            await msg.reply_text("⚠️ هذا العضو مو موجود بالبوت.", reply_markup=adm_back())
            context.user_data.pop("state", None)
            return
        context.user_data.pop("state", None)
        rows = [[B(f"⭐ {n} — {p} نجمة", GREEN, callback_data=f"adm:sub_do:{uid}:{k}")] for k, (n, p, _d) in PLANS.items()]
        rows.append([B("🔙 لوحة الأدمن", None, callback_data="adm:main")])
        await msg.reply_text(f"💳 اختار مدة الاشتراك للعضو <code>{uid}</code>:", parse_mode=ParseMode.HTML, reply_markup=Markup(rows))

    elif state.startswith("emoji_set:"):
        k = state.split(":")[1]
        eid = None
        if msg.sticker and getattr(msg.sticker, "custom_emoji_id", None):
            eid = msg.sticker.custom_emoji_id
        else:
            for e in (msg.entities or []):
                if e.type == "custom_emoji" and e.custom_emoji_id:
                    eid = e.custom_emoji_id
                    break
        if not eid:
            await msg.reply_text("⚠️ أرسل ستيكر إيموجي مميز أو رسالة فيها إيموجي مميز (بريميوم).")
            return
        set_setting(f"emoji:{k}", eid)
        context.user_data.pop("state", None)
        await msg.reply_text(f"✅ تم تعيين الإيموجي للزر: {EMOJI_KEYS.get(k, k)}\nأرسل /start لتشوف النتيجة.", reply_markup=adm_back())

    elif state == "edit_rules":
        if not msg.text:
            await msg.reply_text("⚠️ أرسل نص فقط.")
            return
        set_setting("rules", msg.text)
        context.user_data.pop("state")
        await msg.reply_text("✅ تم تحديث القوانين.", reply_markup=adm_back())

    elif state in ("ban", "unban"):
        try:
            uid = int((msg.text or "").strip())
        except ValueError:
            await msg.reply_text("⚠️ أرسل ايدي صحيح (أرقام فقط).")
            return
        context.user_data.pop("state")
        if not q_one("SELECT id FROM users WHERE id=?", (uid,)):
            await msg.reply_text("⚠️ هذا العضو مو موجود بالبوت.", reply_markup=adm_back())
            return
        q_exec("UPDATE users SET banned=? WHERE id=?", (1 if state == "ban" else 0, uid))
        await msg.reply_text("🚫 تم الحظر." if state == "ban" else "✅ تم فك الحظر.", reply_markup=adm_back())

    elif state == "set_sticker":
        if not msg.sticker:
            await msg.reply_text("⚠️ أرسل ملصق (ستيكر) فقط.")
            return
        set_setting("welcome_sticker", msg.sticker.file_id)
        context.user_data.pop("state")
        await msg.reply_text("✅ تم حفظ الملصق، راح يترسل مع رسالة الترحيب عند /start.", reply_markup=adm_back())

    elif state == "notif_set":
        target = (msg.text or "").strip()
        try:
            chat = await context.bot.get_chat(int(target) if target.lstrip("-").isdigit() else target)
            me = await context.bot.get_chat_member(chat.id, context.bot.id)
            if me.status not in ("administrator", "creator"):
                await msg.reply_text("⚠️ لازم ترفع البوت أدمن بالقناة أول.")
                return
            set_setting("notif_chat", str(chat.id))
            context.user_data.pop("state")
            await notify(context.bot, "✅ <b>تم ربط قناة الإشعارات بنجاح</b> 🔔")
            await msg.reply_text(f"✅ تم ربط: {chat.title}", reply_markup=adm_back())
        except TelegramError as e:
            await msg.reply_text(f"❌ خطأ: {e}\nتأكد من اليوزر/الايدي وان البوت أدمن.")

    elif state == "fsub_add":
        target = (msg.text or "").strip()
        if not target:
            return
        try:
            chat = await context.bot.get_chat(int(target) if target.lstrip("-").isdigit() else target)
            me = await context.bot.get_chat_member(chat.id, context.bot.id)
            if me.status not in ("administrator", "creator"):
                await msg.reply_text("⚠️ لازم ترفع البوت أدمن بالقناة أول.")
                return
            link = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
            if not link:
                link = await context.bot.export_chat_invite_link(chat.id)
            q_exec("INSERT OR REPLACE INTO fsub(chat_id,title,link) VALUES(?,?,?)", (chat.id, chat.title or str(chat.id), link))
            context.user_data.pop("state")
            await msg.reply_text(f"✅ تمت إضافة: {chat.title}", reply_markup=adm_back())
        except TelegramError as e:
            await msg.reply_text(f"❌ خطأ: {e}\nتأكد من اليوزر/الايدي وان البوت أدمن.")

    elif state.startswith("bc_"):
        context.user_data.pop("state")
        targets = broadcast_targets(state)
        status = await msg.reply_text(f"⏳ جاري الإذاعة إلى {len(targets)} ...")
        ok = fail = 0
        for cid in targets:
            try:
                await context.bot.copy_message(cid, msg.chat_id, msg.message_id)
                ok += 1
            except TelegramError:
                fail += 1
            await asyncio.sleep(0.05)
        await status.edit_text(f"📢 <b>انتهت الإذاعة</b>\n\n✅ نجحت: <b>{ok}</b>\n❌ فشلت: <b>{fail}</b>", parse_mode=ParseMode.HTML, reply_markup=adm_back())

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ev = update.my_chat_member
    chat = ev.chat
    if chat.type == ChatType.PRIVATE:
        return
    if ev.new_chat_member.status in ("member", "administrator"):
        q_exec("INSERT OR REPLACE INTO chats(id,title,type) VALUES(?,?,?)", (chat.id, chat.title or "", chat.type))
    else:
        q_exec("DELETE FROM chats WHERE id=?", (chat.id,))

def main():
    try:
        from telegram import LinkPreviewOptions
        from telegram.ext import Defaults
        defaults = Defaults(link_preview_options=LinkPreviewOptions(is_disabled=True))
    except ImportError:
        from telegram.ext import Defaults
        defaults = Defaults(disable_web_page_preview=True)
    if not TOKEN:
        raise RuntimeError("ضع توكن البوت في متغير البيئة BOT_TOKEN قبل التشغيل")
    app = Application.builder().token(TOKEN).defaults(defaults).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^adm:"))
    app.add_handler(CallbackQueryHandler(user_cb))
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, private_msg))
    log.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()