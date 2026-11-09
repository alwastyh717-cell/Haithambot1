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
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError

logging.basicConfig(level=logging.INFO)
ICONS = {}; ICONS_ON = [True]
def B(**kw):
    cb = kw.get("callback_data") or ("owner" if kw.get("url") else None); ic = kw.get("icon_custom_emoji_id") or (ICONS.get(cb) if ICONS_ON[0] and cb else None)
    if ic:
        kw["icon_custom_emoji_id"] = ic; kw["text"] = re.sub(r"^[^\w(]+", "", kw.get("text", "")) or kw.get("text", "")
    return _IB(**kw)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9286024586:AAGL6Ht3lAY6RCVo0cTqAdM-MymsoPMw4ys")
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "7753146356").split(",") if x.strip()}
ROOT = set(ADMINS)
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "@RX62X")
API_ID = int(os.environ.get("API_ID", "36444028"))
API_HASH = os.environ.get("API_HASH", "92aac2e192857ff973a9b3ae2a3274ca")
if not API_ID or not API_HASH:
    raise SystemExit("ضع API_ID و API_HASH بأعلى الملف (من my.telegram.org)")
OWNER = "@K000OOO"

FREE = dict(accounts=1, chats=1)
VIP = dict(accounts=6, chats=10)

_k = os.environ.get("FERNET_KEY", "").encode()
if not _k:
    if not os.path.exists("fernet.key"):
        open("fernet.key", "wb").write(Fernet.generate_key())
    try: os.chmod("fernet.key", 0o600)
    except OSError: pass
    _k = open("fernet.key", "rb").read()
fer = Fernet(_k)

db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
def q(sql, a=()):
    cur = db.execute(sql, a); db.commit(); return cur

q("create table if not exists users(id integer primary key, banned int default 0, reply_on int default 0, reply_text text default '')")
q("create table if not exists accounts(id integer primary key autoincrement, uid int, phone text, name text, session text)")
q("create table if not exists channels(chat text primary key, link text)")
q("create table if not exists replied(acc int, uid int, ts real, primary key(acc,uid))")
q("create table if not exists cfg(k text primary key, v text)")
q("create table if not exists clock_chats(id integer primary key autoincrement, uid int, chat_id int, title text, orig_title text, orig_desc text, mode text)")
q("create table if not exists plans(id integer primary key autoincrement, name text, days int, price text)")

for _s in ("alter table users add column vip_until real default 0", "alter table users add column joined real default 0",
           "alter table channels add column link text", "alter table accounts add column created real default 0",
           "alter table users add column uname text default ''", "alter table users add column fname text default ''",
           "alter table users add column notified_new int default 0", "alter table users add column show_ampm int default 1",
           "alter table users add column clock_on int default 0", "alter table users add column reply_mode text default 'both'",
           "alter table accounts add column orig_first text default ''", "alter table accounts add column orig_last text default ''",
           "alter table accounts add column name_set int default 0", "alter table users add column present_text text default ''",
           "alter table users add column anim_style text default ''", "alter table users add column status_mode text default ''",
           "alter table users add column status_until real default 0"):
    try: q(_s)
    except sqlite3.OperationalError: pass

q("create table if not exists sec_events(id integer primary key autoincrement, ts real, kind text, uid int, ack int default 0)")
q("create table if not exists codes(code text primary key, days int, used_by int default 0, used_at real default 0, created real)")
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

def tog(text, cb, flag):
    ic = ICONS.get("st_on" if flag else "st_off") if ICONS_ON[0] else None
    if ic: return B(text=text, callback_data=cb, icon_custom_emoji_id=ic)
    return B(text=f"{text} {'🟢' if flag else '🔴'}", callback_data=cb)

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

def rep_list(u):
    raw = u["reply_text"] or ""
    try: v = json.loads(raw)
    except ValueError: v = raw
    if not isinstance(v, list): v = [str(v)] if raw.strip() else []
    return [x for x in v if isinstance(x, str) and x.strip()]

TZ = 3
def clock_line(uid):
    u = user(uid); t = time.gmtime(time.time() + TZ * 3600)
    return f"🕐 {deco(hm(t.tm_hour, t.tm_min, bool(u['show_ampm'])))}"

_up = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
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

def now_hour(): return int((time.time() / 3600 + TZ) % 24)
def now_min(): return int((time.time() / 60 + TZ * 60) % 1440)
def hm(h, m=0, ap=True):
    return f"{h % 12 or 12}:{m:02d}" + (f" {'ص' if h < 12 else 'م'}" if ap else "")

