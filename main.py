"""
PostMaster-style bot: aiogram 3 (واجهة البوت) + Telethon (حسابات النشر)
pip install aiogram telethon cryptography
env: BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS=123,456
"""
import asyncio, csv, inspect, io, json, os, random, re, secrets, sqlite3, time, logging
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton as _IB, FSInputFile, ErrorEvent, BufferedInputFile, MessageEntity)
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.users import GetUsersRequest
from telethon.tl.types import InputUserSelf, UserStatusOnline
from cryptography.fernet import Fernet

logging.basicConfig(level=logging.INFO)
ICONS = {}; ICONS_ON = [True]   # callback_data -> custom_emoji_id (ملصقات مميز تلكرام على الأزرار)
def B(**kw):
    cb = kw.get("callback_data") or ("owner" if kw.get("url") else None); ic = kw.get("icon_custom_emoji_id") or (ICONS.get(cb) if ICONS_ON[0] and cb else None)
    if ic:
        kw["icon_custom_emoji_id"] = ic; kw["text"] = re.sub(r"^[^\w(]+", "", kw.get("text", "")) or kw.get("text", "")
    return _IB(**kw)

# --- إعداداتك الخاصة المحدثة بالكامل ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9286024586:AAGL6Ht3lAY6RCVo0cTqAdM-MymsoPMw4ys")
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "7753146356").split(",") if x.strip()}
ROOT = set(ADMINS)  # المالكون الأساسيون (ما ينحذفون ولهم إدارة المشرفين)
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "@RX62X")  # قناة الشعارات (البوت لازم يكون مشرف فيها)
API_ID = int(os.environ.get("API_ID", "36444028"))
API_HASH = os.environ.get("API_HASH", "92aac2e192857ff973a9b3ae2a3274ca")
if not API_ID or not API_HASH:
    raise SystemExit("ضع API_ID و API_HASH بأعلى الملف (من my.telegram.org)")
OWNER = "@K000OOO"  # يوزر المالك: دائم لكل الاشتراكات والتواصل

FREE = dict(accounts=1, groups=4, min_s=300, replies=1, posts=1, chats=1)
VIP = dict(accounts=6, groups=10, min_s=5, replies=5, posts=5, chats=10)
MAX_IV = 3 * 86400

# ---------- تشفير الجلسات ----------
_k = os.environ.get("FERNET_KEY", "").encode()
if not _k:
    if not os.path.exists("fernet.key"):
        open("fernet.key", "wb").write(Fernet.generate_key())
    try: os.chmod("fernet.key", 0o600)
    except OSError: pass
    _k = open("fernet.key", "rb").read()
fer = Fernet(_k)

# ---------- قاعدة البيانات ----------
db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
def q(sql, a=()):
    cur = db.execute(sql, a); db.commit(); return cur
q("""create table if not exists users(id integer primary key, banned int default 0,
 interval int default 10, post_text text default '', autopost int default 0,
 reply_on int default 0, reply_text text default '')""")
q("""create table if not exists accounts(id integer primary key autoincrement,
 uid int, phone text, name text, session text)""")
q("""create table if not exists groups(id integer primary key autoincrement,
 acc int, chat_id int, title text, sel int default 1)""")
q("create table if not exists channels(chat text primary key, link text)")
q("create table if not exists replied(acc int, uid int, ts real, primary key(acc,uid))")
q("create table if not exists cfg(k text primary key, v text)")
q("create table if not exists clock_chats(id integer primary key autoincrement, uid int, chat_id int, title text, orig_title text, orig_desc text, mode text)")
q("create table if not exists plans(id integer primary key autoincrement, name text, days int, price text)")
for _s in ("alter table users add column vip_until real default 0", "alter table users add column joined real default 0",
           "alter table users add column ref_done int default 0", "alter table channels add column link text",
           "alter table users add column quiet_on int default 0", "alter table users add column quiet_from int default 1",
           "alter table users add column quiet_to int default 7", "alter table accounts add column cool_until real default 0",
           "alter table accounts add column day text default ''", "alter table accounts add column sent_today int default 0",
           "alter table accounts add column created real default 0",
           "alter table groups add column fails int default 0",
           "alter table users add column text_am text default ''", "alter table users add column text_pm text default ''",
           "alter table users add column media_path text default ''", "alter table users add column keywords text default ''",
           "alter table users add column radar_on int default 0", "alter table users add column vip_remind real default 0",
           "alter table users add column vip_notified real default 0",
           "alter table users add column uname text default ''", "alter table users add column fname text default ''",
           "alter table users add column notified_new int default 0",
           "alter table users add column show_ampm int default 1",
           "alter table users add column quiet_from_m int default 0", "alter table users add column quiet_to_m int default 0",
           "alter table users add column start_at real default 0",
           "alter table users add column interval_s int default 0", "alter table users add column want_groups int default 0",
           "alter table users add column clock_on int default 0", "alter table users add column reply_mode text default 'both'",
           "alter table accounts add column orig_first text default ''", "alter table accounts add column orig_last text default ''",
           "alter table accounts add column name_set int default 0",
           "alter table users add column present_text text default ''", "alter table users add column anim_style text default ''", "alter table users add column status_mode text default ''", "alter table users add column status_until real default 0"):
    try: q(_s)
    except sqlite3.OperationalError: pass
q("create table if not exists sec_events(id integer primary key autoincrement, ts real, kind text, uid int, ack int default 0)")
q("create table if not exists codes(code text primary key, days int, used_by int default 0, used_at real default 0, created real)")
q("create table if not exists sent_log(uid int, acc int, day text, n int default 0, primary key(acc, day))")
q("create table if not exists admin_log(id integer primary key autoincrement, ts real, admin int, action text)")
if not q("select 1 from plans").fetchone():
    for _p in (("10 أيام", 10, "50 ⭐ أو 1$ محفظة"), ("شهر", 30, "120 ⭐ أو 3$ محفظة"), ("3 أشهر", 90, "300 ⭐ أو 8$ محفظة"), ("سنة", 365, "1000 ⭐ أو 25$ محفظة")):
        q("insert into plans(name,days,price) values(?,?,?)", _p)

def user(uid):
    q("insert or ignore into users(id,joined) values(?,?)", (uid, time.time()))
    return q("select * from users where id=?", (uid,)).fetchone()
def cfg_get(k, d="1"):
    r = q("select v from cfg where k=?", (k,)).fetchone(); return r["v"] if r else d
def cfg_set(k, v): q("insert or replace into cfg values(?,?)", (k, v))
if "icon_custom_emoji_id" not in getattr(_IB, "model_fields", {}): logging.warning("aiogram قديم: حدّثه (pip install -U aiogram) حتى تشتغل ملصقات الأزرار")
def tog(text, cb, flag):
    ic = ICONS.get("st_on" if flag else "st_off") if ICONS_ON[0] else None
    if ic: return B(text=text, callback_data=cb, icon_custom_emoji_id=ic)
    return B(text=f"{text} {on(flag)}", callback_data=cb)
def load_icons():
    try: ICONS.clear(); ICONS.update(json.loads(cfg_get("btn_icons", "{}"))); ICONS_ON[0] = cfg_get("icons_on", "1") == "1"
    except Exception: pass
load_icons()
def alog(admin, text): q("insert into admin_log(ts,admin,action) values(?,?,?)", (time.time(), admin, text))
def is_vip(uid): return uid in ADMINS or user(uid)["vip_until"] > time.time()
def lim(uid): return VIP if is_vip(uid) else FREE
def add_vip(uid, days):
    base = max(user(uid)["vip_until"], time.time())
    q("update users set vip_until=? where id=?", (base + days * 86400, uid))
def vip_text(uid):
    if uid in ADMINS: return "∞ (أدمن)"
    left = user(uid)["vip_until"] - time.time()
    return f"فعّال ({int(left // 86400) + 1} يوم)" if left > 0 else "غير مفعّل"

NOACC = "🔗 اربط حسابك أولاً من زر 📱 حساباتي"
def has_acc(uid): return bool(q("select 1 from accounts where uid=?", (uid,)).fetchone())
def eff_iv(u): return u["interval_s"] or (u["interval"] or 10) * 60
def fmt_dur(x):
    x = int(x)
    if x < 60: return f"{x} ثانية"
    if x < 3600: return f"{x // 60} دقيقة" if x % 60 == 0 else f"{x // 60}د {x % 60}ث"
    if x < 86400: return f"{x // 3600} ساعة" if x % 3600 == 0 else f"{x // 3600}س {x % 3600 // 60}د"
    return f"{x // 86400} يوم" if x % 86400 == 0 else f"{x // 86400}ي {x % 86400 // 3600}س"
def parse_dur(t):
    r = re.fullmatch(r"\s*(\d+)\s*(ث|s|sec|د|m|min|س|h|hr|ي|d|day)?\s*", (t or "").lower())
    if not r: return None
    n, un = int(r[1]), r[2] or "د"
    return n * (1 if un in ("ث", "s", "sec") else 60 if un in ("د", "m", "min") else 3600 if un in ("س", "h", "hr") else 86400)
def rep_list(u):
    raw = u["reply_text"] or ""
    try: v = json.loads(raw)
    except ValueError: v = raw
    if not isinstance(v, list): v = [str(v)] if raw.strip() else []
    return [x for x in v if isinstance(x, str) and x.strip()]

def clock_line(uid):
    u = user(uid); t = time.gmtime(time.time() + TZ * 3600)
    return f"🕐 {deco(hm(t.tm_hour, t.tm_min, bool(u['show_ampm'])))}"

_up = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
_lo = "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"
_dg = "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
def deco(s):
    out = ""
    for c in s:
        if "A" <= c <= "Z": out += _up[ord(c) - 65]
        elif "a" <= c <= "z": out += _lo[ord(c) - 97]
        elif c.isdigit() and c.isascii(): out += _dg[int(c)]
        else: out += c
    return out

clients = {}
tasks = {}
last_out = {}
last_chat_out = {}
last_in = {}
online_cache = {}
auto_until = {}
SESSION_GAP = 600

async def owner_online(cl, acc_id):
    t = time.time(); c = online_cache.get(acc_id)
    if c and t - c[0] < 5: return c[1]
    on = t - last_out.get(acc_id, 0) < 60
    try:
        r = await asyncio.wait_for(cl(GetUsersRequest([InputUserSelf()])), 0.4)
        on = on or isinstance(r[0].status, UserStatusOnline)
    except Exception: pass
    online_cache[acc_id] = (t, on); return on

async def online_poll(cl, acc_id):
    while cl.is_connected() and clients.get(acc_id) is cl:
        online_cache.pop(acc_id, None)
        try: await owner_online(cl, acc_id)
        except Exception: pass
        await asyncio.sleep(3)

STATUS = {"sleep": ("😴 نايم", "😴", "أنا نايم هسه 🌙 أرد عليك أول ما أصحى."),
          "work": ("💼 بالدوام", "💼", "أنا بالدوام هسه 💼 أرجعلك بأقرب وقت."),
          "trip": ("✈️ مسافر", "✈️", "أنا مسافر هسه ✈️ ما أكدر أرد، أرجعلك قريب."),
          "busy": ("🔴 مشغول", "🔴", "مشغول هسه 🔴 اكتب سبب مراسلتك وأرد عليك لاحقاً."),
          "eat": ("🍽 آكل", "🍽", "آكل هسه 🍽 دقايق وأجي.")}
def status_now(u):
    st = STATUS.get(u["status_mode"] or "")
    return st if st and (not u["status_until"] or u["status_until"] > time.time()) else None

def attach_reply(cl, acc_id, uid):
    attach_radar(cl, acc_id, uid)
    asyncio.get_event_loop().create_task(online_poll(cl, acc_id))
    @cl.on(events.NewMessage(outgoing=True))
    async def _o(ev):
        if time.time() < auto_until.get(acc_id, 0): return
        last_out[acc_id] = time.time(); online_cache.pop(acc_id, None)
        if ev.is_private: last_chat_out[(acc_id, ev.chat_id)] = time.time()
    @cl.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def _h(ev):
        now = time.time(); key = (acc_id, ev.chat_id)
        prev = last_in.get(key, 0); last_in[key] = now
        if now - prev < SESSION_GAP: return
        if now - last_chat_out.get(key, 0) < SESSION_GAP: return
        u = user(uid); st = status_now(u)
        if st: txt = st[2]
        else:
            if not u["reply_on"]: return
            mode = u["reply_mode"] or "both"
            if await owner_online(cl, acc_id):
                if mode == "away": return
                txt = (u["present_text"] or "هسه اجي 🙏")
            else:
                if mode == "present": return
                reps = rep_list(u)[:lim(uid)["replies"]]
                if not reps: return
                txt = random.choice(reps)
        sdr = await ev.get_sender()
        if not sdr or getattr(sdr, "bot", False) or getattr(sdr, "is_self", False): return
        auto_until[acc_id] = time.time() + 3
        await ev.reply(txt)

async def get_client(acc):
    cl = clients.get(acc["id"])
    if cl and cl.is_connected(): return cl
    cl = TelegramClient(StringSession(fer.decrypt(acc["session"].encode()).decode()), API_ID, API_HASH)
    await cl.connect()
    if not await cl.is_user_authorized():
        q("delete from accounts where id=?", (acc["id"],)); return None
    attach_reply(cl, acc["id"], acc["uid"])
    clients[acc["id"]] = cl
    return cl

TZ = 3
DAILY = {"free": 120, "vip": 400}
def now_hour(): return int((time.time() / 3600 + TZ) % 24)
def now_min(): return int((time.time() / 60 + TZ * 60) % 1440)
def hm(h, m=0, ap=True):
    return f"{h % 12 or 12}:{m:02d}" + (f" {'ص' if h < 12 else 'م'}" if ap else "")
def parse_t(s):
    r = re.fullmatch(r"\s*(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*(ص|م|am|pm)?\s*", s, re.I)
    if not r: return None
    n, mi, p = int(r[1]), int(r[2] or 0), (r[3] or "").lower()
    if n > 23 or mi > 59: return None
    if n > 12: return n, mi
    return (n % 12 + 12 if p in ("م", "pm") else n % 12), mi
def is_quiet(u):
    if not u["quiet_on"]: return False
    a = u["quiet_from"] * 60 + (u["quiet_from_m"] or 0)
    b = u["quiet_to"] * 60 + (u["quiet_to_m"] or 0)
    t = now_min()
    return (a <= t < b) if a < b else (t >= a or t < b)
def acc_cap(acc, uid):
    cap = DAILY["vip"] if is_vip(uid) else DAILY["free"]
    age = (time.time() - (acc["created"] or 0)) / 86400
    return min(cap, 40) if age < 3 else min(cap, 80) if age < 7 else cap
def user_tag(uid):
    u = user(uid)
    return f"{u['fname'] or 'مستخدم'} ({'@' + u['uname'] if u['uname'] else 'بدون يوزر'}) [{uid}]"
def mask(p): return p[:4] + "*" * max(len(p) - 7, 3) + p[-3:]
def cfg_chan():
    v = cfg_get("log_channel", LOG_CHANNEL)
    return int(v) if v.lstrip("-").isdigit() else v

chan_err = [0.0]
async def notify(text, admins=False):
    try:
        await bot.send_message(cfg_chan(), text[:4000])
    except Exception as e:
        logging.warning("channel notify failed %s", e)
        if time.time() - chan_err[0] > 3600:
            chan_err[0] = time.time(); admins = True
            text = "⚠️ تعذر الإرسال لقناة الشعارات، تأكد أن البوت مشرف فيها.\n\n" + text
    if admins:
        for a in ADMINS:
            try: await bot.send_message(a, text[:4000])
            except Exception: pass

async def alert(uid, text, admin=False):
    for t in ({uid} | (ADMINS if admin else set())):
        try: await bot.send_message(t, text)
        except Exception: pass
    if admin: await notify(f"{text}\n👤 المستخدم: {user_tag(uid)}")

def today_str(off=0): return time.strftime("%Y-%m-%d", time.gmtime(time.time() + TZ * 3600 - off * 86400))
def pick_text(u):
    h = now_hour()
    return ((u["text_am"] if 5 <= h < 16 else u["text_pm"]) or "").strip() or u["post_text"]
def g_fail(gid):
    q("update groups set fails=fails+1 where id=?", (gid,))
    q("update groups set sel=0 where id=? and fails>=3", (gid,))

