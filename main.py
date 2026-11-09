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
​logging.basicConfig(level=logging.INFO)
ICONS = {}; ICONS_ON = [True]
def B(kw):
cb = kw.get("callback_data") or ("owner" if kw.get("url") else None); ic = kw.get("icon_custom_emoji_id") or (ICONS.get(cb) if ICONS_ON[0] and cb else None)
if ic:
kw["icon_custom_emoji_id"] = ic; kw["text"] = re.sub(r"^[^\w(]+", "", kw.get("text", "")) or kw.get("text", "")
return _IB(kw)
​BOT_TOKEN = os.environ.get("BOT_TOKEN", "9286024586:AAGL6Ht3lAY6RCVo0cTqAdM-MymsoPMw4ys")
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "7753146356").split(",") if x.strip()}
ROOT = set(ADMINS)
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "@RX62X")
API_ID = int(os.environ.get("API_ID", "36444028"))
API_HASH = os.environ.get("API_HASH", "92aac2e192857ff973a9b3ae2a3274ca")
if not API_ID or not API_HASH:
raise SystemExit("ضع API_ID و API_HASH بأعلى الملف (من my.telegram.org)")
OWNER = "@K000OOO"
​FREE = dict(accounts=1, groups=4, min_s=300, replies=1, posts=1, chats=1)
VIP = dict(accounts=6, groups=10, min_s=5, replies=5, posts=5, chats=10)
MAX_IV = 3 * 86400
​_k = os.environ.get("FERNET_KEY", "").encode()
if not _k:
if not os.path.exists("fernet.key"):
open("fernet.key", "wb").write(Fernet.generate_key())
try: os.chmod("fernet.key", 0o600)
except OSError: pass
_k = open("fernet.key", "rb").read()
fer = Fernet(_k)
​db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
def q(sql, a=()):
cur = db.execute(sql, a); db.commit(); return cur
​q("create table if not exists users(id integer primary key, banned int default 0, interval int default 10, post_text text default '', autopost int default 0, reply_on int default 0, reply_text text default '')")
q("create table if not exists accounts(id integer primary key autoincrement, uid int, phone text, name text, session text)")
q("create table if not exists groups(id integer primary key autoincrement, acc int, chat_id int, title text, sel int default 1)")
q("create table if not exists channels(chat text primary key, link text)")
q("create table if not exists replied(acc int, uid int, ts real, primary key(acc,uid))")
q("create table if not exists cfg(k text primary key, v text)")
q("create table if not exists clock_chats(id integer primary key autoincrement, uid int, chat_id int, title text, orig_title text, orig_desc text, mode text)")
q("create table if not exists plans(id integer primary key autoincrement, name text, days int, price text)")
​for _s in ("alter table users add column vip_until real default 0", "alter table users add column joined real default 0",
"alter table users add column ref_done int default 0", "alter table channels add column link text",
"alter table users add column quiet_on int default 0", "alter table users add column quiet_from int default 1",
"alter table users add column quiet_to int default 7", "alter table accounts add column cool_until real default 0",
"alter table accounts add column day text default ''", "alter table accounts add column sent_today int default 0",
"alter table accounts add column created real default 0", "alter table groups add column fails int default 0",
"alter table users add column text_am text default ''", "alter table users add column text_pm text default ''",
"alter table users add column media_path text default ''", "alter table users add column keywords text default ''",
"alter table users add column radar_on int default 0", "alter table users add column vip_remind real default 0",
"alter table users add column vip_notified real default 0", "alter table users add column uname text default ''",
"alter table users add column fname text default ''", "alter table users add column notified_new int default 0",
"alter table users add column show_ampm int default 1", "alter table users add column quiet_from_m int default 0",
"alter table users add column quiet_to_m int default 0", "alter table users add column start_at real default 0",
"alter table users add column interval_s int default 0", "alter table users add column want_groups int default 0",
"alter table users add column clock_on int default 0", "alter table users add column reply_mode text default 'both'",
"alter table accounts add column orig_first text default ''", "alter table accounts add column orig_last text default ''",
"alter table accounts add column name_set int default 0", "alter table users add column present_text text default ''",
"alter table users add column anim_style text default ''", "alter table users add column status_mode text default ''",
"alter table users add column status_until real default 0"):
try: q(_s)
except sqlite3.OperationalError: pass
​q("create table if not exists sec_events(id integer primary key autoincrement, ts real, kind text, uid int, ack int default 0)")
q("create table if not exists codes(code text primary key, days int, used_by int default 0, used_at real default 0, created real)")
q("create table if not exists sent_log(uid int, acc int, day text, n int default 0, primary key(acc, day))")
q("create table if not exists admin_log(id integer primary key autoincrement, ts real, admin int, action text)")
​if not q("select 1 from plans").fetchone():
for _p in (("10 أيام", 10, "50 ⭐ أو 1$ محفظة"), ("شهر", 30, "120 ⭐ أو 3$ محفظة"), ("3 أشهر", 90, "300 ⭐ أو 8$ محفظة"), ("سنة", 365, "1000 ⭐ أو 25$ محفظة")):
q("insert into plans(name,days,price) values(?,?,?)", _p)
​def user(uid):
q("insert or ignore into users(id,joined) values(?,?)", (uid, time.time()))
return q("select * from users where id=?", (uid,)).fetchone()
​def cfg_get(k, d="1"):
r = q("select v from cfg where k=?", (k,)).fetchone(); return r["v"] if r else d
​def cfg_set(k, v): q("insert or replace into cfg values(?,?)", (k, v))
​def tog(text, cb, flag):
ic = ICONS.get("st_on" if flag else "st_off") if ICONS_ON[0] else None
if ic: return B(text=text, callback_data=cb, icon_custom_emoji_id=ic)
return B(text=f"{text} {'🟢' if flag else '🔴'}", callback_data=cb)
​def load_icons():
try: ICONS.clear(); ICONS.update(json.loads(cfg_get("btn_icons", "{}"))); ICONS_ON[0] = cfg_get("icons_on", "1") == "1"
except Exception: pass
load_icons()
​def alog(admin, text): q("insert into admin_log(ts,admin,action) values(?,?,?)", (time.time(), admin, text))
def is_vip(uid): return uid in ADMINS or user(uid)["vip_until"] > time.time()
def lim(uid): return VIP if is_vip(uid) else FREE
def add_vip(uid, days):
base = max(user(uid)["vip_until"], time.time())
q("update users set vip_until=? where id=?", (base + days * 86400, uid))
​def vip_text(uid):
if uid in ADMINS: return "∞ (أدمن)"
left = user(uid)["vip_until"] - time.time()
return f"فعّال ({int(left // 86400) + 1} يوم)" if left > 0 else "غير مفعّل"
​NOACC = "🔗 اربط حسابك أولاً من زر 📱 حساباتي"
def has_acc(uid): return bool(q("select 1 from accounts where uid=?", (uid,)).fetchone())
def eff_iv(u): return u["interval_s"] or (u["interval"] or 10) * 60
​def fmt_dur(x):
x = int(x)
if x < 60: return f"{x} ثانية"
if x < 3600: return f"{x // 60} دقيقة" if x % 60 == 0 else f"{x // 60}د {x % 60}ث"
if x < 86400: return f"{x // 3600} ساعة" if x % 3600 == 0 else f"{x // 3600}س {x % 3600 // 60}د"
return f"{x // 86400} يوم" if x % 86400 == 0 else f"{x // 86400}ي {x % 86400 // 3600}س"
​def parse_dur(t):
r = re.fullmatch(r"\s*(\d+)\s*(ث|s|sec|د|m|min|س|h|hr|ي|d|day)?\s*", (t or "").lower())
if not r: return None
n, un = int(r[1]), r[2] or "د"
return n * (1 if un in ("ث", "s", "sec") else 60 if un in ("د", "m", "min") else 3600 if un in ("س", "h", "hr") else 86400)
​def rep_list(u):
raw = u["reply_text"] or ""
try: v = json.loads(raw)
except ValueError: v = raw
if not isinstance(v, list): v = [str(v)] if raw.strip() else []
return [x for x in v if isinstance(x, str) and x.strip()]
​TZ = 3
def clock_line(uid):
u = user(uid); t = time.gmtime(time.time() + TZ * 3600)
return f"🕐 {deco(hm(t.tm_hour, t.tm_min, bool(u['show_ampm'])))}"
​_up = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
_lo = "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"
_dg = "𝟎𝟏𝟐𝟑𝟒𝟔𝟕𝟖𝟗"
def deco(s):
out = ""
for c in s:
if "A" <= c <= "Z": out += _up[ord(c) - 65]
elif "a" <= c <= "z": out += _lo[ord(c) - 97]
elif c.isdigit() and c.isascii(): out += _dg[int(c)]
else: out += c
return out
​clients = {}
tasks = {}
last_out = {}
last_chat_out = {}
last_in = {}
online_cache = {}
auto_until = {}
SESSION_GAP = 600
​async def owner_online(cl, acc_id):
t = time.time(); c = online_cache.get(acc_id)
if c and t - c[0] < 5: return c[1]
on = t - last_out.get(acc_id, 0) < 60
try:
r = await asyncio.wait_for(cl(GetUsersRequest([InputUserSelf()])), 0.4)
on = on or isinstance(r[0].status, UserStatusOnline)
except Exception: pass
online_cache[acc_id] = (t, on); return on
​async def online_poll(cl, acc_id):
while cl.is_connected() and clients.get(acc_id) is cl:
online_cache.pop(acc_id, None)
try: await owner_online(cl, acc_id)
except Exception: pass
await asyncio.sleep(3)
​STATUS = {"sleep": ("😴 نايم", "😴", "أنا نايم هسه 🌙 أرد عليك أول ما أصحى."),
"work": ("💼 بالدوام", "💼", "أنا بالدوام هسه 💼 أرجعلك بأقرب وقت."),
"trip": ("✈️ مسافر", "✈️", "أنا مسافر هسه ✈️ ما أكدر أرد، أرجعلك قريب."),
"busy": ("🔴 مشغول", "🔴", "مشغول هسه 🔴 اكتب سبب مراسلتك وأرد عليك لاحقاً."),
"eat": ("🍽 آكل", "🍽", "آكل هسه 🍽 دقايق وأجي.")}
def status_now(u):
st = STATUS.get(u["status_mode"] or "")
return st if st and (not u["status_until"] or u["status_until"] > time.time()) else None
​def attach_reply(cl, acc_id, uid):
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
​async def get_client(acc):
cl = clients.get(acc["id"])
if cl and cl.is_connected(): return cl
cl = TelegramClient(StringSession(fer.decrypt(acc["session"].encode()).decode()), API_ID, API_HASH)
await cl.connect()
if not await cl.is_user_authorized():
q("delete from accounts where id=?", (acc["id"],)); return None
attach_reply(cl, acc["id"], acc["uid"])
clients[acc["id"]] = cl
return cl
​DAILY = {"free": 120, "vip": 400}
def now_hour(): return int((time.time() / 3600 + TZ) % 24)
def now_min(): return int((time.time() / 60 + TZ * 60) % 1440)
def hm(h, m=0, ap=True):
return f"{h % 12 or 12}:{m:02d}" + (f" {'ص' if h < 12 else 'م'}" if ap else "")
​def cfg_chan():
v = cfg_get("log_channel", LOG_CHANNEL)
return int(v) if v.lstrip("-").isdigit() else v
​async def notify(text, admins=False):
try:
await bot.send_message(cfg_chan(), text[:4000])
except Exception:
if admins:
for a in ADMINS:
try: await bot.send_message(a, text[:4000])
except Exception: pass
​async def alert(uid, text, admin=False):
for t in ({uid} | (ADMINS if admin else set())):
try: await bot.send_message(t, text)
except Exception: pass
​def today_str(off=0): return time.strftime("%Y-%m-%d", time.gmtime(time.time() + TZ * 3600 - off * 86400))
def pick_text(u):
h = now_hour()
return ((u["text_am"] if 5 <= h < 16 else u["text_pm"]) or "").strip() or u["post_text"]
​bot = Bot(BOT_TOKEN); dp = Dispatcher(storage=MemoryStorage())
​@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
await state.clear(); uid = m.from_user.id
await m.answer(f"أهلاً بك 👋\n\nالبوت يعمل بنجاح!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="👑 لوحة الأدمن", callback_data="adm")]]))
​@dp.callback_query(F.data == "adm")
async def adm(c: CallbackQuery):
if c.from_user.id in ADMINS:
await c.message.edit_text("👑 لوحة الأدمن تعمل بنجاح", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="🔙 رجوع", callback_data="home")]]))
await c.answer()
​@dp.callback_query(F.data == "home")
async def home(c: CallbackQuery):
await c.message.edit_text("القائمة الرئيسية", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="👑 لوحة الأدمن", callback_data="adm")]]))
await c.answer()
​async def main():
await notify("✅ تم تشغيل البوت بنجاح")
await dp.start_polling(bot)
​if name == "main":
asyncio.run(main())