def cfg_chan():
    v = cfg_get("log_channel", LOG_CHANNEL)
    return int(v) if v.lstrip("-").isdigit() else v

async def notify(text, admins=False):
    try:
        await bot.send_message(cfg_chan(), text[:4000])
    except Exception:
        if admins:
            for a in ADMINS:
                try: await bot.send_message(a, text[:4000])
                except Exception: pass

async def alert(uid, text, admin=False):
    for t in ({uid} | (ADMINS if admin else set())):
        try: await bot.send_message(t, text)
        except Exception: pass

def main_text(uid):
    u = user(uid)
    na = q("select count(*) c from accounts where uid=?", (uid,)).fetchone()["c"]
    head = (clock_line(uid) + "\n\n") if u["clock_on"] else ""
    return head + (f"📡 حالتك:\n"
            f"├ 📱 الحسابات: {na}\n"
            f"├ 💬 الرد بالخاص: {'يعمل' if u['reply_on'] else 'متوقف'} {'🟢' if u['reply_on'] else '🔴'}\n"
            f"└ 💎 VIP: {vip_text(uid)}\n\n"
            f"👇 اختر من الأزرار:")

def main_kb(uid):
    u = user(uid)
    na = q("select count(*) c from accounts where uid=?", (uid,)).fetchone()["c"]
    vip = is_vip(uid)
    rows = [
        [B(text=f"📱 حساباتي ({na})", callback_data="accs")],
        [tog("💬 رد بالخاص", "ar", u["reply_on"])],
        [B(text="🕐 الساعة الوقتية", callback_data="clk")],
        [B(text="📢 ساعة القناة / الكروب", callback_data="cc")],
        [B(text="💎 VIP ✅ (تجديد)" if vip else "⭐ تفعيل VIP", callback_data="vipbuy"), B(text="🎟 تفعيل كود", callback_data="rc")],
        [B(text="🎁 VIP مجاناً", callback_data="vipfree")],
        [B(text="🧑‍💻 تواصل مع المالك", url="https://t.me/" + OWNER.lstrip("@"))],
    ]
    if uid in ADMINS: rows.append([B(text="👑 لوحة الأدمن", callback_data="adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back(cb="home"): return InlineKeyboardMarkup(inline_keyboard=[[B(text="🔙 رجوع", callback_data=cb)]])

bot = Bot(BOT_TOKEN); dp = Dispatcher(storage=MemoryStorage())
pending = {}
login_hits = {}
def login_ok(uid, limit=10, window=3600):
    t = time.time(); L = [x for x in login_hits.get(uid, []) if t - x < window]
    ok = len(L) < limit
    if ok: L.append(t)
    login_hits[uid] = L
    return ok

@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear(); uid = m.from_user.id
    await m.answer(f"أهلاً {deco(m.from_user.first_name or '')} 👋\n\n" + main_text(uid), reply_markup=main_kb(uid))

@dp.callback_query(F.data.in_({"home", "chk"}))
async def home(c: CallbackQuery, state: FSMContext):
    await state.clear(); await c.message.edit_text(main_text(c.from_user.id), reply_markup=main_kb(c.from_user.id)); await c.answer()

@dp.callback_query(F.data == "accs")
async def accs(c: CallbackQuery):
    rows = []; n_ = q("select count(*) c from accounts where uid=?", (c.from_user.id,)).fetchone()["c"]
    txt = f"📱 حساباتي\n\n🔢 عدد الحسابات: {n_} / {lim(c.from_user.id)['accounts']}\n\n"
    for a in q("select * from accounts where uid=?", (c.from_user.id,)).fetchall():
        txt += f"• {deco(a['name'])} — {deco(a['phone'])}\n"
        rows.append([B(text=f"🗑 حذف {a['phone']}", callback_data=f"ad:{a['id']}")])
    rows.append([B(text="➕ إضافة حساب", callback_data="addacc")]); rows.append([B(text="🔙 رجوع", callback_data="home")])
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data.startswith("ad:"))
async def ad(c: CallbackQuery):
    aid = int(c.data[3:]); a = q("select * from accounts where id=? and uid=?", (aid, c.from_user.id)).fetchone()
    if a:
        await clock_restore(a)
        cl = clients.pop(aid, None)
        if cl: await cl.disconnect()
        q("delete from accounts where id=?", (aid,))
    await accs(c)

class S(StatesGroup):
    phone = State(); code = State(); pw = State(); rep = State()

@dp.callback_query(F.data == "addacc")
async def addacc(c: CallbackQuery, state: FSMContext):
    if q("select count(*) c from accounts where uid=?", (c.from_user.id,)).fetchone()["c"] >= lim(c.from_user.id)["accounts"]:
        return await c.answer("وصلت للحد الأقصى للحسابات 💎 رقّي إلى VIP لزيادة الحد", show_alert=True)
    await state.set_state(S.phone); await c.message.edit_text("📞 أرسل رقم الحساب مع رمز الدولة مثل: +964770xxxxxxx", reply_markup=back("accs")); await c.answer()

@dp.message(S.phone)
async def ph(m: Message, state: FSMContext):
    if not login_ok(m.from_user.id): return await m.answer("⛔ محاولات كثيرة.")
    phone = re.sub(r"[^\d+]", "", m.text or "")
    cl = TelegramClient(StringSession(), API_ID, API_HASH); await cl.connect()
    try: sent = await cl.send_code_request(phone)
    except Exception as e:
        await cl.disconnect(); return await m.answer(f"❌ تعذر إرسال الكود: {e}")
    pending[m.from_user.id] = (cl, phone, sent.phone_code_hash); await state.set_state(S.code)
    await m.answer("📩 أرسل الكود **مع فواصل بين الأرقام** مثل 1-2-3-4-5", parse_mode="Markdown")

async def finish_login(m, state, cl, phone):
    me = await cl.get_me()
    sess = fer.encrypt(cl.session.save().encode()).decode()
    q("insert into accounts(uid,phone,name,session,created) values(?,?,?,?,?)", (m.from_user.id, phone, me.first_name or "acc", sess, time.time()))
    aid = q("select max(id) m from accounts").fetchone()["m"]
    attach_reply(cl, aid, m.from_user.id); clients[aid] = cl
    await notify(f"📱 ربط حساب جديد\n👤 {user_tag(m.from_user.id)}\n📞 {mask(phone)}")
    await state.clear(); await m.answer("✅ تم ربط الحساب بنجاح.", reply_markup=main_kb(m.from_user.id))

@dp.message(S.code)
async def code(m: Message, state: FSMContext):
    cl, phone, h = pending[m.from_user.id]
    try: await cl.sign_in(phone, re.sub(r"\D", "", m.text or ""), phone_code_hash=h)
    except errors.SessionPasswordNeededError:
        await state.set_state(S.pw); return await m.answer("🔐 أرسل كلمة مرور التحقق بخطوتين:")
    except Exception as e:
        return await m.answer(f"❌ {e}")
    await finish_login(m, state, cl, phone)

@dp.message(S.pw)
async def pw(m: Message, state: FSMContext):
    cl, phone, _ = pending[m.from_user.id]
    try: await cl.sign_in(password=m.text)
    except Exception as e:
        return await m.answer(f"❌ {e}")
    try: await m.delete()
    except Exception: pass
    await finish_login(m, state, cl, phone)

@dp.callback_query(F.data == "ar")
async def ar(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    u = user(c.from_user.id); reps = rep_list(u)
    txt = f"💬 الرد بالخاص: {'يعمل' if u['reply_on'] else 'متوقف'} {'🟢' if u['reply_on'] else '🔴'}\n\n📝 الكليشات:\n" + ("\n".join(reps) or "لا يوجد")
    rows = [[B(text="⏹ إيقاف" if u["reply_on"] else "▶️ تشغيل", callback_data="art")],
            [B(text="➕ إضافة كليشة", callback_data="arx")],
            [B(text="🔙 رجوع", callback_data="home")]]
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data == "art")
async def art(c: CallbackQuery):
    q("update users set reply_on=1-reply_on where id=?", (c.from_user.id,)); await ar(c, None)

@dp.callback_query(F.data == "arx")
async def arx(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.rep); await c.message.edit_text("✍️ أرسل نص كليشة الرد الآلي:", reply_markup=back("ar")); await c.answer()

@dp.message(S.rep)
async def rep_in(m: Message, state: FSMContext):
    uid = m.from_user.id; txt = (m.text or "").strip()
    if not txt: return await m.answer("أرسل نصاً صحيحاً.")
    q("update users set reply_text=?, reply_on=1 where id=?", (json.dumps([txt], ensure_ascii=False), uid))
    await state.clear(); await m.answer("✅ تم حفظ كليشة الرد الآلي.", reply_markup=main_kb(uid))

@dp.callback_query(F.data == "clk")
async def clk(c: CallbackQuery, state: FSMContext):
    await state.clear(); uid = c.from_user.id; u = user(uid)
    rows = ([[B(text="❌ إيقاف الساعة", callback_data="clkoff")], [B(text="🔄 تغيير الصيغة", callback_data="clkf")]] if u["clock_on"]
            else [[B(text="✅ تفعيل الساعة الوقتية", callback_data="clkf")]]
    ) + [[B(text="🔙 رجوع", callback_data="home")]]
    await c.message.edit_text(f"🕐 الساعة الوقتية\n\n{clock_line(uid)}\n\nيظهر الوقت بجانب اسم حسابك المربوط بتلكرام ويتحدّث كل دقيقة.\n\nالحالة: {'مفعّل ✅' if u['clock_on'] else 'غير مفعّل'}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@dp.callback_query(F.data == "clkf")
async def clkf(c: CallbackQuery):
    if not has_acc(c.from_user.id): return await c.answer(NOACC, show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="☀️🌙 مع ص / م", callback_data="clks:1")], [B(text="⏭ بدون ص / م", callback_data="clks:0")], [B(text="🔙 رجوع", callback_data="clk")]])
    await c.message.edit_text("اختر صيغة الوقت:", reply_markup=kb); await c.answer()