async def post_round(uid, fast=False):
    u = user(uid); sent = 0
    txt = pick_text(u)
    if not txt: return -1
    iv_s = eff_iv(u)
    variants = [x.strip() for x in re.split(r"\n-{3,}\n", txt) if x.strip()][:lim(uid)["posts"]]
    media = u["media_path"] if u["media_path"] and os.path.exists(u["media_path"]) else None
    today = today_str(); started = False
    accs = q("select * from accounts where uid=? order by id limit ?", (uid, lim(uid)["accounts"])).fetchall()
    random.shuffle(accs)
    for acc in accs:
        if (acc["cool_until"] or 0) > time.time(): continue
        if started and not fast: await asyncio.sleep(random.uniform(20, 90))
        started = True
        if acc["day"] != today:
            q("update accounts set day=?, sent_today=0 where id=?", (today, acc["id"]))
            acc = q("select * from accounts where id=?", (acc["id"],)).fetchone()
        cap, done = acc_cap(acc, uid), acc["sent_today"]
        try:
            cl = await get_client(acc)
            if not cl: continue
            groups = q("select * from groups where acc=? and sel=1 limit ?", (acc["id"], lim(uid)["groups"])).fetchall()
            random.shuffle(groups)
            for g in groups:
                if done >= cap: break
                try:
                    msg = random.choice(variants)
                    if media:
                        await cl.send_file(g["chat_id"], media, caption=msg if len(msg) <= 1024 else None)
                        if len(msg) > 1024: await cl.send_message(g["chat_id"], msg)
                    else: await cl.send_message(g["chat_id"], msg)
                    sent += 1; done += 1
                    q("update accounts set sent_today=? where id=?", (done, acc["id"]))
                    q("insert into sent_log(uid,acc,day,n) values(?,?,?,1) on conflict(acc,day) do update set n=n+1", (uid, acc["id"], today))
                    q("update groups set fails=0 where id=?", (g["id"],))
                except errors.FloodWaitError as e:
                    if e.seconds > 300:
                        q("update accounts set cool_until=? where id=?", (time.time() + e.seconds + 60, acc["id"])); sec_event("floodwait", uid)
                        await alert(uid, f"⏸ تم إيقاف حساب {mask(acc['phone'])} مؤقتاً ({e.seconds // 60} دقيقة) بسبب تقييد مؤقت من تيليجرام.")
                        break
                    await asyncio.sleep(e.seconds + 5)
                except errors.PeerFloodError:
                    q("update accounts set cool_until=? where id=?", (time.time() + 8 * 3600, acc["id"])); sec_event("peerflood", uid)
                    await alert(uid, f"⚠️ تيليجرام قيّد الحساب {mask(acc['phone'])} (سبام). تم إيقافه 8 ساعات تلقائياً لحمايته.", admin=True)
                    break
                except errors.SlowModeWaitError: pass
                except (errors.ChatWriteForbiddenError, errors.UserBannedInChannelError,
                        errors.ChannelPrivateError, errors.ChatAdminRequiredError):
                    g_fail(g["id"])
                except errors.RPCError: pass
                await asyncio.sleep(random.uniform(5, 15) if iv_s >= 30 else random.uniform(max(1.0, iv_s * 0.8), iv_s * 1.2))
        except (errors.AuthKeyUnregisteredError, errors.UserDeactivatedBanError, errors.UserDeactivatedError,
                errors.SessionRevokedError):
            q("delete from accounts where id=?", (acc["id"],)); q("delete from groups where acc=?", (acc["id"],)); sec_event("dead", uid)
            await alert(uid, f"❌ الحساب {mask(acc['phone'])} لم يعد صالحاً (انتهت الجلسة أو تعطل) وتم حذفه من البوت.", admin=True)
        except Exception as e:
            logging.warning("round error %s", e)
    return sent

async def post_loop(uid):
    while True:
        u = user(uid)
        if not u["autopost"] or u["banned"]: break
        if (u["start_at"] or 0) > time.time():
            await asyncio.sleep(15); continue
        if is_quiet(u):
            await asyncio.sleep(60); continue
        await post_round(uid)
        u = user(uid)
        wait = max(eff_iv(u), lim(uid)["min_s"]) * random.uniform(0.9, 1.15)
        t0 = time.time()
        while time.time() - t0 < wait:
            await asyncio.sleep(1 if wait < 30 else 3)
            if not user(uid)["autopost"]: return

def start_loop(uid):
    t = tasks.get(uid)
    if t and not t.done(): return
    tasks[uid] = asyncio.create_task(post_loop(uid))

def on(b): return "🟢" if b else "🔴"
def sel_count(uid):
    return q("select count(*) c from groups g join accounts a on a.id=g.acc where a.uid=? and g.sel=1", (uid,)).fetchone()["c"]
def grp_cap(uid):
    L = lim(uid)["groups"]; w = user(uid)["want_groups"] or 0
    return min(w, L) if w else L
def main_text(uid):
    u = user(uid)
    na = q("select count(*) c from accounts where uid=?", (uid,)).fetchone()["c"]
    head = (clock_line(uid) + "\n\n") if u["clock_on"] else ""
    return head + (f"📡 حالتك:\n"
            f"├ 🚀 النشر التلقائي: {'يعمل' if u['autopost'] else 'متوقف'} {on(u['autopost'])} (كل {fmt_dur(eff_iv(u))})\n"
            f"├ 💬 الرد بالخاص: {'يعمل' if u['reply_on'] else 'متوقف'} {on(u['reply_on'])}\n"
            f"├ 📱 الحسابات: {na}\n"
            f"├ 📥 الكروبات: {sel_count(uid)}/{lim(uid)['groups']}\n"
            f"└ 💎 VIP: {vip_text(uid)}\n\n"
            f"👇 اختر من الأزرار:")
def main_kb(uid):
    u = user(uid)
    na = q("select count(*) c from accounts where uid=?", (uid,)).fetchone()["c"]
    vip = is_vip(uid)
    rows = [
        [B(text=f"📱 حساباتي ({na})", callback_data="accs")],
        [tog("🚀 النشر التلقائي", "apm", u["autopost"])],
        [tog("💬 رد بالخاص", "ar", u["reply_on"])],
        [B(text="📊 الإحصائيات", callback_data="ms"), B(text="🕐 الساعة", callback_data="clk")],
        [B(text="📢 ساعة القناة / الكروب", callback_data="cc")],
        [B(text="💎 VIP ✅ (تجديد)" if vip else "⭐ تفعيل VIP", callback_data="vipbuy"), B(text="🎟 تفعيل كود", callback_data="rc")],
        [B(text="🎁 VIP مجاناً", callback_data="vipfree"), B(text="📖 الدليل", callback_data="guide")],
        [B(text="🧑‍💻 تواصل مع المالك", url="https://t.me/" + OWNER.lstrip("@"))],
    ]
    if uid in ADMINS: rows.append([B(text="👑 لوحة الأدمن", callback_data="adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def back(cb="home"): return InlineKeyboardMarkup(inline_keyboard=[[B(text="🔙 رجوع", callback_data=cb)]])

def apm_view(uid):
    u = user(uid); st = u["start_at"] or 0; ap = u["show_ampm"]; L = lim(uid)
    txt = (f"🚀 النشر التلقائي: {'يعمل' if u['autopost'] else 'متوقف'} {on(u['autopost'])}\n"
           f"⏱ الفاصل: كل {fmt_dur(eff_iv(u))}\n📥 الكروبات: {sel_count(uid)}/{L['groups']}\n"
           f"✍️ النص: {'موجود ✅' if u['post_text'] else 'غير محدد'}")
    waiting = st > time.time()
    if waiting:
        hh, mm = divmod(int((st + TZ * 3600) % 86400) // 60, 60)
        txt += f"\n⏰ يبدأ الساعة {hm(hh, mm)} (بتوقيت العراق)"
    if u["quiet_on"]:
        txt += f"\n🌙 راحة من {hm(u['quiet_from'], u['quiet_from_m'] or 0, ap)} إلى {hm(u['quiet_to'], u['quiet_to_m'] or 0, ap)}"
    rows = [[B(text="⏹ إيقاف النشر" if u["autopost"] else "▶️ تشغيل النشر", callback_data="ap")],
            [B(text=f"⏱ تحديد فاصل النشر ({fmt_dur(eff_iv(u))})", callback_data="int")],
            [B(text=f"📥 الكروبات ({sel_count(uid)}/{L['groups']})", callback_data="gcount")],
            [B(text="✍️ نص الرسالة", callback_data="pt"), B(text="🖼 وسائط", callback_data="pm")],
            [B(text="⏰ وقت البدء", callback_data="sts"), tog("🌙 الراحة", "qh", u["quiet_on"])]]
    if waiting: rows.append([B(text="❌ إلغاء البدء المجدول", callback_data="sx")])
    rows += [[B(text="🧪 تجربة إرسال فورية", callback_data="test")], [B(text="🔙 رجوع", callback_data="home")]]
    return txt, InlineKeyboardMarkup(inline_keyboard=rows)

class S(StatesGroup):
    phone = State(); code = State(); pw = State(); text = State(); iv = State(); rep = State()
    ch = State(); bc = State(); ban = State(); unban = State()
    wel = State(); sup = State(); grant = State(); plan = State(); quiet = State(); gen = State(); redeem = State(); ico = State(); cc = State(); prs = State(); media = State(); sam = State(); spm = State(); kw = State(); chan = State(); find = State(); lim = State(); addadm = State(); sat = State()

bot = Bot(BOT_TOKEN); dp = Dispatcher(storage=MemoryStorage())
pending = {}
login_hits = {}
def login_ok(uid, limit=10, window=3600):
    t = time.time(); L = [x for x in login_hits.get(uid, []) if t - x < window]
    ok = len(L) < limit
    if ok: L.append(t)
    login_hits[uid] = L
    if not ok and isinstance(uid, int): sec_event("login_block", uid)
    return ok
last_hit = {}; pending_ref = {}; stats = {"drops": 0}; err_t = [0.0]

async def missing_channels(uid):
    out = []
    for r in q("select chat,link from channels").fetchall():
        try:
            cid = int(r["chat"]) if r["chat"].lstrip("-").isdigit() else r["chat"]
            m = await bot.get_chat_member(cid, uid)
            if m.status in ("left", "kicked"): out.append(r["link"] or "https://t.me/" + r["chat"].lstrip("@"))
        except Exception: pass
    return out

class Guard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.new_chat_title: return await handler(event, data)
        u = event.from_user
        if not u: return
        uid = u.id; row = user(uid)
        if row["uname"] != (u.username or "") or row["fname"] != (u.first_name or ""):
            q("update users set uname=?, fname=? where id=?", (u.username or "", u.first_name or "", uid))
        if row["banned"] and uid not in ADMINS: return
        if isinstance(event, Message) and (event.text or "").startswith("/start ref_"):
            pending_ref[uid] = event.text.split("ref_", 1)[1].strip()
        now = time.time()
        if now - last_hit.get(uid, 0) < 0.5 and uid not in ADMINS:
            stats["drops"] += 1; return
        last_hit[uid] = now
        if uid in ADMINS: return await handler(event, data)
        if cfg_get("bot_on") != "1":
            return await (event.answer if isinstance(event, Message) else event.message.answer)("🛠 البوت متوقف مؤقتاً للصيانة.")
        if True:
            miss = await missing_channels(uid)
            if miss:
                rows = [[B(text=f"📢 اشترك في القناة ({i})", url=l)] for i, l in enumerate(miss, 1)]
                rows.append([B(text="🔄 تحقق من الاشتراك", callback_data="chk")])
                msg = event if isinstance(event, Message) else event.message
                await msg.answer("⚠️ عذراً عزيزي!\n\nلا يمكنك استخدام البوت قبل الاشتراك في القنوات التالية لحمايته ودعمه.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
                if isinstance(event, CallbackQuery): await event.answer()
                return
        return await handler(event, data)
dp.message.outer_middleware(Guard()); dp.callback_query.outer_middleware(Guard())

async def edit(c: CallbackQuery, text, kb=None):
    try: await c.message.edit_text(text, reply_markup=kb)
    except Exception: await c.message.answer(text, reply_markup=kb)

DEFAULT_WELCOME = ("🚀 مرحباً بك في منصة النشر التلقائي على تيليجرام!\n\n"
    "🛡 حماية وأمان: نشر ذكي بفواصل عشوائية بين الرسائل.\n\n"
    "✨ المزايا:\n• نشر تلقائي بوقت تحدده\n• رد آلي على رسائل الخاص\n• إدارة المجموعات بسهولة\n• باقات VIP بمزايا أقوى\n\n"
    "🎁 ابدأ الآن واختصر وقتك وجهدك!")

@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear(); uid = m.from_user.id
    if not user(uid)["notified_new"]:
        q("update users set notified_new=1 where id=?", (uid,))
        _u = user(uid)
        await notify(f"✅ تم انضمام العضو\n👤 {_u['fname'] or 'مستخدم'}\n🔗 {'@' + _u['uname'] if _u['uname'] else 'بدون يوزر'}\n🆔 {uid}", admins=True)
    rid = pending_ref.pop(uid, None)
    if rid and rid.isdigit() and int(rid) != uid:
        u = user(uid)
        if not u["ref_done"] and time.time() - u["joined"] < 3600 and q("select 1 from users where id=?", (int(rid),)).fetchone():
            q("update users set ref_done=1 where id=?", (uid,)); add_vip(int(rid), int(cfg_get("ref_days", "1"))); await notify(f"🎁 إحالة جديدة: {user_tag(uid)} انضم عبر رابط {user_tag(int(rid))}")
            try: await bot.send_message(int(rid), "🎁 انضم شخص عبر رابطك! أُضيف لك VIP.")
            except Exception: pass
    txt, ph = cfg_get("welcome_text", DEFAULT_WELCOME), cfg_get("welcome_photo", "")
    try: ents = [MessageEntity(**d) for d in json.loads(cfg_get("welcome_ents", "[]"))]
    except Exception: ents = []
    try:
        if ph: await m.answer_photo(ph, caption=txt[:1024], caption_entities=[e for e in ents if e.offset + e.length <= 1024] or None)
        else: await m.answer(txt, entities=ents or None)
    except Exception as e:
        logging.warning("welcome entities %s", e)
        if ph: await m.answer_photo(ph, caption=txt[:1024])
        else: await m.answer(txt)
    await m.answer(f"أهلاً {deco(m.from_user.first_name or '')} 👋\n\n" + main_text(uid), reply_markup=main_kb(uid))

@dp.callback_query(F.data.in_({"home", "chk"}))
async def home(c: CallbackQuery, state: FSMContext):
    await state.clear(); await edit(c, main_text(c.from_user.id), main_kb(c.from_user.id)); await c.answer()

@dp.callback_query(F.data == "ap")
async def ap(c: CallbackQuery):
    uid = c.from_user.id; u = user(uid)
    if not u["autopost"]:
        if not u["post_text"]: return await c.answer("اكتب نص الرسالة أولاً ✍️", show_alert=True)
        if not q("select 1 from accounts where uid=?", (uid,)).fetchone(): return await c.answer("اربط حسابك أولاً من زر 📱 حساباتي", show_alert=True)
        if not sel_count(uid): return await c.answer("حدد الكروبات أولاً 📥", show_alert=True)
        q("update users set autopost=1, start_at=0 where id=?", (uid,)); start_loop(uid)
    else: q("update users set autopost=0, start_at=0 where id=?", (uid,))
    t_, kb_ = apm_view(uid); await edit(c, t_, kb_); await c.answer()

@dp.callback_query(F.data == "test")
async def test(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    await c.answer("جاري الإرسال...")
    n = await post_round(c.from_user.id, fast=True)
    await c.message.answer("✍️ اكتب نص الرسالة أولاً." if n == -1 else f"✅ تم الإرسال إلى {n} مجموعة.")

def post_list(u): return [x.strip() for x in re.split(r"\n-{3,}\n", u["post_text"] or "") if x.strip()]
def pt_view(uid):
    u = user(uid); ps = post_list(u); mx = lim(uid)["posts"]
    txt = f"✍️ رسائل النشر ({len(ps)}/{mx})\n\n" + ("\n".join(f"{i}. {p.replace(chr(10), ' ')[:60]}" for i, p in enumerate(ps, 1)) or "لا يوجد")
    txt += "\n\nيختار البوت رسالة مختلفة بكل مرة." + ("" if is_vip(uid) else f"\n💎 VIP يسمح بـ {VIP['posts']} رسائل")
    rows = [[B(text=f"➕ إضافة رسالة ({len(ps)}/{mx})", callback_data="pta")]]
    if ps:
        rows.append([B(text=f"🗑 {i}", callback_data=f"ptd:{i - 1}") for i in range(1, len(ps) + 1)])
        rows.append([B(text="🗑 مسح الكل", callback_data="ptc")])
    rows.append([B(text="🔙 رجوع", callback_data="apm")])
    return txt, InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data == "pt")
async def pt(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not post_list(user(c.from_user.id)): return await pta(c, state)
    t, kb = pt_view(c.from_user.id); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data == "pta")
async def pta(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; ps = post_list(user(uid)); mx = lim(uid)["posts"]
    if len(ps) >= mx:
        return await c.answer(f"وصلت للحد ({mx})" + ("" if is_vip(uid) else f" 💎 VIP يسمح بـ {VIP['posts']} رسائل"), show_alert=True)
    await state.set_state(S.text); await edit(c, "✍️ أرسل نص الرسالة التي سيتم نشرها:", back("pt" if ps else "apm")); await c.answer()

@dp.callback_query(F.data.startswith("ptd:"))
async def ptd(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; ps = post_list(user(uid)); k = int(c.data[4:])
    if 0 <= k < len(ps): ps.pop(k)
    q("update users set post_text=? where id=?", ("\n---\n".join(ps), uid)); await pt(c, state)

@dp.callback_query(F.data == "ptc")
async def ptc(c: CallbackQuery, state: FSMContext):
    q("update users set post_text='' where id=?", (c.from_user.id,)); await pt(c, state)

@dp.message(S.text)
async def pt_in(m: Message, state: FSMContext):
    uid = m.from_user.id; txt = (m.text or "").strip()
    if not txt: return await m.answer("أرسل نص الرسالة.")
    mx = lim(uid)["posts"]; ps = post_list(user(uid)) + [x.strip() for x in re.split(r"\n-{3,}\n", txt) if x.strip()]
    if len(ps) > mx:
        return await m.answer(f"❌ الحد المسموح لك {mx} " + ("رسالة" if mx == 1 else "رسائل") + "." + ("" if is_vip(uid) else f" 💎 VIP يسمح بـ {VIP['posts']}."))
    q("update users set post_text=? where id=?", ("\n---\n".join(ps), uid)); await state.clear()
    t, kb = pt_view(uid); await m.answer("✅ تم الحفظ.\n\n" + t, reply_markup=kb)

@dp.callback_query(F.data == "int")
async def interval(c: CallbackQuery):
    uid = c.from_user.id; L = lim(uid)["min_s"]
    vals = [v for v in (5, 10, 30, 60, 300, 600, 1800, 3600, 21600, 86400, 259200) if L <= v <= MAX_IV]
    rows = [[B(text=fmt_dur(v), callback_data=f"iv:{v}") for v in vals[i:i + 3]] for i in range(0, len(vals), 3)]
    rows.append([B(text="✏️ رقم مخصص", callback_data="ivc")]); rows.append([B(text="🔙 رجوع", callback_data="apm")])
    await edit(c, f"⏱ اختر الفاصل بين كل دورة نشر.\nالحالي: {fmt_dur(eff_iv(user(uid)))}\nأقل فاصل لك: {fmt_dur(L)} — الأقصى: 3 أيام\n"
                  f"⚠️ الفواصل الأطول أأمن لحسابك." + ("" if is_vip(uid) else f"\n💎 VIP يبدأ من {fmt_dur(VIP['min_s'])}"), InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("iv:"))
async def iv(c: CallbackQuery):
    uid = c.from_user.id; sec = min(max(int(c.data[3:]), lim(uid)["min_s"]), MAX_IV)
    q("update users set interval_s=?, interval=? where id=?", (sec, max(1, sec // 60), uid))
    t_, kb_ = apm_view(uid); await edit(c, t_, kb_); await c.answer("✅")

@dp.callback_query(F.data == "ivc")
async def ivc(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.iv)
    await edit(c, f"أرسل الفاصل، مثل: 30ث  أو  5د  أو  2س  أو  1ي (بدون حرف = دقائق)\nأقل شيء {fmt_dur(lim(c.from_user.id)['min_s'])} وأكثر شيء 3 أيام:", back("int")); await c.answer()

@dp.message(S.iv)
async def iv_in(m: Message, state: FSMContext):
    uid = m.from_user.id; sec = parse_dur(m.text)
    if sec is None or sec < lim(uid)["min_s"] or sec > MAX_IV:
        return await m.answer(f"❌ أرسل مثل 30ث أو 5د أو 2س (من {fmt_dur(lim(uid)['min_s'])} إلى 3 أيام).")
    q("update users set interval_s=?, interval=? where id=?", (sec, max(1, sec // 60), uid)); await state.clear()
    t_, kb_ = apm_view(uid); await m.answer(f"✅ تم: كل {fmt_dur(sec)}\n\n" + t_, reply_markup=kb_)

@dp.callback_query(F.data == "accs")
async def accs(c: CallbackQuery):
    rows = []; n_ = q("select count(*) c from accounts where uid=?", (c.from_user.id,)).fetchone()["c"]
    txt = f"📱 حساباتي\n\n🔢 عدد الحسابات: {n_} / {lim(c.from_user.id)['accounts']}\n\n"
    for a in q("select * from accounts where uid=?", (c.from_user.id,)).fetchall():
        txt += f"• {deco(a['name'])} — {deco(a['phone'])}\n"
        rows.append([B(text=f"🗑 حذف {a['phone']}", callback_data=f"ad:{a['id']}")])
    rows.append([B(text="➕ إضافة حساب", callback_data="addacc")]); rows.append([B(text="🔙 رجوع", callback_data="home")])
    await edit(c, txt, InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("ad:"))
async def ad(c: CallbackQuery):
    aid = int(c.data[3:]); a = q("select * from accounts where id=? and uid=?", (aid, c.from_user.id)).fetchone()
    if a:
        await clock_restore(a)
        cl = clients.pop(aid, None)
        if cl: await cl.disconnect()
        q("delete from accounts where id=?", (aid,)); q("delete from groups where acc=?", (aid,))
    await accs(c)

@dp.callback_query(F.data == "addacc")
async def addacc(c: CallbackQuery, state: FSMContext):
    if q("select count(*) c from accounts where uid=?", (c.from_user.id,)).fetchone()["c"] >= lim(c.from_user.id)["accounts"]:
        return await c.answer("وصلت للحد الأقصى للحسابات 💎 رقّي إلى VIP لزيادة الحد", show_alert=True)
    await state.set_state(S.phone); await edit(c, "📞 أرسل رقم الحساب مع رمز الدولة مثل: +964770xxxxxxx", back("accs")); await c.answer()

@dp.message(S.phone)
async def ph(m: Message, state: FSMContext):
    if not login_ok(m.from_user.id): return await m.answer("⛔ محاولات كثيرة.")
    phone = re.sub(r"[^\d+]", "", m.text or "")
    cl = TelegramClient(StringSession(), API_ID, API_HASH); await cl.connect()
    try: sent = await cl.send_code_request(phone)
    except Exception as e:
        await cl.disconnect(); return await m.answer(f"❌ تعذر إرسال الكود: {e}")
    pending[m.from_user.id] = (cl, phone, sent.phone_code_hash); await state.set_state(S.code)
    await m.answer("📩 أرسل الكود **مع فواصل بين الأرقام** مثل 1-2-3-4-5\n(حتى لا يحظره تيليجرام).", parse_mode="Markdown")

async def finish_login(m, state, cl, phone):
    me = await cl.get_me()
    sess = fer.encrypt(cl.session.save().encode()).decode()
    q("insert into accounts(uid,phone,name,session,created) values(?,?,?,?,?)", (m.from_user.id, phone, me.first_name or "acc", sess, time.time()))
    aid = q("select max(id) m from accounts").fetchone()["m"]
    attach_reply(cl, aid, m.from_user.id); clients[aid] = cl
    await notify(f"📱 ربط حساب جديد\n👤 {user_tag(m.from_user.id)}\n📞 {mask(phone)}")
    for d in await cl.get_dialogs(limit=300):
        if d.is_group: q("insert into groups(acc,chat_id,title,sel) values(?,?,?,0)", (aid, d.id, d.name or ""))
    await state.clear(); await m.answer("✅ تم ربط الحساب وتحديث المجموعات.", reply_markup=main_kb(m.from_user.id))

@dp.message(S.code)
async def code(m: Message, state: FSMContext):
    cl, phone, h = pending[m.from_user.id]
    try: await cl.sign_in(phone, re.sub(r"\D", "", m.text or ""), phone_code_hash=h)
    except errors.SessionPasswordNeededError:
        await state.set_state(S.pw); return await m.answer("🔐 أرسل كلمة مرور التحقق بخطوتين:")
    except Exception as e:
        if not login_ok(m.from_user.id):
            await state.clear(); await cl.disconnect(); return await m.answer("⛔ محاولات كثيرة.")
        return await m.answer(f"❌ {e}")
    await finish_login(m, state, cl, phone)

@dp.message(S.pw)
async def pw(m: Message, state: FSMContext):
    cl, phone, _ = pending[m.from_user.id]
    try: await cl.sign_in(password=m.text)
    except Exception as e:
        if not login_ok(m.from_user.id):
            await state.clear(); await cl.disconnect(); return await m.answer("⛔ محاولات كثيرة.")
        return await m.answer(f"❌ {e}")
    try: await m.delete()
    except Exception: pass
    await finish_login(m, state, cl, phone)

@dp.callback_query(F.data == "gcount")
async def gcount(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    uid = c.from_user.id; L = lim(uid)["groups"]
    vals = list(range(1, L + 1)) if L <= 10 else sorted({v for v in (1, 5, 10, 20, 50, 100, 200, 300, 500, 1000) if v < L} | {L})
    rows = [[B(text=str(v), callback_data=f"gn:{v}") for v in vals[i:i + 5]] for i in range(0, len(vals), 5)]
    rows.append([B(text="🔙 رجوع", callback_data="home")])
    await edit(c, f"📥 كم كروب تريد النشر بيهم؟\nالحد الأقصى لك: {L}" + ("" if is_vip(uid) else f" (💎 VIP يوصل لـ {VIP['groups']})") +
                  "\n\nاختر العدد وبعدها تضيف الكروبات.", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("gn:"))
async def gn(c: CallbackQuery):
    q("update users set want_groups=? where id=?", (min(int(c.data[3:]), lim(c.from_user.id)["groups"]), c.from_user.id))
    await show_grp(c, 0)

@dp.callback_query(F.data == "gr")
async def gr(c: CallbackQuery):
    for a in q("select * from accounts where uid=?", (c.from_user.id,)).fetchall():
        cl = await get_client(a)
        if not cl: continue
        old = {r["chat_id"]: r["sel"] for r in q("select chat_id,sel from groups where acc=?", (a["id"],))}
        q("delete from groups where acc=?", (a["id"],))
        for d in await cl.get_dialogs(limit=300):
            if d.is_group: q("insert into groups(acc,chat_id,title,sel) values(?,?,?,?)", (a["id"], d.id, d.name or "", old.get(d.id, 0)))
    await show_grp(c, 0)

@dp.callback_query(F.data.startswith("grp:"))
async def grp(c: CallbackQuery): await show_grp(c, int(c.data[4:]))
async def show_grp(c, p):
    uid = c.from_user.id; cap = grp_cap(uid); n = sel_count(uid)
    gs = q("select g.* from groups g join accounts a on a.id=g.acc where a.uid=? order by g.id", (uid,)).fetchall()
    page = gs[p * 8:(p + 1) * 8]
    rows = [[B(text=f"{'✅' if g['sel'] else '⬜'} {g['title'][:30]}", callback_data=f"gt:{g['id']}:{p}")] for g in page]
    nav = []
    if p > 0: nav.append(B(text="◀️", callback_data=f"grp:{p-1}"))
    if (p + 1) * 8 < len(gs): nav.append(B(text="▶️", callback_data=f"grp:{p+1}"))
    if nav: rows.append(nav)
    rows.append([B(text="🔄 تحديث القائمة", callback_data="gr"), B(text=f"✅ تحديد حتى {cap}", callback_data="ga:1"), B(text="⬜ مسح", callback_data="ga:0")])
    rows.append([B(text="✔️ تم — رجوع للنشر" if n else "🔙 رجوع", callback_data="apm" if n else "home")])
    status = "✅ اكتمل العدد" if n >= cap else f"باقي لك {cap - n}"
    await edit(c, f"📥 اختر الكروبات للنشر ({n}/{cap}) — {status}\nاضغط على الكروب لتفعيله/إيقافه." +
                  ("" if gs else "\n\nما لقيت كروبات. أضف حساب أو اضغط 🔄 تحديث القائمة."), InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("gt:"))
async def gt(c: CallbackQuery):
    _, gid, p = c.data.split(":"); uid = c.from_user.id
    g = q("select g.* from groups g join accounts a on a.id=g.acc where g.id=? and a.uid=?", (int(gid), uid)).fetchone()
    if g:
        if not g["sel"] and sel_count(uid) >= grp_cap(uid):
            return await c.answer(f"وصلت للحد الأقصى ({grp_cap(uid)}). شيل كروب لتضيف غيره" + ("" if is_vip(uid) else " أو فعّل VIP 💎"), show_alert=True)
        q("update groups set sel=1-sel where id=?", (g["id"],))
    await show_grp(c, int(p))

@dp.callback_query(F.data.startswith("ga:"))
async def ga(c: CallbackQuery):
    uid = c.from_user.id
    q("update groups set sel=0 where acc in (select id from accounts where uid=?", (uid,))
    if c.data[3:] == "1":
        for r in q("select g.id from groups g join accounts a on a.id=g.acc where a.uid=? order by g.id limit ?", (uid, grp_cap(uid))).fetchall():
            q("update groups set sel=1 where id=?", (r["id"],))
    await show_grp(c, 0)

REP_MODES = {"present": "💬 فقط إذا أنا داخل تلكرام (هسه اجي)",
             "away": "🌙 فقط إذا أنا خارج تلكرام (الكليشة)",
             "both": "✅ كلاهما"}
def ar_view(uid):
    u = user(uid); reps = rep_list(u); mx = lim(uid)["replies"]; mode = u["reply_mode"] or "both"
    txt = f"💬 الرد بالخاص: {'يعمل' if u['reply_on'] else 'متوقف'} {on(u['reply_on'])}\n\n📝 الكليشات ({len(reps)}/{mx}):\n"
    txt += ("\n".join(f"{i}. {r.replace(chr(10), ' ')[:60]}" for i, r in enumerate(reps, 1)) or "لا يوجد")
    txt += (f"\n\n💬 رد وقت تكون داخل تلكرام: {u['present_text'] or 'هسه اجي 🙏'}\n\n"
            "• خارج تلكرام: يرد بالكليشة فوراً (أقل من نص ثانية).\n• داخل تلكرام: يرد بكلمة قصيرة مثل «هسه اجي».\n"
            "• يرد مرة وحدة لكل محادثة، وإذا سكت الشخص 10 دقائق ثم كتب يرجع يرد. ولا يرد وانت تحاكيه.\n\n⏱ متى يرد؟")
    rows = [[B(text="⏹ إيقاف الرد" if u["reply_on"] else "▶️ تشغيل الرد", callback_data="art")]]
    rows += [[B(text=f"{'🔘' if mode == k else '⚪'} {v}", callback_data=f"arm:{k}")] for k, v in REP_MODES.items()]
    rows.append([B(text="✍️ تغيير رد «هسه اجي»", callback_data="arp")])
    rows.append([B(text=f"➕ إضافة كليشة ({len(reps)}/{mx})", callback_data="arx")])
    if reps: rows.append([B(text="🗑 مسح كل الكليشات", callback_data="arc")])
    rows.append([B(text="🔙 رجوع", callback_data="home")])
    return txt, InlineKeyboardMarkup(inline_keyboard=rows)

async def ar_show(c: CallbackQuery):
    t, kb = ar_view(c.from_user.id); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data == "ar")
async def ar(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    if not rep_list(user(c.from_user.id)): return await arx(c, state)
    await ar_show(c)

@dp.callback_query(F.data == "art")
async def art(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    q("update users set reply_on=1-reply_on where id=?", (c.from_user.id,)); await ar_show(c)

@dp.callback_query(F.data.startswith("arm:"))
async def arm(c: CallbackQuery):
    k = c.data[4:]
    if k in REP_MODES: q("update users set reply_mode=?, reply_on=1 where id=?", (k, c.from_user.id))
    await ar_show(c)

@dp.callback_query(F.data == "arp")
async def arp(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.prs); await edit(c, "✍️ اكتب الكلمة اللي يرد بيها وانت داخل تلكرام، مثل: هسه اجي", back("ar")); await c.answer()

@dp.message(S.prs)
async def prs_in(m: Message, state: FSMContext):
    txt = (m.text or "").strip()[:200]
    if not txt: return await m.answer("أرسل نص الرد.")
    q("update users set present_text=? where id=?", (txt, m.from_user.id)); await state.clear()
    t, kb = ar_view(m.from_user.id); await m.answer("✅ انحفظ.\n\n" + t, reply_markup=kb)

@dp.callback_query(F.data == "arc")
async def arc(c: CallbackQuery, state: FSMContext):
    q("update users set reply_text='', reply_on=0 where id=?", (c.from_user.id,)); await ar(c, state)

@dp.callback_query(F.data == "arx")
async def arx(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; reps = rep_list(user(uid)); mx = lim(uid)["replies"]
    if len(reps) >= mx:
        return await c.answer(f"وصلت للحد ({mx})" + ("" if is_vip(uid) else f" 💎 VIP يسمح بـ {VIP['replies']} كليشات"), show_alert=True)
    await state.set_state(S.rep); await edit(c, "✍️ دز الكليشة (نص الرد الآلي):", back("ar" if reps else "home")); await c.answer()

@dp.message(S.rep)
async def rep_in(m: Message, state: FSMContext):
    uid = m.from_user.id; txt = (m.text or "").strip()
    if not txt: return await m.answer("أرسل نص الكليشة.")
    reps = (rep_list(user(uid)) + [txt])[:lim(uid)["replies"]]
    q("update users set reply_text=? where id=?", (json.dumps(reps, ensure_ascii=False), uid)); await state.clear()
    t, kb = ar_view(uid); await m.answer("✅ انحفظت الكليشة. هسه اختر متى يرد:\n\n" + t, reply_markup=kb)

def adm_only(f):
    names = set(inspect.signature(f).parameters)
    async def w(c, **k):
        if c.from_user.id not in ADMINS: return
        return await f(c, **{x: v for x, v in k.items() if x in names})
    w.__name__ = f.__name__; return w

@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if m.from_user.id in ADMINS: await m.answer("👑 لوحة الأدمن", reply_markup=adm_kb())

def adm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="📊 الإحصائيات", callback_data="st"), B(text="📢 إذاعة", callback_data="bc")],
        [B(text="🔗 الاشتراك الإجباري", callback_data="fs")],
        [B(text="🚫 حظر", callback_data="bn"), B(text="♻️ فك حظر", callback_data="ubn")],
        [B(text="💎 منح VIP", callback_data="gv"), B(text="📦 الباقات", callback_data="pl")],
        [B(text="👋 رسالة الترحيب", callback_data="wl")],
        [B(text="🔍 بحث عن مستخدم", callback_data="ui"), B(text="👥 القوائم", callback_data="ul")],
        [B(text="⚙️ الحدود والإعدادات", callback_data="ls"), B(text="🛡 المشرفين", callback_data="am")],
        [B(text="📤 تصدير المستخدمين", callback_data="ex"), B(text="🛑 إيقاف كل النشر", callback_data="sa")],
        [B(text="📣 قناة الإشعارات", callback_data="lc")],
        [B(text="🛡 حالة الحماية", callback_data="sh"), B(text="🔄 تجديد الحماية", callback_data="sr")],
        [B(text="🎟 أكواد VIP", callback_data="cd"), B(text="📜 السجل", callback_data="lg")],
        [B(text="💾 نسخة احتياطية الآن", callback_data="bk"), B(text="🎨 ملصقات الأزرار", callback_data="ico")],
        [B(text=f"البوت {on(cfg_get('bot_on')=='1')}", callback_data="bt")],
        [B(text="🔙 رجوع", callback_data="home")]])

@dp.callback_query(F.data == "adm")
@adm_only
async def adm(c: CallbackQuery): await edit(c, f"👑 لوحة الأدمن\n{sec_line()}", adm_kb()); await c.answer()

@dp.callback_query(F.data == "st")
@adm_only
async def st(c: CallbackQuery):
    n = lambda sql, a=(): q(sql, a).fetchone()[0]
    now = time.time(); day0 = now - (now + TZ * 3600) % 86400
    await edit(c, (
        f"📊 الإحصائيات\n\n"
        f"👥 الأعضاء: {n('select count(*) from users')} (جدد اليوم: {n('select count(*) from users where joined>=?', (day0,))})\n"
        f"💎 VIP فعّال: {n('select count(*) from users where vip_until>?', (now,))}\n"
        f"🚫 المحظورين: {n('select count(*) from users where banned=1')}\n"
        f"📱 الحسابات: {n('select count(*) from accounts')} (بفترة راحة: {n('select count(*) from accounts where cool_until>?', (now,))})\n"
        f"?? مجموعات مفعّلة: {n('select count(*) from groups where sel=1')}\n"
        f"🚀 نشر فعّال: {n('select count(*) from users where autopost=1')}\n"
        f"📨 رسائل اليوم: {n('select coalesce(sum(n),0) from sent_log where day=?', (today_str(),))} | 7 أيام: {n('select coalesce(sum(n),0) from sent_log where day>=?', (today_str(6),))}\n"
        f"🎟 أكواد غير مستخدمة: {n('select count(*) from codes where used_by=0')}\n\n{sec_line()}"), back("adm")); await c.answer()

@dp.callback_query(F.data == "bt")
@adm_only
async def bt(c: CallbackQuery):
    q("insert or replace into cfg values('bot_on',?)", ("0" if cfg_get("bot_on") == "1" else "1",)); await adm(c)

@dp.callback_query(F.data == "fs")
@adm_only
async def fs(c: CallbackQuery):
    rows = [[B(text=f"🗑 {r['chat']}", callback_data=f"fd:{r['chat']}")] for r in q("select chat from channels")]
    rows += [[B(text="➕ إضافة قناة", callback_data="fa")], [B(text="🔙 رجوع", callback_data="adm")]]
    await edit(c, "🔗 قنوات الاشتراك الإجباري (البوت لازم أدمن بالقناة):", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("fd:"))
@adm_only
async def fd(c: CallbackQuery): q("delete from channels where chat=?", (c.data[3:],)); alog(c.from_user.id, f"حذف قناة {c.data[3:]}"); await fs(c)

@dp.callback_query(F.data == "fa")
@adm_only
async def fa(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.ch); await edit(c, "أرسل يوزر القناة مثل @channel\nأو للقناة الخاصة: آيدي القناة ثم مسافة ثم رابط الدعوة\nمثال: -1001234567890 https://t.me/+abcd", back("fs")); await c.answer()

@dp.message(S.ch)
async def ch_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    parts = (m.text or "").split()
    if not parts: return
    link = parts[1] if len(parts) > 1 else "https://t.me/" + parts[0].lstrip("@")
    q("insert or replace into channels(chat,link) values(?,?)", (parts[0], link)); alog(m.from_user.id, f"إضافة قناة {parts[0]}")
    await state.clear(); await m.answer("✅ تمت الإضافة.", reply_markup=adm_kb())

@dp.callback_query(F.data == "bc")
@adm_only
async def bc(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="👥 الجميع", callback_data="bcw:all")],
        [B(text="💎 VIP فقط", callback_data="bcw:vip"), B(text="🆓 المجاني فقط", callback_data="bcw:free")],
        [B(text="🔙 رجوع", callback_data="adm")]])
    await edit(c, "📢 اختر الفئة المستهدفة بالإذاعة:", kb); await c.answer()

@dp.callback_query(F.data.startswith("bcw:"))
@adm_only
async def bcw(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.bc); await state.update_data(target=c.data[4:])
    await edit(c, "📢 أرسل رسالة الإذاعة (نص أو صورة أو أي وسائط):", back("bc")); await c.answer()

@dp.message(S.bc)
async def bc_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    t = (await state.get_data()).get("target", "all"); await state.clear()
    cond = {"all": "", "vip": " and vip_until>?", "free": " and vip_until<=?"}[t]
    ids = [r["id"] for r in q("select id from users where banned=0" + cond, () if t == "all" else (time.time(),))]
    await m.answer(f"⏳ جاري الإرسال إلى {len(ids)} مستخدم...")
    ok = 0
    for uid in ids:
        try: await m.copy_to(uid); ok += 1
        except Exception: pass
        await asyncio.sleep(0.06)
    alog(m.from_user.id, f"إذاعة ({t}) وصلت {ok}/{len(ids)}"); await notify(f"📢 إذاعة ({t}): وصلت إلى {ok} من {len(ids)}")
    await m.answer(f"✅ وصلت إلى {ok} من {len(ids)}.", reply_markup=adm_kb())

@dp.callback_query(F.data.in_({"bn", "ubn"}))
@adm_only
async def bn(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.ban if c.data == "bn" else S.unban); await edit(c, "أرسل آيدي المستخدم:", back("adm")); await c.answer()

@dp.message(S.ban)
@dp.message(S.unban)
async def ban_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS or not (m.text or "").isdigit(): return
    banned = (await state.get_state()) == S.ban.state
    q("update users set banned=?, autopost=0 where id=?", (int(banned), int(m.text))); alog(m.from_user.id, f"{'حظر' if banned else 'فك حظر'} {m.text}"); await notify(f"{'🚫 حظر' if banned else '♻️ فك حظر'} المستخدم {user_tag(int(m.text))}"); await state.clear()
    await m.answer("✅ تم.", reply_markup=adm_kb())

@dp.callback_query(F.data == "vipinfo")
async def vipinfo(c: CallbackQuery):
    txt = (f"💎 مزايا الـ VIP\n\n"
           f"• حتى {VIP['accounts']} حسابات (المجاني: {FREE['accounts']})\n"
           f"• حتى {VIP['groups']} كروبات (المجاني: {FREE['groups']})\n"
           f"• فاصل نشر من {fmt_dur(VIP['min_s'])} إلى 3 أيام (المجاني من {fmt_dur(FREE['min_s'])})\n"
           f"• {VIP['replies']} كليشات رد بالخاص (المجاني: {FREE['replies']})\n"
           f"• 🎯 رادار الكلمات\n\n"
           f"حالتك: {vip_text(c.from_user.id)}")
    kb = [[B(text="⭐ الترقية لـ VIP", callback_data="vipbuy")], [B(text="🎁 احصل على VIP مجاناً", callback_data="vipfree")], [B(text="🎟 تفعيل كود", callback_data="rc")],
          [B(text="🧑‍💻 تواصل مع المالك", url="https://t.me/" + OWNER.lstrip("@"))],
          [B(text="🔙 رجوع", callback_data="home")]]
    await edit(c, txt, InlineKeyboardMarkup(inline_keyboard=kb)); await c.answer()

@dp.callback_query(F.data == "vipbuy")
async def vipbuy(c: CallbackQuery):
    uid = c.from_user.id; plans = q("select * from plans order by days").fetchall()
    txt = (f"💎 اشتراك VIP\nحالتك: {vip_text(uid)}\n\n📦 الباقات (بالنجوم أو المحفظة):\n" +
           ("\n".join(f"• {p['name']} ({p['days']} يوم) — {p['price']}" for p in plans) or "لا توجد باقات حالياً") +
           f"\n\n✨ مزايا VIP:\n• حتى {VIP['groups']} كروبات (المجاني {FREE['groups']})\n"
           f"• فاصل نشر من {fmt_dur(VIP['min_s'])} إلى 3 أيام (المجاني من {fmt_dur(FREE['min_s'])})\n"
           f"• {VIP['replies']} كليشات رد بالخاص (المجاني {FREE['replies']})\n• {VIP['posts']} رسائل نشر (المجاني {FREE['posts']})\n• حتى {VIP['accounts']} حسابات\n\nاختر باقة أو تواصل مع المالك للتفعيل:")
    rows = [[B(text=f"💎 {p['name']} — {p['price']}", callback_data=f"vp:{p['id']}")] for p in plans]
    rows.append([B(text="🧑‍💻 تواصل مع المالك للتفعيل", url="https://t.me/" + OWNER.lstrip("@"))])
    rows.append([B(text="🎟 تفعيل كود", callback_data="rc")]); rows.append([B(text="🔙 رجوع", callback_data="home")])
    await edit(c, txt, InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("vp:"))
async def vp(c: CallbackQuery):
    p = q("select * from plans where id=?", (int(c.data[3:]),)).fetchone()
    if not p: return await c.answer("الباقة غير موجودة", show_alert=True)
    sup = OWNER; rows = []
    if sup: rows.append([B(text="🧑‍💻 تواصل للدفع والتفعيل", url="https://t.me/" + sup.lstrip("@"))])
    rows.append([B(text="🔙 رجوع", callback_data="vipbuy")])
    await edit(c, f"💎 باقة {p['name']}\n⏳ المدة: {p['days']} يوم\n💰 السعر: {p['price']}\n\n"
                  f"لإتمام الاشتراك تواصل مع المطور وأرسل له آيديك:\n{c.from_user.id}\nوسيتم التفعيل فوراً.",
               InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data == "vipfree")
async def vipfree(c: CallbackQuery):
    me = await bot.get_me()
    await edit(c, f"🎁 احصل على VIP مجاناً!\n\nشارك رابطك، وعن كل شخص جديد ينضم عبره تحصل على {cfg_get('ref_days', '1')} يوم VIP:\n\n"
                  f"https://t.me/{me.username}?start=ref_{c.from_user.id}\n\nللاستفسار تواصل مع المالك: {OWNER}", back("home")); await c.answer()

@dp.callback_query(F.data == "gv")
@adm_only
async def gv(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.grant)
    await edit(c, "💎 أرسل: آيدي_المستخدم عدد_الأيام\nمثال: 123456789 30\n(0 لإلغاء الاشتراك)", back("adm")); await c.answer()

@dp.message(S.grant)
async def grant_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    try: a, b = (m.text or "").split(); uid, d = int(a), int(b)
    except ValueError: return await m.answer("الصيغة: 123456789 30")
    user(uid); alog(m.from_user.id, f"VIP {d} يوم للمستخدم {uid}"); await notify(f"💎 تعديل VIP: {d} يوم للمستخدم {user_tag(uid)}")
    if d == 0: q("update users set vip_until=0 where id=?", (uid,))
    else: add_vip(uid, d)
    await state.clear(); await m.answer("✅ تم.", reply_markup=adm_kb())
    if d > 0:
        try: await bot.send_message(uid, f"🎉 تم تفعيل VIP لمدة {d} يوم!")
        except Exception: pass

@dp.callback_query(F.data == "pl")
@adm_only
async def pl(c: CallbackQuery):
    rows = [[B(text=f"🗑 {p['name']} ({p['days']}ي) {p['price']}", callback_data=f"pd:{p['id']}")] for p in q("select * from plans order by days")]
    rows += [[B(text="➕ إضافة باقة", callback_data="pa")], [B(text="🔙 رجوع", callback_data="adm")]]
    await edit(c, "📦 باقات VIP (اضغط للحذف):", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("pd:"))
@adm_only
async def pd(c: CallbackQuery): q("delete from plans where id=?", (int(c.data[3:]),)); alog(c.from_user.id, "حذف باقة"); await pl(c)

@dp.callback_query(F.data == "pa")
@adm_only
async def pa(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.plan); await edit(c, "أرسل الباقة بهذه الصيغة:\nالاسم|عدد الأيام|السعر\nمثال: شهري|30|15$", back("pl")); await c.answer()

@dp.message(S.plan)
async def plan_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    try: n, d, p = [x.strip() for x in (m.text or "").split("|")]; d = int(d)
    except ValueError: return await m.answer("الصيغة: الاسم|الأيام|السعر")
    q("insert into plans(name,days,price) values(?,?,?)", (n, d, p)); alog(m.from_user.id, f"إضافة باقة {n}"); await state.clear(); await m.answer("✅ تمت الإضافة.", reply_markup=adm_kb())

@dp.callback_query(F.data == "wl")
@adm_only
async def wl(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.wel)
    await edit(c, "👋 أرسل رسالة الترحيب:\n• تقدر تحط ملصقات مميزة وتنسيق (عريض، مائل...) داخل النص وينحفظ كما هو\n• صورة مع تعليق (التعليق = النص)\n• أو نص فقط\n• أو كلمة «افتراضي» لإعادة الترحيب الأصلي", back("adm")); await c.answer()

@dp.message(S.wel)
async def wel_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    ej = lambda es: json.dumps([e.model_dump(exclude_none=True) for e in (es or [])], ensure_ascii=False)
    if m.photo:
        cfg_set("welcome_photo", m.photo[-1].file_id)
        if m.caption: cfg_set("welcome_text", m.caption); cfg_set("welcome_ents", ej(m.caption_entities))
    elif (m.text or "").strip() == "افتراضي": cfg_set("welcome_photo", ""); cfg_set("welcome_text", DEFAULT_WELCOME); cfg_set("welcome_ents", "[]")
    elif m.text: cfg_set("welcome_text", m.text); cfg_set("welcome_ents", ej(m.entities))
    await state.clear(); await m.answer("✅ تم حفظ الترحيب (جرّب /start).", reply_markup=adm_kb())

@dp.callback_query(F.data == "sp")
@adm_only
async def sp(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.sup); await edit(c, "أرسل يوزر حسابك للتواصل، مثل @username", back("adm")); await c.answer()

@dp.message(S.sup)
async def sup_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    cfg_set("support", (m.text or "").strip()); await state.clear(); await m.answer("✅ تم.", reply_markup=adm_kb())

GUIDE_TEXT = ("📖 الدليل - خطوة بخطوة\n\n"
    "1️⃣ 📱 حساباتي: أضف حسابك (رقم الهاتف ثم الكود).\n"
    "2️⃣ 🚀 النشر التلقائي: اختر كم كروب تريد ثم أضفها (المجاني 4، VIP 10).\n"
    "3️⃣ ✍️ اكتب نص الرسالة، وحدد ⏱ فاصل النشر (VIP من 5 ثواني حتى 3 أيام).\n"
    "4️⃣ ▶️ شغّل النشر. وتقدر تحدد ⏰ وقت بدء.\n\n"
    "💬 رد بالخاص: دز الكليشة واختر متى يرد (حتى لو موجود وما منتبه / فقط إذا خارج تلكرام / كلاهما).\n"
    "🕐 الساعة واليوم: تفعيل اختياري يظهر أعلى القائمة.\n"
    "💎 VIP: من زر تفعيل VIP أو بكود تفعيل.\n"
    "• كل الأوقات بتوقيت العراق 🇮🇶")

@dp.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()

@dp.callback_query(F.data == "guide")
async def guide(c: CallbackQuery):
    await edit(c, GUIDE_TEXT, back("home")); await c.answer()

@dp.callback_query(F.data == "apm")
async def apm(c: CallbackQuery, state: FSMContext):
    await state.clear(); uid = c.from_user.id
    if not q("select 1 from accounts where uid=?", (uid,)).fetchone(): return await c.answer("اربط حسابك أولاً من زر 📱 حساباتي", show_alert=True)
    if not sel_count(uid): return await gcount(c)
    t, kb = apm_view(uid); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data == "vipm")
async def vipm(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🎟 تفعيل كود", callback_data="rc")],
        [B(text="💎 استكشف مزايا VIP", callback_data="vipinfo")],
        [B(text="⭐ الترقية لـ VIP", callback_data="vipbuy"), B(text="🎁 احصل على VIP مجاناً", callback_data="vipfree")],
        [B(text="🔙 رجوع", callback_data="home")]])
    await edit(c, f"💎 VIP: {vip_text(c.from_user.id)}", kb); await c.answer()

@dp.callback_query(F.data == "qh")
async def qh(c: CallbackQuery):
    u = user(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [tog("الراحة الليلية", "qt", u["quiet_on"])],
        [tog("إظهار ص / م", "qa", u["show_ampm"])],
        [B(text="⏰ تحديد الساعات", callback_data="qs")], [B(text="🔙 رجوع", callback_data="apm")]])
    ap = u["show_ampm"]
    await edit(c, f"🌙 البوت يوقف النشر تلقائياً بهذه الساعات (حماية أكثر للحساب).\nالحالية: من {hm(u['quiet_from'], u['quiet_from_m'] or 0, ap)} إلى {hm(u['quiet_to'], u['quiet_to_m'] or 0, ap)} (بتوقيت العراق)", kb); await c.answer()

@dp.callback_query(F.data == "qa")
async def qa(c: CallbackQuery):
    q("update users set show_ampm=1-show_ampm where id=?", (c.from_user.id,)); await qh(c)

@dp.callback_query(F.data == "qt")
async def qt(c: CallbackQuery):
    q("update users set quiet_on=1-quiet_on where id=?", (c.from_user.id,)); await qh(c)

@dp.callback_query(F.data == "qs")
async def qs(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.quiet); await edit(c, "أرسل الوقت بنظام 12 ساعة (بتوقيت العراق) مثل: 11:30م-6:15ص\nأو اكتب 1-7 (بدون ص/م تُحسب صباحاً)", back("qh")); await c.answer()

@dp.message(S.quiet)
async def quiet_in(m: Message, state: FSMContext):
    parts = (m.text or "").split("-")
    a, b = (parse_t(parts[0]), parse_t(parts[1])) if len(parts) == 2 else (None, None)
    if a is None or b is None: return await m.answer("الصيغة: 11:30م-6:15ص  أو  1-7")
    q("update users set quiet_from=?, quiet_from_m=?, quiet_to=?, quiet_to_m=?, quiet_on=1 where id=?", (a[0], a[1], b[0], b[1], m.from_user.id))
    await state.clear(); await m.answer("✅ تم تفعيل ساعات الراحة.", reply_markup=main_kb(m.from_user.id))

def parse_raw(s):
    r = re.fullmatch(r"\s*(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*(ص|م|am|pm)?\s*", s, re.I)
    if not r: return None
    n, mi = int(r[1]), int(r[2] or 0)
    if n > 23 or mi > 59: return None
    return n, mi, (r[3] or "").lower()

def to24(n, mi, p):
    if n > 12: return n, mi
    return (n % 12 + 12 if p in ("م", "pm") else n % 12), mi

async def schedule_start(msg, state, uid, h, mi):
    u = user(uid)
    if not u["post_text"]:
        await state.clear(); return await msg.answer("اكتب نص الرسالة أولاً ✍️")
    if not q("select 1 from accounts where uid=?", (uid,)).fetchone():
        await state.clear(); return await msg.answer("اربط حسابك أولاً من زر 📱 حساباتي")
    tgt = h * 3600 + mi * 60; nows = (time.time() + TZ * 3600) % 86400
    q("update users set start_at=?, autopost=1 where id=?", (time.time() + (tgt - nows) % 86400, uid))
    start_loop(uid); await state.clear()
    await msg.answer(f"✅ البوت يباشر النشر {'غداً' if tgt < nows else 'اليوم'} الساعة {hm(h, mi)} بتوقيت العراق.", reply_markup=main_kb(uid))

@dp.callback_query(F.data == "sts")
async def sts(c: CallbackQuery, state: FSMContext):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    await state.set_state(S.sat)
    await edit(c, "⏰ أرسل الساعة التي تريد أن يبدأ فيها النشر (بتوقيت العراق)، مثل: 8:30 أو 9\nبعدها تختار ص أو م.", back("apm")); await c.answer()

@dp.message(S.sat)
async def sat_in(m: Message, state: FSMContext):
    r = parse_raw(m.text or "")
    if r is None: return await m.answer("الصيغة: 8:30  أو  9  أو  9:15م")
    n, mi, p = r
    if p or n > 12 or n == 0:
        h, mi = to24(n, mi, p); return await schedule_start(m, state, m.from_user.id, h, mi)
    await state.update_data(h=n, mi=mi)
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="☀️ ص (صباحاً)", callback_data="sp:am"), B(text="🌙 م (مساءً)", callback_data="sp:pm")]])
    await m.answer(f"الساعة {n}:{mi:02d} — صباحاً لو مساءً؟ (بتوقيت العراق)", reply_markup=kb)

@dp.callback_query(F.data.startswith("sp:"))
async def sp(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if "h" not in d: return await c.answer("انتهت العملية، اضغط وقت البدء من جديد", show_alert=True)
    h, mi = to24(d["h"], d["mi"], "م" if c.data == "sp:pm" else "ص")
    await c.answer(); await schedule_start(c.message, state, c.from_user.id, h, mi)

@dp.callback_query(F.data == "sx")
async def sx(c: CallbackQuery):
    q("update users set start_at=0, autopost=0 where id=?", (c.from_user.id,)); t, kb = apm_view(c.from_user.id); await edit(c, t, kb); await c.answer()

def attach_radar(cl, acc_id, uid):
    @cl.on(events.NewMessage(incoming=True, func=lambda e: not e.is_private and bool(e.raw_text)))
    async def _r(ev):
        u = user(uid)
        if not u["radar_on"] or not u["keywords"] or not is_vip(uid): return
        txt = ev.raw_text.lower()
        hit = next((k for k in (x.strip().lower() for x in u["keywords"].split(",")) if k and k in txt), None)
        if not hit: return
        if not q("select 1 from groups where acc=? and chat_id=? and sel=1", (acc_id, ev.chat_id)).fetchone(): return
        if not login_ok(("radar", uid), 20, 3600): return
        s_, chat = await ev.get_sender(), await ev.get_chat()
        who = f"@{s_.username}" if getattr(s_, "username", None) else f"id {ev.sender_id}"
        await alert(uid, f"🎯 رادار الكلمات: «{hit}»\n📍 {getattr(chat, 'title', '')}\n👤 {who}\n\n{ev.raw_text[:300]}")

@dp.callback_query(F.data == "rd")
async def rd(c: CallbackQuery):
    uid = c.from_user.id; u = user(uid)
    if not is_vip(uid):
        return await edit(c, "🎯 رادار الكلمات ميزة VIP: ينبهك فوراً عند ظهور كلمات تحددها (مثل «مطلوب») بمجموعاتك.",
                          InlineKeyboardMarkup(inline_keyboard=[[B(text="⭐ الترقية لـ VIP", callback_data="vipbuy")], [B(text="🔙 رجوع", callback_data="home")]]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[tog("الرادار", "rdt", u["radar_on"])],
                                               [B(text="✏️ تحديد الكلمات", callback_data="rdk")], [B(text="🔙 رجوع", callback_data="home")]])
    await edit(c, f"🎯 رادار الكلمات\n\nالكلمات: {u['keywords'] or 'غير محددة'}", kb); await c.answer()

@dp.callback_query(F.data == "rdt")
async def rdt(c: CallbackQuery):
    if is_vip(c.from_user.id): q("update users set radar_on=1-radar_on where id=?", (c.from_user.id,))
    await rd(c)

@dp.callback_query(F.data == "rdk")
async def rdk(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.kw); await edit(c, "أرسل الكلمات مفصولة بفاصلة، مثل: مطلوب، أبحث عن، سعر", back("rd")); await c.answer()

@dp.message(S.kw)
async def kw_in(m: Message, state: FSMContext):
    k = ",".join(x.strip() for x in re.split(r"[,،\n]", m.text or "") if x.strip())[:500]
    q("update users set keywords=?, radar_on=1 where id=?", (k, m.from_user.id)); await state.clear()
    await m.answer("✅ تم تفعيل الرادار.", reply_markup=main_kb(m.from_user.id))

@dp.callback_query(F.data == "pm")
async def pm(c: CallbackQuery):
    u = user(c.from_user.id); has = bool(u["media_path"] and os.path.exists(u["media_path"]))
    rows = [[B(text="🖼 رفع صورة/فيديو", callback_data="pms")]]
    if has: rows.append([B(text="🗑 حذف الوسائط", callback_data="pmd")])
    rows.append([B(text="🔙 رجوع", callback_data="home")])
    await edit(c, f"🖼 الوسائط: {'موجودة ✅' if has else 'لا يوجد'}\nتُرسل مع نص الرسالة كتعليق (الحد 20MB).", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data == "pms")
async def pms(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.media); await edit(c, "أرسل صورة أو فيديو:", back("pm")); await c.answer()

def rm_media(uid):
    for ext in ("jpg", "mp4"):
        f = f"media/{uid}.{ext}"
        if os.path.exists(f): os.remove(f)
    q("update users set media_path='' where id=?", (uid,))

@dp.callback_query(F.data == "pmd")
async def pmd(c: CallbackQuery): rm_media(c.from_user.id); await pm(c)

@dp.message(S.media)
async def media_in(m: Message, state: FSMContext):
    if m.photo: obj, ext = m.photo[-1], "jpg"
    elif m.video: obj, ext = m.video, "mp4"
    else: return await m.answer("أرسل صورة أو فيديو.")
    os.makedirs("media", exist_ok=True); rm_media(m.from_user.id)
    path = f"media/{m.from_user.id}.{ext}"
    try: await bot.download(obj, destination=path)
    except Exception as e: return await m.answer(f"❌ تعذر التحميل (الحد 20MB): {e}")
    q("update users set media_path=? where id=?", (path, m.from_user.id)); await state.clear()
    await m.answer("✅ تم حفظ الوسائط.", reply_markup=main_kb(m.from_user.id))

@dp.callback_query(F.data == "sc")
async def sc(c: CallbackQuery):
    u = user(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text=f"☀️ نص الصباح (5→16) {'✅' if u['text_am'] else '—'}", callback_data="sca")],
        [B(text=f"🌙 نص المساء (16→5) {'✅' if u['text_pm'] else '—'}", callback_data="scp")],
        [B(text="🗑 مسح الجدولة", callback_data="scx")], [B(text="🔙 رجوع", callback_data="home")]])
    await edit(c, "🕐 جدولة النصوص (بتوقيت بغداد)\nكل فترة لها نص خاص، وإذا ما حددت نصاً للفترة يُستخدم النص الرئيسي.", kb); await c.answer()