@dp.callback_query(F.data.startswith("clks:"))
async def clks(c: CallbackQuery):
    uid = c.from_user.id
    q("update users set clock_on=1, show_ampm=? where id=?", (int(c.data[5:]), uid)); u = user(uid)
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        try: await clock_apply(acc, u)
        except Exception: pass
    await c.message.edit_text(main_text(uid), reply_markup=main_kb(uid))
    await c.answer("✅ تم تفعيل الساعة بجانب اسمك", show_alert=True)

@dp.callback_query(F.data == "clkoff")
async def clkoff(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id; q("update users set clock_on=0 where id=?", (uid,))
    for acc in q("select * from accounts where uid=?", (uid,)).fetchall():
        await clock_restore(acc)
    await clk(c, state)

clock_last = {}
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
    try: await cl(UpdateProfileRequest(first_name=first, last_name=last))
    except Exception: pass
    return True

async def clock_restore(acc):
    if not acc["name_set"]: return
    try:
        cl = await get_client(acc)
        if cl: await cl(UpdateProfileRequest(first_name=acc["orig_first"] or "-", last_name=acc["orig_last"] or ""))
    except Exception: pass
    q("update accounts set name_set=0 where id=?", (acc["id"],))

async def clock_loop():
    while True:
        await asyncio.sleep(60 - time.time() % 60 + 1)
        for u in q("select * from users where clock_on=1 and banned=0").fetchall():
            for acc in q("select * from accounts where uid=?", (u["id"],)).fetchall():
                try: await clock_apply(acc, u)
                except Exception: pass
                await asyncio.sleep(0.5)

@dp.callback_query(F.data == "vipbuy")
async def vipbuy(c: CallbackQuery):
    await c.message.edit_text(f"💎 تفعيل VIP\n\nتواصل مع المالك للتفعيل: {OWNER}\nآيديك: `{c.from_user.id}`", parse_mode="Markdown", reply_markup=back("home"))
    await c.answer()

@dp.callback_query(F.data == "vipfree")
async def vipfree(c: CallbackQuery):
    me = await bot.get_me()
    await c.message.edit_text(f"🎁 احصل على VIP مجاناً عبر مشاركة رابطك:\nhttps://t.me/{me.username}?start=ref_{c.from_user.id}", reply_markup=back("home"))
    await c.answer()

@dp.callback_query(F.data == "rc")
async def rc(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.rep); await c.message.edit_text("🎟 أرسل كود التفعيل:", reply_markup=back("home")); await c.answer()

@dp.callback_query(F.data == "adm")
async def adm(c: CallbackQuery):
    if c.from_user.id in ADMINS:
        await c.message.edit_text("👑 لوحة الأدمن", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="🔙 رجوع", callback_data="home")]]))
    await c.answer()

async def main():
    asyncio.create_task(clock_loop())
    await notify("✅ تم تشغيل البوت بنجاح")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