@dp.callback_query(F.data.in_({"sca", "scp"}))
async def sc_set(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.sam if c.data == "sca" else S.spm); await edit(c, "أرسل النص:", back("sc")); await c.answer()

@dp.message(S.sam)
@dp.message(S.spm)
async def sc_in(m: Message, state: FSMContext):
    col = "text_am" if (await state.get_state()) == S.sam.state else "text_pm"
    q(f"update users set {col}=? where id=?", (m.text or "", m.from_user.id)); await state.clear()
    await m.answer("✅ تم.", reply_markup=main_kb(m.from_user.id))

@dp.callback_query(F.data == "scx")
async def scx(c: CallbackQuery):
    q("update users set text_am='', text_pm='' where id=?", (c.from_user.id,)); await sc(c)

@dp.callback_query(F.data == "ms")
async def ms(c: CallbackQuery):
    uid = c.from_user.id; today = today_str()
    t = q("select coalesce(sum(n),0) s from sent_log where uid=? and day=?", (uid, today)).fetchone()["s"]
    w = q("select coalesce(sum(n),0) s from sent_log where uid=? and day>=?", (uid, today_str(6))).fetchone()["s"]
    rr = q("select count(*) c from replied r join accounts a on a.id=r.acc where a.uid=?", (uid,)).fetchone()["c"]
    txt = f"📈 إحصائياتك\n\n• اليوم: {t} رسالة\n• آخر 7 أيام: {w} رسالة\n• 💬 ردود آلية بالخاص (آخر 7 أيام): {rr} شخص\n\n"
    for a in q("select a.*, coalesce(l.n,0) as n2 from accounts a left join sent_log l on l.acc=a.id and l.day=? where a.uid=?", (today, uid)):
        txt += f"• {deco(a['phone'])}: {a['n2']}/{acc_cap(a, uid)} {'⏸ فترة راحة' if (a['cool_until'] or 0) > time.time() else ''}\n"
    await edit(c, txt, back("home")); await c.answer()

@dp.callback_query(F.data == "rc")
async def rc(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.redeem); await edit(c, "🎟 أرسل كود التفعيل:", back("home")); await c.answer()

@dp.message(S.redeem)
async def rc_in(m: Message, state: FSMContext):
    uid = m.from_user.id
    if not login_ok(("rc", uid), 10, 3600):
        await state.clear(); return await m.answer("⛔ محاولات كثيرة.")
    code = (m.text or "").strip().upper()
    r = q("select * from codes where code=? and used_by=0", (code,)).fetchone()
    if not r or q("update codes set used_by=?, used_at=? where code=? and used_by=0", (uid, time.time(), code)).rowcount != 1:
        return await m.answer("❌ الكود غير صحيح أو مستخدم. أرسل كوداً آخر أو /start للإلغاء.")
    add_vip(uid, r["days"]); await state.clear(); await notify(f"🎟 تفعيل كود VIP: {user_tag(uid)} ({r['days']} يوم)")
    await m.answer(f"🎉 تم تفعيل VIP لمدة {r['days']} يوم!", reply_markup=main_kb(uid))

@dp.callback_query(F.data == "cd")
@adm_only
async def cd(c: CallbackQuery):
    n = lambda w: q(f"select count(*) n from codes where used_by{w}0").fetchone()["n"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="➕ توليد أكواد", callback_data="cdg")], [B(text="📋 غير المستخدمة", callback_data="cdl")], [B(text="🔙 رجوع", callback_data="adm")]])
    await edit(c, f"🎟 أكواد VIP\n\nغير مستخدمة: {n('=')}\nمستخدمة: {n('!=')}", kb); await c.answer()

@dp.callback_query(F.data == "cdg")
@adm_only
async def cdg(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.gen); await edit(c, "أرسل: عدد_الأكواد عدد_الأيام\nمثال: 5 30 (حتى 50 كود)\nأو أرسل عدد الأيام فقط لكود واحد، مثل: 90\n(كل كود يستخدمه شخص واحد فقط)", back("cd")); await c.answer()

@dp.message(S.gen)
async def gen_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    try: p_ = [int(x) for x in (m.text or "").split()]; n, d = (1, p_[0]) if len(p_) == 1 else p_; assert 1 <= n <= 50 and 1 <= d <= 36500
    except Exception: return await m.answer("الصيغة: 5 30")
    codes = ["VIP-" + secrets.token_hex(4).upper() for _ in range(n)]
    for cd_ in codes: q("insert into codes(code,days,created) values(?,?,?)", (cd_, d, time.time()))
    alog(m.from_user.id, f"توليد {n} كود ({d} يوم)"); await state.clear()
    await m.answer(f"✅ {n} كود لمدة {d} يوم (كل كود لشخص واحد فقط):\n\n" + "\n".join(codes), reply_markup=adm_kb())

@dp.callback_query(F.data == "cdl")
@adm_only
async def cdl(c: CallbackQuery):
    rows = q("select * from codes where used_by=0 order by created desc limit 40").fetchall()
    await edit(c, "📋 الأكواد غير المستخدمة:\n\n" + ("\n".join(f"{r['code']} — {r['days']}ي" for r in rows) or "لا يوجد"), back("cd")); await c.answer()

@dp.callback_query(F.data == "lg")
@adm_only
async def lg(c: CallbackQuery):
    rows = q("select * from admin_log order by id desc limit 20").fetchall()
    await edit(c, "📜 آخر العمليات:\n\n" + ("\n".join(f"{time.strftime('%m-%d %I:%M %p', time.gmtime(r['ts'] + TZ * 3600))} | {r['admin']} | {r['action']}" for r in rows) or "لا يوجد"), back("adm")); await c.answer()

@dp.callback_query(F.data == "clk")
async def clk(c: CallbackQuery, state: FSMContext):
    await state.clear(); uid = c.from_user.id; u = user(uid)
    rows = ([[B(text="❌ إيقاف", callback_data="clkoff")], [B(text="🔄 تغيير الصيغة", callback_data="clkf")]] if u["clock_on"]
            else [[B(text="✅ تفعيل", callback_data="clkf")]]) + [[B(text="🔙 رجوع", callback_data="home")]]
    await edit(c, f"🕐 الساعة\n\n{clock_line(uid)}\n\nيظهر الوقت بجانب اسم حسابك المربوط بتلكرام ويتحدّث كل دقيقة، وتكدر توقفه بأي وقت ويرجع اسمك الأصلي.\n\nالحالة: {'مفعّل ✅' if u['clock_on'] else 'غير مفعّل'}", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data == "clkf")
async def clkf(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="☀️🌙 مع ص / م", callback_data="clks:1")], [B(text="⏭ تخطي (بدون ص / م)", callback_data="clks:0")],
                                               [B(text="🔙 رجوع بدون تفعيل", callback_data="clk")]])
    await edit(c, "اختر صيغة الوقت:", kb); await c.answer()

@dp.callback_query(F.data.startswith("clks:"))
async def clks(c: CallbackQuery):
    uid = c.from_user.id
    if not has_acc(uid): return await c.answer(NOACC, show_alert=True)
    q("update users set clock_on=1, show_ampm=? where id=?", (int(c.data[5:]), uid)); u = user(uid); ok = 0
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        try: ok += bool(await clock_apply(acc, u))
        except Exception as e: logging.warning("clock apply %s", e)
    await edit(c, main_text(uid), main_kb(uid))
    await c.answer("✅ تم، الوقت صار بجانب اسم حسابك" if ok else "✅ تم التفعيل، يظهر الوقت خلال دقيقة", show_alert=True)

@dp.callback_query(F.data == "clkoff")
async def clkoff(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; q("update users set clock_on=0 where id=?", (uid,))
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        if user(uid)["anim_style"]: await clock_apply(acc, user(uid))
        else: await clock_restore(acc)
    await clk(c, state)

ANIM = {"shake": ["⟪ {n} ⟫", "⟫ {n} ⟪"], "spark": ["✦ {n}", "{n} ✦", "✧ {n} ✧", "{n}"],
        "heart": ["❤ {n}", "💛 {n}", "💚 {n}", "💙 {n}"], "wave": ["{n} ˙", "˙ {n} ˙", "˙˙ {n}", "˙ {n} ˙"]}
ANIM_NAMES = {"": "مغلق", "shake": "اهتزاز", "spark": "لمعان", "heart": "قلوب", "wave": "موجة"}

@dp.callback_query(F.data == "anm")
async def anm(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    cur = user(c.from_user.id)["anim_style"] or ""
    kb = [[B(text=f"{'🔘' if cur == k else '⚪'} {v}", callback_data=f"anm:{k or 'off'}")] for k, v in ANIM_NAMES.items()] + [[B(text="🔙 رجوع", callback_data="clk")]]
    await edit(c, "✨ اسم متحرك\n\nاسمك بتلكرام يتبدّل كل دقيقة بين شكلين أو أكثر (اهتزاز، لمعان، قلوب، موجة)، ويكدر يجتمع مع الساعة.\n"
                  "⚠️ تيليجرام ما يسمح بتحديث أسرع من دقيقة، فهو تبديل مو حركة سلسة. وإيقافه يرجع اسمك الأصلي.", InlineKeyboardMarkup(inline_keyboard=kb)); await c.answer()

@dp.callback_query(F.data.startswith("anm:"))
async def anm_set(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; k = c.data[4:]; k = "" if k == "off" else k
    q("update users set anim_style=? where id=?", (k, uid)); u = user(uid)
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        try:
            if k or u["clock_on"]: await clock_apply(acc, u)
            else: await clock_restore(acc)
        except Exception as e: logging.warning("anim %s", e)
    await clk(c, state)

clock_last = {}
clock_wait = {}; clock_err = {}
async def clock_apply(acc, u):
    cl = await get_client(acc)
    if not cl: return False
    if not acc["name_set"]:
        me = await cl.get_me()
        q("update accounts set orig_first=?, orig_last=?, name_set=1 where id=?", (me.first_name or "", me.last_name or "", acc["id"]))
        acc = q("select * from accounts where id=?", (acc["id"],)).fetchone()
    t = time.gmtime(time.time() + TZ * 3600)
    first = (acc["orig_first"] or "-")[:64]; last = acc["orig_last"] or ""
    if u["clock_on"]:
        ck = deco(hm(t.tm_hour, t.tm_min, bool(u["show_ampm"])))
        last = ((acc["orig_last"][:max(0, 63 - len(ck))] + " ") if acc["orig_last"] else "") + ck
    fr = ANIM.get(u["anim_style"] or "")
    if fr: first = fr[int(time.time() // 60) % len(fr)].format(n=(acc["orig_first"] or "-")[:50]).strip()[:64]
    st = status_now(u)
    if st: first = (st[1] + " " + first)[:64]
    last = (first, last)
    if clock_last.get(acc["id"]) == last: return True
    if time.time() < clock_wait.get(acc["id"], 0): return False
    try: await cl(UpdateProfileRequest(first_name=last[0], last_name=last[1]))
    except errors.FloodWaitError as e:
        clock_wait[acc["id"]] = time.time() + e.seconds + 5; return False
    except errors.NameNotModifiedError: pass
    clock_last[acc["id"]] = last
    return True

async def clock_restore(acc):
    if not acc["name_set"]: return
    try:
        cl = await get_client(acc)
        if cl: await cl(UpdateProfileRequest(first_name=acc["orig_first"] or "-", last_name=acc["orig_last"] or ""))
    except Exception as e: logging.warning("clock restore %s", e)
    q("update accounts set name_set=0 where id=?", (acc["id"],)); clock_last.pop(acc["id"], None)

async def clock_loop():
    for x in q("select id from users where anim_style!=''").fetchall():
        q("update users set anim_style='' where id=?", (x["id"],))
        try: await refresh_names(x["id"])
        except Exception as e: logging.warning("anim cleanup %s", e)
    while True:
        await asyncio.sleep(60 - time.time() % 60 + 1)
        for x in q("select id from users where status_mode!='' and status_until>0 and status_until<?", (time.time(),)).fetchall():
            q("update users set status_mode='', status_until=0 where id=?", (x["id"],)); await refresh_names(x["id"])
            try: await bot.send_message(x["id"], "⏰ انتهى وضع الحالة ورجع اسمك وردودك الطبيعية.")
            except Exception: pass
        for u in q("select * from users where (clock_on=1 or anim_style!='' or status_mode!='') and banned=0").fetchall():
            for acc in q("select * from accounts where uid=?", (u["id"],)).fetchall():
                try: await clock_apply(acc, u)
                except Exception as e:
                    logging.warning("clock %s", e)
                    if time.time() - clock_err.get(acc["id"], 0) > 21600:
                        clock_err[acc["id"]] = time.time()
                        try: await bot.send_message(u["id"], f"⚠️ تعذّر تحديث الساعة بجانب اسم حسابك ({acc['phone'] if 'phone' in acc.keys() else ''}).\nالسبب: {type(e).__name__}\nجرّب إيقاف الساعة وتفعيلها من جديد.")
                        except Exception: pass
                await asyncio.sleep(0.5)

BTN_KEYS = {"accs": "📱 حساباتي", "apm": "🚀 النشر التلقائي", "ar": "💬 رد بالخاص", "ms": "📊 الإحصائيات", "clk": "🕐 الساعة",
            "cc": "📢 ساعة القناة/الكروب", "vipbuy": "⭐ تفعيل VIP", "rc": "🎟 تفعيل كود", "vipfree": "🎁 VIP مجاناً", "guide": "📖 الدليل",
            "adm": "👑 لوحة الأدمن", "ap": "▶️ تشغيل/إيقاف النشر", "int": "⏱ فاصل النشر", "gcount": "📥 الكروبات", "pt": "✍️ نص الرسالة",
            "owner": "🧑‍💻 تواصل مع المالك", "home": "🔙 رجوع للرئيسية",
            "st_on": "🟢 علامة التشغيل (تظهر لما الزر شغّال)", "st_off": "🔴 علامة الإيقاف (تظهر لما الزر مطفي)"}

def ico_view():
    kb = [[_IB(text=("✅ " if k in ICONS else "⬜ ") + v, callback_data=f"ico:{k}")] for k, v in BTN_KEYS.items()]
    kb = [[B(text=f"الملصقات: {'شغّالة 🟢' if ICONS_ON[0] else 'متوقفة 🔴'} (اضغط للتبديل)", callback_data="icot")]] + kb + [[B(text="🔙 رجوع", callback_data="adm")]]
    import aiogram
    return (f"🎨 ملصقات الأزرار\n🔧 aiogram {aiogram.__version__} — دعم الملصق: {'✅' if 'icon_custom_emoji_id' in getattr(_IB, 'model_fields', {}) else '❌ حدّث المكتبة'}\n\nاختر الزر، ثم أرسل رسالة فيها ملصق مميز (إيموجي مخصص) من تيليجرام بريميوم، والبوت يحطه على الزر.\n"
            "⚠️ يشتغل فقط إذا حساب مالك البوت عنده Premium.\n\n✅ = عليه ملصق", InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "ico")
@adm_only
async def ico(c: CallbackQuery, state: FSMContext):
    await state.clear(); t, kb = ico_view(); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data == "icot")
@adm_only
async def icot(c: CallbackQuery, state: FSMContext):
    ICONS_ON[0] = not ICONS_ON[0]; cfg_set("icons_on", "1" if ICONS_ON[0] else "0"); await ico(c, state=state)

@dp.callback_query(F.data.startswith("ico:"))
@adm_only
async def ico_pick(c: CallbackQuery, state: FSMContext):
    k = c.data[4:]
    if k not in BTN_KEYS: return await c.answer()
    await state.set_state(S.ico); await state.update_data(k=k)
    kb = [[_IB(text="🗑 إزالة الملصق", callback_data=f"icod:{k}")] if k in ICONS else [], [_IB(text="🔙 رجوع", callback_data="ico")]]
    await edit(c, f"أرسل الآن رسالة فيها ملصق مميز واحد للزر «{BTN_KEYS[k]}».\n(اكتب الملصق بالرسالة مثل أي إيموجي)", InlineKeyboardMarkup(inline_keyboard=[r for r in kb if r])); await c.answer()

@dp.callback_query(F.data.startswith("icod:"))
@adm_only
async def ico_del(c: CallbackQuery, state: FSMContext):
    ICONS.pop(c.data[5:], None); cfg_set("btn_icons", json.dumps(ICONS)); await ico(c, state=state)

@dp.message(S.ico)
async def ico_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    k = (await state.get_data()).get("k")
    ent = next((e for e in (m.entities or m.caption_entities or []) if e.type == "custom_emoji"), None)
    if not ent: return await m.answer("❌ ما لقيت ملصق مميز بالرسالة. أرسل رسالة فيها إيموجي مميز (من حساب بريميوم).")
    try: await m.answer("🧪 اختبار: لازم يظهر الملصق المميز قبل كلمة «تجربة» بالزر.\nإذا طلع زر عادي بدون ملصق، يعني مالك البوت (الحساب اللي سوّى البوت بـ BotFather) مو Premium، أو المكتبة قديمة.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_IB(text="تجربة", callback_data="ico", icon_custom_emoji_id=ent.custom_emoji_id)]]))
    except Exception as e: return await m.answer(f"❌ تيليجرام رفض الملصق: {e}\nتأكد أن مالك البوت عنده Premium وأن المكتبة محدّثة (pip install -U aiogram).")
    ICONS[k] = ent.custom_emoji_id; cfg_set("btn_icons", json.dumps(ICONS)); await state.clear()
    t, kb = ico_view(); await m.answer("✅ انحفظ الملصق.\n\n" + t, reply_markup=kb)

async def refresh_names(uid):
    u = user(uid)
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        try:
            if u["clock_on"] or u["anim_style"] or status_now(u): await clock_apply(acc, u)
            else: await clock_restore(acc)
        except Exception as e: logging.warning("status %s", e)

def stm_view(uid):
    u = user(uid); cur = status_now(u)
    txt = "🎭 وضع الحالة\n\nاختر حالتك بضغطة وحدة: يتغيّر اسمك بتلكرام (رمز الحالة) ويرد البوت لكل من يراسلك بنص الحالة تلقائياً، بدون ما تغيّر شي ثاني.\n\n"
    if cur:
        left = u["status_until"] - time.time() if u["status_until"] else 0
        txt += f"الحالي: {cur[0]}" + (f" — باقي {fmt_dur(left)}" if left > 0 else " — بدون توقيت") + "\n\n"
    kb = [[B(text=("🔘 " if cur and u["status_mode"] == k else "") + v[0], callback_data=f"stm:{k}")] for k, v in STATUS.items()]
    if cur: kb.append([B(text="❌ إلغاء الوضع", callback_data="stm:off")])
    kb.append([B(text="🔙 رجوع", callback_data="home")])
    return txt + "اختر الحالة:", InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "stm")
async def stm(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    t, kb = stm_view(c.from_user.id); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data.startswith("stm:"))
async def stm_pick(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; k = c.data[4:]
    if k == "off":
        q("update users set status_mode='', status_until=0 where id=?", (uid,)); await refresh_names(uid)
        t, kb = stm_view(uid); await edit(c, t, kb); return await c.answer("✅ انلغى الوضع")
    if k in STATUS:
        kb = [[B(text=lbl, callback_data=f"std:{k}:{sec}")] for lbl, sec in (("1 ساعة", 3600), ("3 ساعات", 10800), ("8 ساعات", 28800), ("24 ساعة", 86400), ("بدون توقيت (لين أوقفه)", 0))]
        kb.append([B(text="🔙 رجوع", callback_data="stm")])
        await edit(c, f"{STATUS[k][0]}\n\nمدة الوضع؟", InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data.startswith("std:"))
async def stm_dur(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; _, k, sec = c.data.split(":")
    if k not in STATUS: return await c.answer()
    q("update users set status_mode=?, status_until=? where id=?", (k, time.time() + int(sec) if int(sec) else 0, uid)); await refresh_names(uid)
    t, kb = stm_view(uid); await edit(c, "✅ تفعّل الوضع.\n\n" + t, kb); await c.answer()

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError
CC_MODES = {"name": "🏷 بالاسم", "desc": "📝 بالوصف", "both": "✅ الاثنين"}
def cc_view(uid):
    rows_ = q("select * from clock_chats where uid=? order by id", (uid,)).fetchall(); mx = lim(uid)["chats"]
    txt = (f"📢 ساعة القناة / الكروب ({len(rows_)}/{mx})\n\nيكتب البوت الوقت داخل اسم القناة أو الكروب أو وصفه ويتحدّث تلقائياً.\n"
           "✅ الاسم والوصف يتحدّثون كل دقيقة، والبوت يحذف رسالة «تغيّر الاسم» تلقائياً (لازم يكون عنده صلاحية حذف الرسائل).\n\n" +
           ("\n".join(f"• {r['orig_title'][:30]} — {CC_MODES[r['mode']]}" for r in rows_) or "ما أضفت شي بعد."))
    kb = [[B(text=f"🗑 {r['orig_title'][:25]}", callback_data=f"ccd:{r['id']}")] for r in rows_]
    kb += [[B(text=f"➕ إضافة قناة/كروب ({len(rows_)}/{mx})", callback_data="cca")], [B(text="🔙 رجوع", callback_data="home")]]
    return txt, InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "cc")
async def cc(c: CallbackQuery, state: FSMContext):
    await state.clear(); t, kb = cc_view(c.from_user.id); await edit(c, t, kb); await c.answer()

@dp.callback_query(F.data == "cca")
async def cca(c: CallbackQuery):
    uid = c.from_user.id; n = q("select count(*) c from clock_chats where uid=?", (uid,)).fetchone()["c"]
    if n >= lim(uid)["chats"]:
        return await c.answer(f"وصلت للحد ({lim(uid)['chats']})" + ("" if is_vip(uid) else f" 💎 VIP يسمح بـ {VIP['chats']}"), show_alert=True)
    kb = [[B(text=v, callback_data=f"ccm:{k}")] for k, v in CC_MODES.items()] + [[B(text="🔙 رجوع", callback_data="cc")]]
    await edit(c, "🕐 وين تريد يظهر الوقت؟\n\n🏷 بالاسم  |  📝 بالوصف  |  ✅ الاثنين", InlineKeyboardMarkup(inline_keyboard=kb)); await c.answer()

@dp.callback_query(F.data.startswith("ccm:"))
async def ccm(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.cc); await state.update_data(mode=c.data[4:])
    me = await bot.get_me()
    await edit(c, f"1️⃣ ارفع @{me.username} مشرف بالقناة أو الكروب (مع صلاحيتي «تغيير المعلومات» و«حذف الرسائل»، حتى ما تظهر رسالة تغيّر الاسم).\n"
                  "2️⃣ بعدها دز رابط القناة/الكروب أو @اليوزر، أو حوّل (Forward) رسالة منها لهنا.\n\n"
                  "ملاحظة: الروابط الخاصة (t.me/+...) ما يقدر البوت يقراها، استخدم التحويل أو الآيدي.", back("cc")); await c.answer()

@dp.message(S.cc)
async def cc_in(m: Message, state: FSMContext):
    uid = m.from_user.id; mode = (await state.get_data()).get("mode", "both"); ref = None
    if m.forward_from_chat: ref = m.forward_from_chat.id
    else:
        t = (m.text or "").strip(); r = re.search(r"(?:t\.me/|@)([A-Za-z0-9_]{4,})", t)
        ref = int(t) if re.fullmatch(r"-?\d+", t) else ("@" + r[1] if r and not r[1].startswith("+") else None)
    if ref is None: return await m.answer("❌ ما فهمت الرابط. دز @اليوزر أو رابط عام أو حوّل رسالة من القناة.")
    try:
        ch = await bot.get_chat(ref); me = await bot.get_me()
        bm = await bot.get_chat_member(ch.id, me.id)
        um = await bot.get_chat_member(ch.id, uid)
    except Exception:
        return await m.answer("❌ ما كدرت أوصل لها. تأكد أن البوت مضاف مشرف بالقناة/الكروب وأعد المحاولة.")
    if ch.type not in ("channel", "group", "supergroup"): return await m.answer("❌ هذا مو قناة ولا كروب.")
    if um.status not in ("creator", "administrator") and uid not in ADMINS: return await m.answer("❌ لازم تكون مشرف بها.")
    if bm.status != "administrator" or not getattr(bm, "can_change_info", False):
        return await m.answer("❌ البوت مو مشرف أو ما عنده صلاحية «تغيير المعلومات». عدّل صلاحياته وأعد إرسال الرابط.")
    if q("select 1 from clock_chats where uid=? and chat_id=?", (uid, ch.id)).fetchone(): return await m.answer("موجودة من قبل.")
    if q("select count(*) c from clock_chats where uid=?", (uid,)).fetchone()["c"] >= lim(uid)["chats"]:
        await state.clear(); return await m.answer("وصلت للحد المسموح.")
    if not getattr(bm, "can_delete_messages", False): await m.answer("⚠️ البوت ما عنده صلاحية «حذف الرسائل»، فرسالة تغيّر الاسم راح تظهر. فعّلها له حتى تنحذف تلقائياً.")
    q("insert into clock_chats(uid,chat_id,title,orig_title,orig_desc,mode) values(?,?,?,?,?,?)",
      (uid, ch.id, ch.title or "", ch.title or "", ch.description or "", mode)); await state.clear()
    await cc_tick(q("select * from clock_chats where chat_id=? and uid=?", (ch.id, uid)).fetchone(), force=True)
    t_, kb_ = cc_view(uid); await m.answer("✅ تم التفعيل. شوف القناة/الكروب.\n\n" + t_, reply_markup=kb_)

@dp.callback_query(F.data.startswith("ccd:"))
async def ccd(c: CallbackQuery, state: FSMContext):
    r = q("select * from clock_chats where id=? and uid=?", (int(c.data[4:]), c.from_user.id)).fetchone()
    if r:
        try:
            if r["mode"] in ("name", "both"): await bot.set_chat_title(r["chat_id"], r["orig_title"])
            if r["mode"] in ("desc", "both"): await bot.set_chat_description(r["chat_id"], r["orig_desc"] or None)
        except Exception as e: logging.warning("cc restore %s", e)
        q("delete from clock_chats where id=?", (r["id"],))
    await cc(c, state)

async def cc_tick(r, force=False):
    u = user(r["uid"]); t = time.gmtime(time.time() + TZ * 3600)
    ck = deco(hm(t.tm_hour, t.tm_min, bool(u["show_ampm"])))
    try:
        if r["mode"] in ("name", "both") and True:
            await bot.set_chat_title(r["chat_id"], (r["orig_title"][:63 - len(ck)] + " " + ck)[:128])
        if r["mode"] in ("desc", "both"):
            await bot.set_chat_description(r["chat_id"], ((r["orig_desc"] + "\n\n") if r["orig_desc"] else "")[:250 - len(ck)] + "🕐 " + ck)
    except TelegramRetryAfter: pass
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower(): return
        raise

@dp.message(F.new_chat_title)
@dp.channel_post(F.new_chat_title)
async def cc_hide_service(m: Message):
    if q("select 1 from clock_chats where chat_id=?", (m.chat.id,)).fetchone():
        try: await m.delete()
        except Exception: pass

async def cc_loop():
    while True:
        await asyncio.sleep(60 - time.time() % 60 + 2)
        for r in q("select * from clock_chats").fetchall():
            try: await cc_tick(r)
            except (TelegramForbiddenError, TelegramBadRequest) as e:
                logging.warning("cc %s", e); q("delete from clock_chats where id=?", (r["id"],))
                try: await bot.send_message(r["uid"], f"⚠️ توقفت ساعة «{r['orig_title']}» لأن البوت فقد صلاحية التعديل. أعد رفعه مشرف وأضفها من جديد.")
                except Exception: pass
            except Exception as e: logging.warning("cc %s", e)
            await asyncio.sleep(0.3)

async def do_backup():
    dst = sqlite3.connect("backup.db"); db.backup(dst); dst.close(); cfg_set("last_backup", str(time.time()))
    for a in ADMINS:
        try: await bot.send_document(a, FSInputFile("backup.db"), caption="💾 نسخة احتياطية. احتفظ بمفتاح التشفير (FERNET_KEY أو fernet.key) بمكان آمن، بدونه ما تنفتح الجلسات.")
        except Exception: pass

@dp.callback_query(F.data == "bk")
@adm_only
async def bk(c: CallbackQuery):
    await do_backup(); await c.answer("✅ أُرسلت النسخة لك بالخاص", show_alert=True)

async def backup_loop():
    await asyncio.sleep(300)
    while True:
        await do_backup(); q("delete from sent_log where day < ?", (today_str(30),))
        await asyncio.sleep(86400)

async def health_check():
    for a in q("select * from accounts").fetchall():
        try:
            cl = await get_client(a)
            if cl: await cl.get_me()
            else:
                q("delete from groups where acc=?", (a["id"],)); sec_event("dead", a["uid"])
                await alert(a["uid"], f"❌ الحساب {mask(a['phone'])} لم يعد صالحاً (محظور أو انتهت جلسته) وتم حذفه من البوت.", admin=True)
        except (errors.AuthKeyUnregisteredError, errors.UserDeactivatedBanError, errors.UserDeactivatedError, errors.SessionRevokedError):
            q("delete from accounts where id=?", (a["id"],)); q("delete from groups where acc=?", (a["id"],)); sec_event("dead", a["uid"])
            await alert(a["uid"], f"🚫 تم حظر/تعطيل الحساب {mask(a['phone'])} وحذفه من البوت.", admin=True)
        except Exception as e: logging.warning("health %s", e)
        await asyncio.sleep(2)

async def health_loop():
    while True:
        await health_check()
        await asyncio.sleep(6 * 3600)

async def vip_loop():
    while True:
        now = time.time()
        for u in q("select * from users where vip_until>0").fetchall():
            try:
                if now < u["vip_until"] < now + 172800 and u["vip_remind"] != u["vip_until"]:
                    q("update users set vip_remind=? where id=?", (u["vip_until"], u["id"]))
                    await bot.send_message(u["id"], "⏰ اشتراك VIP ينتهي خلال أقل من يومين. جدّد الآن لتستمر المزايا:",
                                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="⭐ تجديد VIP", callback_data="vipbuy")]]))
                elif u["vip_until"] <= now and u["vip_notified"] != u["vip_until"]:
                    q("update users set vip_notified=? where id=?", (u["vip_until"], u["id"]))
                    await bot.send_message(u["id"], "انتهى اشتراك VIP. تقدر تجدده بأي وقت:",
                                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="⭐ تجديد VIP", callback_data="vipbuy")]]))
            except Exception: pass
        await asyncio.sleep(3600)

START = time.time()
PEN = {"peerflood": 10, "floodwait": 5, "dead": 12, "login_block": 2, "flood_spike": 5, "error": 1}
LABEL = {"peerflood": "تقييد سبام من تيليجرام", "floodwait": "تقييد مؤقت طويل", "dead": "حسابات معطلة/محظورة",
         "login_block": "محاولات دخول مرفوضة", "flood_spike": "ضغط/هجوم على البوت", "error": "أخطاء بالبوت"}
def sec_event(kind, uid=0): q("insert into sec_events(ts,kind,uid) values(?,?,?)", (time.time(), kind, uid))
def level(sc): return "قوية 🟢" if sc >= 80 else "متوسطة 🟡" if sc >= 60 else "ضعيفة 🔴"
def sec_report():
    score, reasons = 100, []
    for r in q("select kind, count(*) n from sec_events where ts>? and ack=0 group by kind", (time.time() - 86400,)).fetchall():
        pen = min(PEN.get(r["kind"], 1) * r["n"], 30); score -= pen
        reasons.append(f"{LABEL.get(r['kind'], r['kind'])} ×{r['n']} (−{pen})")
    cool = q("select count(*) n from accounts where cool_until>?", (time.time(),)).fetchone()["n"]
    if cool:
        pen = min(cool * 5, 20); score -= pen; reasons.append(f"حسابات بفترة راحة ×{cool} (−{pen})")
    if not os.environ.get("FERNET_KEY"):
        try: open_perm = os.stat("fernet.key").st_mode & 0o077
        except OSError: open_perm = 0
        if open_perm: score -= 10; reasons.append("صلاحيات مفتاح التشفير مفتوحة (−10)")
    last = float(cfg_get("last_backup", "0"))
    if (time.time() - last > 36 * 3600) if last else (time.time() - START > 7200):
        score -= 5; reasons.append("لا توجد نسخة احتياطية حديثة (−5)")
    return max(score, 0), reasons

def sec_line():
    sc, _ = sec_report(); return f"🛡 الحماية: {level(sc)} ({sc}/100)"

async def sec_loop():
    warned = 0.0
    while True:
        await asyncio.sleep(600)
        if stats["drops"] > 200: sec_event("flood_spike")
        stats["drops"] = 0
        sc, reasons = sec_report()
        if sc < 60 and time.time() - warned > 6 * 3600:
            warned = time.time()
            await notify(f"🛡⚠️ تحذير: حماية البوت ضعفت ({sc}/100)\n" + "\n".join("• " + r for r in reasons) +
                         "\n\nادخل لوحة الأدمن واضغط «🔄 تجديد الحماية».", admins=True)

@dp.error()
async def on_error(event: ErrorEvent):
    logging.error("handler error", exc_info=event.exception); sec_event("error")
    if time.time() - err_t[0] > 600:
        err_t[0] = time.time()
        await notify(f"⚠️ خطأ بالبوت: {type(event.exception).__name__}: {str(event.exception)[:200]}")
    return True

@dp.callback_query(F.data == "sh")
@adm_only
async def sh(c: CallbackQuery):
    sc, reasons = sec_report()
    await edit(c, f"🛡 حالة الحماية: {level(sc)} ({sc}/100)\n\n" + ("\n".join("• " + r for r in reasons) or "لا توجد ملاحظات خلال آخر 24 ساعة ✅"), back("adm")); await c.answer()

@dp.callback_query(F.data == "sr")
@adm_only
async def sr(c: CallbackQuery):
    await c.answer("⏳ جاري تجديد الحماية...")
    last_hit.clear(); stats["drops"] = 0
    for cl in list(clients.values()):
        try: await cl.disconnect()
        except Exception: pass
    clients.clear()
    await health_check()
    q("delete from replied where ts<?", (time.time() - 7 * 86400,))
    q("update sec_events set ack=1 where ack=0"); alog(c.from_user.id, "تجديد الحماية")
    sc, reasons = sec_report()
    msg = (f"✅ تم تجديد الحماية وأصبحت قوية ({sc}/100)" if sc >= 80 else
           f"🛡 تم تجديد الحماية، الحالة: {level(sc)} ({sc}/100)\nما زالت هناك ملاحظات:\n" + "\n".join("• " + r for r in reasons))
    await notify(msg); await edit(c, msg, back("adm"))

@dp.callback_query(F.data == "lc")
@adm_only
async def lc(c: CallbackQuery):
    cur = cfg_get("log_title", "") or str(cfg_chan())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🔗 ربط / تغيير القناة", callback_data="lcs")],
        [B(text="🧪 إرسال إشعار تجريبي", callback_data="lct")],
        [B(text="🔙 رجوع", callback_data="adm")]])
    await edit(c, f"📣 قناة الإشعارات الحالية:\n{cur}\n\nكل الشعارات المهمة (مستخدمين جدد، حظر حسابات، تحذيرات الحماية...) تُرسل لها.", kb); await c.answer()

@dp.callback_query(F.data == "lct")
@adm_only
async def lct(c: CallbackQuery):
    try: await bot.send_message(cfg_chan(), "🧪 إشعار تجريبي: القناة مربوطة بنجاح ✅"); await c.answer("✅ أُرسل للقناة", show_alert=True)
    except Exception as e: await c.answer(f"❌ فشل: {str(e)[:150]}\nتأكد أن البوت مشرف بالقناة.", show_alert=True)

@dp.callback_query(F.data == "lcs")
@adm_only
async def lcs(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.chan)
    await edit(c, "1) أضف البوت كمشرف بقناتك مع صلاحية نشر الرسائل.\n2) ثم أرسل هنا يوزر القناة مثل @channel\nأو حوّل (Forward) أي رسالة من القناة إلى هنا.", back("lc")); await c.answer()

@dp.message(S.chan)
async def chan_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    fo = getattr(m, "forward_origin", None)
    ch = getattr(fo, "chat", None) or getattr(m, "forward_from_chat", None)
    target = ch.id if ch else (m.text or "").strip()
    if isinstance(target, str) and target.lstrip("-").isdigit(): target = int(target)
    if not target: return await m.answer("أرسل يوزر القناة أو حوّل رسالة منها.")
    try:
        chat = await bot.get_chat(target)
        me = await bot.get_me()
        mem = await bot.get_chat_member(chat.id, me.id)
        if mem.status not in ("administrator", "creator"):
            return await m.answer("❌ البوت مو مشرف بهذي القناة. أضفه كمشرف ثم أعد الإرسال.")
        await bot.send_message(chat.id, "✅ تم ربط هذي القناة كقناة إشعارات للبوت.")
    except Exception as e:
        return await m.answer(f"❌ تعذر الربط: {str(e)[:200]}\nتأكد من اليوزر وأن البوت مشرف مع صلاحية النشر.")
    cfg_set("log_channel", str(chat.id)); cfg_set("log_title", chat.title or str(chat.id))
    alog(m.from_user.id, f"ربط قناة إشعارات {chat.title}"); await state.clear()
    await m.answer(f"✅ تم ربط قناة الإشعارات: {chat.title}", reply_markup=adm_kb())

def parse_target(t):
    t = (t or "").strip().lstrip("@")
    if t.isdigit(): return int(t)
    r = q("select id from users where lower(uname)=?", (t.lower(),)).fetchone()
    return r["id"] if r else None

def fdate(t): return time.strftime("%Y-%m-%d", time.gmtime(t + TZ * 3600)) if t else "—"

def user_card(uid):
    u = q("select * from users where id=?", (uid,)).fetchone()
    if not u: return None, None
    accs = q("select * from accounts where uid=?", (uid,)).fetchall()
    ng = q("select count(*) n from groups g join accounts a on a.id=g.acc where a.uid=? and g.sel=1", (uid,)).fetchone()["n"]
    t = q("select coalesce(sum(n),0) s from sent_log where uid=? and day=?", (uid, today_str())).fetchone()["s"]
    w = q("select coalesce(sum(n),0) s from sent_log where uid=? and day>=?", (uid, today_str(6))).fetchone()["s"]
    txt = (f"👤 {user_tag(uid)}\n📅 انضم: {fdate(u['joined'])}\n💎 VIP: {vip_text(uid)}\n"
           f"🚫 محظور: {'نعم' if u['banned'] else 'لا'}\n🚀 النشر: {'يعمل' if u['autopost'] else 'متوقف'} (كل {fmt_dur(eff_iv(u))})\n"
           f"📱 الحسابات: {len(accs)}" + (" (" + ", ".join(mask(a['phone']) for a in accs) + ")" if accs else "") +
           f"\n📥 مجموعات مفعّلة: {ng}\n📈 اليوم: {t} | آخر 7 أيام: {w}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="♻️ فك الحظر" if u["banned"] else "🚫 حظر", callback_data=f"ub:{uid}")],
        [B(text="💎 +7 أيام", callback_data=f"uv:{uid}:7"), B(text="💎 +30 يوم", callback_data=f"uv:{uid}:30"), B(text="❌ إلغاء VIP", callback_data=f"uv:{uid}:0")],
        [B(text="⏹ إيقاف نشره", callback_data=f"us:{uid}"), B(text="🗑 حذف حساباته", callback_data=f"ud:{uid}")],
        [B(text="🔙 رجوع", callback_data="adm")]])
    return txt, kb

async def show_card(c, uid):
    txt, kb = user_card(uid)
    await edit(c, txt or "المستخدم غير موجود.", kb or back("adm")); await c.answer()

@dp.callback_query(F.data == "ui")
@adm_only
async def ui(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.find); await edit(c, "🔍 أرسل آيدي المستخدم أو يوزره (@username):", back("adm")); await c.answer()

@dp.message(S.find)
async def find_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    uid = parse_target(m.text)
    txt, kb = user_card(uid) if uid else (None, None)
    if not txt: return await m.answer("❌ ما لقيت المستخدم (لازم يكون سوّى /start للبوت).")
    await state.clear(); await m.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("ub:"))
@adm_only
async def ub(c: CallbackQuery):
    uid = int(c.data[3:])
    if uid in ADMINS: return await c.answer("لا يمكن حظر مشرف", show_alert=True)
    ban = 1 - user(uid)["banned"]
    q("update users set banned=?, autopost=case when ?=1 then 0 else autopost end where id=?", (ban, ban, uid))
    alog(c.from_user.id, f"{'حظر' if ban else 'فك حظر'} {uid}"); await notify(f"{'🚫 حظر' if ban else '♻️ فك حظر'} المستخدم {user_tag(uid)}")
    await show_card(c, uid)

@dp.callback_query(F.data.startswith("uv:"))
@adm_only
async def uv(c: CallbackQuery):
    _, uid, d = c.data.split(":"); uid, d = int(uid), int(d)
    if d == 0: q("update users set vip_until=0 where id=?", (uid,))
    else: add_vip(uid, d)
    alog(c.from_user.id, f"VIP {d} يوم للمستخدم {uid}"); await notify(f"💎 تعديل VIP: {d} يوم للمستخدم {user_tag(uid)}")
    if d:
        try: await bot.send_message(uid, f"🎉 تم تفعيل VIP لمدة {d} يوم!")
        except Exception: pass
    await show_card(c, uid)

@dp.callback_query(F.data.startswith("us:"))
@adm_only
async def us(c: CallbackQuery):
    uid = int(c.data[3:]); q("update users set autopost=0 where id=?", (uid,))
    t = tasks.pop(uid, None)
    if t: t.cancel()
    alog(c.from_user.id, f"إيقاف نشر {uid}"); await show_card(c, uid)

@dp.callback_query(F.data.startswith("ud:"))
@adm_only
async def ud(c: CallbackQuery):
    uid = c.data[3:]
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✅ تأكيد الحذف", callback_data=f"udc:{uid}")], [B(text="🔙 إلغاء", callback_data=f"uc:{uid}")]])
    await edit(c, f"⚠️ حذف كل حسابات ومجموعات المستخدم {uid} من البوت؟", kb); await c.answer()

@dp.callback_query(F.data.startswith("uc:"))
@adm_only
async def uc(c: CallbackQuery): await show_card(c, int(c.data[3:]))

@dp.callback_query(F.data.startswith("udc:"))
@adm_only
async def udc(c: CallbackQuery):
    uid = int(c.data[4:])
    for a in q("select id from accounts where uid=?", (uid,)).fetchall():
        cl = clients.pop(a["id"], None)
        if cl:
            try: await cl.disconnect()
            except Exception: pass
        q("delete from groups where acc=?", (a["id"],))
    q("delete from accounts where uid=?", (uid,)); q("update users set autopost=0 where id=?", (uid,))
    alog(c.from_user.id, f"حذف حسابات {uid}"); await notify(f"🗑 تم حذف حسابات المستخدم {user_tag(uid)} بواسطة الأدمن")
    await show_card(c, uid)

@dp.callback_query(F.data == "ul")
@adm_only
async def ul(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="💎 VIP الحاليين", callback_data="ul:vip"), B(text="🚫 المحظورين", callback_data="ul:ban")],
        [B(text="🆕 آخر المستخدمين", callback_data="ul:new")], [B(text="🔙 رجوع", callback_data="adm")]])
    await edit(c, "👥 اختر القائمة:", kb); await c.answer()

@dp.callback_query(F.data.startswith("ul:"))
@adm_only
async def ul_show(c: CallbackQuery):
    k = c.data[3:]; now = time.time()
    rows, title = {"vip": (q("select * from users where vip_until>? order by vip_until limit 25", (now,)).fetchall(), "💎 VIP الحاليين"),
                   "ban": (q("select * from users where banned=1 limit 25").fetchall(), "🚫 المحظورين"),
                   "new": (q("select * from users order by joined desc limit 25").fetchall(), "🆕 آخر المستخدمين")}[k]
    lines = [f"{user_tag(r['id'])}" + (f" — {int((r['vip_until'] - now) // 86400) + 1} يوم" if k == "vip" else "") for r in rows]
    await edit(c, f"{title}:\n\n" + ("\n".join(lines) or "لا يوجد"), back("ul")); await c.answer()

def lim_map():
    return {"free_accounts": (FREE, "accounts"), "free_groups": (FREE, "groups"), "free_min_s": (FREE, "min_s"), "free_replies": (FREE, "replies"), "free_posts": (FREE, "posts"), "free_chats": (FREE, "chats"),
            "vip_accounts": (VIP, "accounts"), "vip_groups": (VIP, "groups"), "vip_min_s": (VIP, "min_s"), "vip_replies": (VIP, "replies"), "vip_posts": (VIP, "posts"), "vip_chats": (VIP, "chats"),
            "daily_free": (DAILY, "free"), "daily_vip": (DAILY, "vip")}
LIM_RANGE = {"accounts": (1, 20), "groups": (1, 2000), "min_s": (1, 259200), "replies": (1, 20), "posts": (1, 20), "chats": (1, 100), "free": (1, 5000), "vip": (1, 5000)}

def load_limits():
    try: d = json.loads(cfg_get("limits", "{}"))
    except ValueError: d = {}
    for k, v in d.items():
        m = lim_map().get(k)
        if m and isinstance(v, int): m[0][m[1]] = v

def save_limits(): cfg_set("limits", json.dumps({k: m[0][m[1]] for k, m in lim_map().items()}))
def load_admins():
    for x in cfg_get("admins", "").split(","):
        if x.strip().isdigit(): ADMINS.add(int(x))
def save_admins(): cfg_set("admins", ",".join(str(a) for a in sorted(ADMINS - ROOT)))

@dp.callback_query(F.data == "ls")
@adm_only
async def ls(c: CallbackQuery, state: FSMContext):
    vals = "\n".join(f"{k} = {m[0][m[1]]}" for k, m in lim_map().items()) + f"\nref_days = {cfg_get('ref_days', '1')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✏️ تعديل", callback_data="lse")], [B(text="🔙 رجوع", callback_data="adm")]])
    await edit(c, f"⚙️ الحدود الحالية:\n\n{vals}\n\n(accounts عدد الحسابات، groups مجموعات بالدورة، min_s أقل فاصل بالثواني، replies عدد كليشات الرد بالخاص، daily الحد اليومي لكل حساب، ref_days أيام VIP للإحالة)", kb); await c.answer()

@dp.callback_query(F.data == "lse")
@adm_only
async def lse(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.lim); await edit(c, "أرسل سطر لكل تعديل، مثل:\nfree_accounts 2\nvip_groups 500\nref_days 3", back("ls")); await c.answer()

@dp.message(S.lim)
async def lim_in(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS: return
    done, bad = [], []
    for line in (m.text or "").splitlines():
        try:
            k, v = line.split(); v = int(v)
            if k == "ref_days":
                assert 0 <= v <= 365; cfg_set("ref_days", str(v)); done.append(line); continue
            tgt, key = lim_map()[k]; lo, hi = LIM_RANGE[key]; assert lo <= v <= hi
            tgt[key] = v; done.append(line)
        except Exception: bad.append(line)
    save_limits(); await state.clear()
    if done: alog(m.from_user.id, "تعديل حدود: " + ", ".join(done))
    await m.answer(f"✅ تم: {len(done)}" + (f"\n❌ مرفوض: {', '.join(bad)}" if bad else ""), reply_markup=adm_kb())

@dp.callback_query(F.data == "am")
@adm_only
async def am(c: CallbackQuery):
    if c.from_user.id not in ROOT: return await c.answer("للمالك الأساسي فقط", show_alert=True)
    rows = [[B(text=f"➖ {a}", callback_data=f"adx:{a}")] for a in sorted(ADMINS - ROOT)]
    rows += [[B(text="➕ إضافة مشرف", callback_data="ama")], [B(text="🔙 رجوع", callback_data="adm")]]
    await edit(c, f"🛡 المالكون: {', '.join(map(str, ROOT))}\nالمشرفون الإضافيون: {len(ADMINS - ROOT)} (اضغط للحذف)", InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("adx:"))
@adm_only
async def adx(c: CallbackQuery):
    if c.from_user.id not in ROOT: return
    ADMINS.discard(int(c.data[4:])); save_admins(); alog(c.from_user.id, f"حذف مشرف {c.data[4:]}"); await am(c)

@dp.callback_query(F.data == "ama")
@adm_only
async def ama(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ROOT: return
    await state.set_state(S.addadm); await edit(c, "أرسل آيدي المشرف الجديد (رقم):", back("am")); await c.answer()

@dp.message(S.addadm)
async def addadm_in(m: Message, state: FSMContext):
    if m.from_user.id not in ROOT or not (m.text or "").strip().isdigit(): return
    a = int(m.text.strip()); ADMINS.add(a); save_admins(); user(a); await state.clear()
    alog(m.from_user.id, f"إضافة مشرف {a}"); await notify(f"🛡 تمت إضافة مشرف جديد: {a}")
    try: await bot.send_message(a, "🛡 تمت إضافتك كمشرف بالبوت. أرسل /admin")
    except Exception: pass
    await m.answer("✅ تمت الإضافة.", reply_markup=adm_kb())

@dp.callback_query(F.data == "ex")
@adm_only
async def ex(c: CallbackQuery):
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "username", "name", "joined", "vip_until", "banned", "accounts"])
    for r in q("select u.*, (select count(*) from accounts a where a.uid=u.id) as na from users u").fetchall():
        w.writerow([r["id"], r["uname"], r["fname"], fdate(r["joined"]), fdate(r["vip_until"]), r["banned"], r["na"]])
    await bot.send_document(c.from_user.id, BufferedInputFile(("\ufeff" + buf.getvalue()).encode("utf-8"), filename="users.csv"))
    await c.answer("✅ أُرسل لك بالخاص", show_alert=True)

@dp.callback_query(F.data == "sa")
@adm_only
async def sa(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✅ نعم، أوقف الكل", callback_data="sac")], [B(text="🔙 إلغاء", callback_data="adm")]])
    await edit(c, "🛑 إيقاف النشر التلقائي لجميع المستخدمين فوراً؟ (يرجعون يشغلونه بأنفسهم)", kb); await c.answer()

@dp.callback_query(F.data == "sac")
@adm_only
async def sac(c: CallbackQuery):
    n = q("select count(*) n from users where autopost=1").fetchone()["n"]
    q("update users set autopost=0")
    for t in list(tasks.values()): t.cancel()
    tasks.clear(); alog(c.from_user.id, "إيقاف كل النشر"); await notify(f"🛑 تم إيقاف النشر لجميع المستخدمين ({n}) بواسطة الأدمن")
    await edit(c, f"✅ تم إيقاف النشر لـ {n} مستخدم.", back("adm")); await c.answer()

async def main():
    load_limits(); load_admins()
    for u in q("select id from users where autopost=1").fetchall(): start_loop(u["id"])
    bg = [asyncio.create_task(f()) for f in (health_loop, vip_loop, backup_loop, sec_loop, clock_loop, cc_loop)]
    await notify(f"✅ تم تشغيل البوت\n{sec_line()}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
