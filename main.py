import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import bot, dp, db
from utils.api.crypto import get_real_prices, suggest_coins
import re

COIN_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-_$]{0,14}$")

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from data.config import PRIMARY_ADMIN
MIN_INTERVAL = 40

# ==================== STATES ====================
class Register(StatesGroup):
    phone = State()
    name = State()

class EditProfile(StatesGroup):
    name = State()
    interval = State()

class PremiumOrder(StatesGroup):
    waiting_screenshot = State()

class CoinSearch(StatesGroup):
    waiting_for_symbol = State()

# ==================== KEYBOARDS ====================
def main_menu(user_id):
    kb = [[KeyboardButton(text="📊 Narxlarni ko'rish")],
          [KeyboardButton(text="🔔 Avto-xabardorlik"), KeyboardButton(text="👤 Profile")]]
    if user_id == PRIMARY_ADMIN:
        kb.append([KeyboardButton(text="👨‍💼 USERS Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]], resize_keyboard=True)

def is_registered(user_id):
    """Return True if the user exists in the Users table."""
    return bool(db.execute("SELECT 1 FROM Users WHERE id=?", (user_id,), fetchone=True))


def format_price(value, currency='USD'):
    """Format small prices with adaptive precision to avoid 0.0000 output.
    currency: 'USD', 'RUB', or 'UZS'
    """
    try:
        v = float(value)
    except Exception:
        return "N/A"

    # USD formatting
    if currency == 'USD':
        if v >= 1:
            return f"${v:,.2f}"
        if v >= 0.01:
            return f"${v:,.4f}"
        if v >= 0.0001:
            return f"${v:,.6f}"
        return f"${v:.8f}"

    # RUB formatting
    if currency == 'RUB':
        if v >= 1:
            return f"{v:,.2f} ₽"
        if v >= 0.01:
            return f"{v:,.4f} ₽"
        return f"{v:.6f} ₽"

    # UZS formatting (correct thousands separator, incl. negatives)
    if currency == 'UZS':
        if abs(v) >= 1000:
            return f"{int(round(v)):,} so'm"
        if abs(v) >= 1:
            return f"{v:,.2f} so'm"
        return f"{v:.4f} so'm"

    return str(value)

# ==================== START & REGISTRATION ====================
@dp.message(Command("start"))
async def start_bot(message: types.Message, state: FSMContext):
    await state.clear()
    user = db.execute("SELECT * FROM Users WHERE id=?", (message.from_user.id,), fetchone=True)
    
    if not user:
        kb = [[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]]
        await message.answer(
            "🤖 <b>Assalomu alaykum!</b>\n\nTelefon raqamingizni yuboring:",
            reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
            parse_mode="HTML"
        )
        await state.set_state(Register.phone)
    else:
        await message.answer(f"Xush kelibsiz! {user[3]} 👋", reply_markup=main_menu(message.from_user.id))

@dp.message(Register.phone, F.contact)
async def get_phone(message: types.Message, state: FSMContext):
    """Register the user immediately using the shared contact and Telegram full name."""
    phone = message.contact.phone_number
    full_name = message.from_user.full_name or message.from_user.username or "N/A"
    username = message.from_user.username or "N/A"

    try:
        db.execute(
            "INSERT INTO Users (id, phone, username, full_name, interval_min, is_premium, view_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message.from_user.id, phone, username, full_name, MIN_INTERVAL, 0, 0),
            commit=True
        )
        await message.answer("✅ Ro'yxatdan o'tdingiz!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
        logger.info(f"New user: {message.from_user.id}")
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await message.answer("❌ Xatolik! /start ni qayta yuboring.")
    finally:
        await state.clear()


# ==================== COIN SEARCH ====================
@dp.message(F.text == "📊 Narxlarni ko'rish")
async def show_coins_search(message: types.Message, state: FSMContext):
    await state.clear()    # Ensure user is registered before allowing coin search
    if not is_registered(message.from_user.id):
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))
    db.execute("UPDATE Users SET view_count = view_count + 1 WHERE id=?", (message.from_user.id,), commit=True)
    await state.set_state(CoinSearch.waiting_for_symbol)
    await message.answer(
        "💰 <b>Coin qidiruv</b>\n\nIstalgan coin/token belgisini kiriting👇\n"
        "<i>Masalan: BTC, ETH, SOL, PEPE, WIF, 1INCH, POPCAT...</i>\n"
        "Barcha kripto va tokenlar qo'llab-quvvatlanadi.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

@dp.message(CoinSearch.waiting_for_symbol, F.text)
async def search_coin(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Asosiy menyu", reply_markup=main_menu(message.from_user.id))
    
    # Extra safety: prevent unregistered users from performing searches
    if not is_registered(message.from_user.id):
        await state.clear()
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))

    coin = message.text.upper().strip().lstrip("$")

    if not COIN_RE.match(coin):
        return await message.answer("❌ To'g'ri coin belgisini kiriting (masalan: BTC, 1INCH, PEPE)")
    
    # Daily limit check for free users (5 views/day). Premium and admin exempt.
    u = db.execute("SELECT is_premium, daily_views, last_view_date FROM Users WHERE id=?", (message.from_user.id,), fetchone=True)
    today = datetime.now().strftime("%Y-%m-%d")
    if u:
        is_prem = bool(u[0]) or (message.from_user.id == PRIMARY_ADMIN)
        daily = u[1] or 0
        last_date = u[2]
        if last_date != today:
            db.execute("UPDATE Users SET daily_views=0, last_view_date=? WHERE id=?", (today, message.from_user.id), commit=True)
            daily = 0
        if not is_prem and daily >= 5:
            kb = InlineKeyboardBuilder()
            kb.button(text="💎 Premium", callback_data="buy_premium")
            kb.adjust(1)
            return await message.answer("⚠️ Bugun bepul limit (5 ta) tugadi. Iltimos ertaga qayta urinib ko'ring yoki Premium oling👇", parse_mode="HTML", reply_markup=kb.as_markup())
    
    loading = await message.answer("🔍 Qidirilmoqda...")
    
    try:
        data = await get_real_prices([coin])
        if not data or data[0] is None:
            await loading.delete()
            # O'xshash coinlarni taklif qilish
            try:
                suggs = await suggest_coins(coin, limit=5)
            except Exception:
                suggs = []
            if suggs:
                kb = InlineKeyboardBuilder()
                lines = []
                for s in suggs:
                    lines.append(f"• <b>{s['symbol']}</b> - {s['name']}")
                return await message.answer(
                    f"❌ <b>{coin}</b> topilmadi.\n\nBalki shulardan biri:\n"
                    + "\n".join(lines)
                    + "\n\nBelgisini aniq yozib qayta urining.",
                    parse_mode="HTML",
                )
            return await message.answer(f"❌  Bu turdagi coin mavjud emas. Iltimos to'g'ri kiriting.", parse_mode="HTML")

        d = data[0]
        usd_str = format_price(d.get('usd', 0), 'USD')
        rub_str = format_price(d.get('rub', 0), 'RUB')
        uzs_str = format_price(d.get('uzs', 0), 'UZS')
        coin_name = d.get('name')
        title = f"💰 <b>{coin}</b>" + (f" ({coin_name})" if coin_name and coin_name.upper() != coin else "")

        text = f"{title}\n\n💵 USD: <code>{usd_str}</code>\n🇷🇺 RUB: <code>{rub_str}</code>\n🇺🇿 UZS: <code>{uzs_str}</code>"
        # Yagona manbali (ekzotik) coinlar uchun ogohlantirish
        src = (d.get('source') or '')
        if src and '+' not in src:
            text += f"\n\n🔎 Manba: {src} (kam likvid - narx taxminiy)"
        
        # Increment daily_views for free users
        u2 = db.execute("SELECT is_premium FROM Users WHERE id=?", (message.from_user.id,), fetchone=True)
        is_prem2 = bool(u2[0]) if u2 else False
        if not is_prem2 and message.from_user.id != PRIMARY_ADMIN:
            db.execute("UPDATE Users SET daily_views = daily_views + 1 WHERE id=?", (message.from_user.id,), commit=True)
        
        exists = db.execute("SELECT * FROM CryptoPreferences WHERE user_id=? AND coin_symbol=?", 
                           (message.from_user.id, coin), fetchone=True)
        
        kb = InlineKeyboardBuilder()
        if exists:
            kb.button(text="✅ Kuzatuvda", callback_data=f"watching_{coin}")
        else:
            kb.button(text="🔔 Kuzatuvga qo'shish", callback_data=f"notify_{coin}")
        
        await loading.delete()
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.error(f"Search error: {e}")
        await loading.delete()
        await message.answer("❌ Xatolik yuz berdi.")

@dp.callback_query(F.data.startswith("notify_"))
async def add_watchlist(callback: types.CallbackQuery):
    # Prevent unregistered users from adding coins to watchlist
    if not is_registered(callback.from_user.id):
        await callback.answer("Iltimos /start bilan ro'yxatdan o'ting.", show_alert=True)
        return

    coin = callback.data.split("_")[1]
    try:
        exists = db.execute(
            "SELECT 1 FROM CryptoPreferences WHERE user_id=? AND coin_symbol=?",
            (callback.from_user.id, coin), fetchone=True)
        if exists:
            await callback.answer(f"✅ {coin} allaqachon kuzatuvda!", show_alert=True)
            return
        # INSERT OR IGNORE: ikki marta tez bosilgandagi race'dan himoya
        # (DB'dagi UNIQUE(user_id, coin_symbol) duplicate yozuvni bloklaydi)
        db.execute("INSERT OR IGNORE INTO CryptoPreferences (user_id, coin_symbol) VALUES (?, ?)",
                  (callback.from_user.id, coin), commit=True)
        await callback.answer(f"✅ {coin} qo'shildi!", show_alert=True)
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Kuzatuvda", callback_data=f"watching_{coin}")
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    except sqlite3.IntegrityError:
        logger.info(f"Watchlist duplicate: user {callback.from_user.id} already watches {coin}")
        await callback.answer(f"✅ {coin} allaqachon kuzatuvda!", show_alert=True)
    except sqlite3.Error as e:
        logger.error(f"Watchlist DB error for user {callback.from_user.id}, coin {coin}: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)
    except Exception as e:
        logger.error(f"Watchlist unexpected error for user {callback.from_user.id}, coin {coin}: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)

# ==================== AUTO-NOTIFY ====================
@dp.message(F.text == "🔔 Avto-xabardorlik")
async def auto_notify(message: types.Message):
    # Ensure the user is registered before showing auto-notify settings
    if not is_registered(message.from_user.id):
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))

    coins = db.execute("SELECT coin_symbol FROM CryptoPreferences WHERE user_id=?", 
                      (message.from_user.id,), fetchall=True)
    interval = db.execute("SELECT interval_min FROM Users WHERE id=?", 
                         (message.from_user.id,), fetchone=True)[0] or MIN_INTERVAL
    
    text = "<b>🔔 Avto-xabardorlik</b>\n\n"
    if not coins:
        text += "❌ Hech qanday coin yo'q.\n📊 Avval coin qo'shing."
        kb = InlineKeyboardBuilder()
    else:
        text += f"🕒 Interval: {interval}s\n📊 Coinlar: {len(coins)} ta\n\nO'chirish:"
        kb = InlineKeyboardBuilder()
        for c in coins:
            kb.button(text=f"❌ {c[0]}", callback_data=f"remove_{c[0]}")
        kb.button(text="🕒 Intervalni o'zgartirish", callback_data="edit_interval")
        kb.adjust(1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("remove_"))
async def remove_coin(callback: types.CallbackQuery):
    # Prevent unregistered users from removing coins
    if not is_registered(callback.from_user.id):
        await callback.answer("Iltimos /start bilan ro'yxatdan o'ting.", show_alert=True)
        return

    coin = callback.data.split("_")[1]
    db.execute("DELETE FROM CryptoPreferences WHERE user_id=? AND coin_symbol=?",
              (callback.from_user.id, coin), commit=True)
    await callback.answer(f"✅ {coin} o'chirildi!")
    await callback.message.delete()

# ==================== PROFILE ====================
@dp.message(F.text == "👤 Profile")
async def profile(message: types.Message):
    u = db.execute("SELECT full_name, phone, is_premium, premium_until, interval_min, view_count FROM Users WHERE id=?",
                  (message.from_user.id,), fetchone=True)
    
    if not u:
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))
    
    if message.from_user.id == PRIMARY_ADMIN:
        status, expire, is_prem = "⚡ Admin", "Cheksiz", True
    else:
        is_prem = bool(u[2])
        status = "💎 Premium" if is_prem else "🆓 Oddiy"
        expire = u[3] or "Yo'q"
    
    # Unpack the selected columns (order: full_name, phone, is_premium, premium_until, interval_min, view_count)
    full_name, phone, is_premium_flag, premium_until, interval_min, view_count = u
    username = message.from_user.username or "N/A"
    user_id = message.from_user.id

    text = f"<b>👤 ISM    {full_name}</b>\n📞 TELEFON     {phone}\n💬 USERNAME    @{username}\n🆔ID-raqam     {user_id}\n⭐OBUNA     {status}\n⏳MUDDAT     obuna {expire}\n🕒INTERVAL     {interval_min}s\n👁SO'ROVLAR     {view_count}"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Ismni tahrirlash", callback_data="edit_name")
    kb.button(text="🕒 Intervalni tahrirlash", callback_data="edit_interval")
    if not is_prem and message.from_user.id != PRIMARY_ADMIN:
        kb.button(text="💎 Premium", callback_data="buy_premium")
    kb.adjust(1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "edit_name")
async def edit_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Yangi ism:", reply_markup=back_keyboard())
    await state.set_state(EditProfile.name)
    await callback.answer()

@dp.message(EditProfile.name)
async def update_name(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Bekor qilindi", reply_markup=main_menu(message.from_user.id))
    
    db.execute("UPDATE Users SET full_name=? WHERE id=?", (message.text, message.from_user.id), commit=True)
    await message.answer("✅ Yangilandi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "edit_interval")
async def edit_interval(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    u = db.execute("SELECT is_premium FROM Users WHERE id=?", (callback.from_user.id,), fetchone=True)
    
    if callback.from_user.id == PRIMARY_ADMIN or (u and u[0]):
        await callback.message.answer(f"🕒 Yangi interval (min {MIN_INTERVAL}s):", reply_markup=back_keyboard())
        await state.set_state(EditProfile.interval)
    else:
        await callback.message.answer("⚠️ Faqat Premium!", parse_mode="HTML")
    await callback.answer()

@dp.message(EditProfile.interval)
async def update_interval(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("Bekor qilindi", reply_markup=main_menu(message.from_user.id))
    
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam!")
    
    val = int(message.text)
    if val < MIN_INTERVAL:
        return await message.answer(f"⚠️ Min {MIN_INTERVAL}s!")
    
    db.execute("UPDATE Users SET interval_min=? WHERE id=?", (val, message.from_user.id), commit=True)
    await message.answer(f"✅ Interval: {val}s", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# ==================== PREMIUM ====================
@dp.callback_query(F.data == "buy_premium")
async def premium_plans(callback: types.CallbackQuery):
    text = "💎 <b>Premium</b>\n❗️❗️❗️\nPastdagi carta raqamga korsatilga tarifdagi miqdorni tashlab screenshotni botga tashlang \n❗️Screenshotda carta-raqam , Ism-Familaya aniq korinishi kerak\nCarta raqam💳  <code>9860350142320406</code>\nCarta Egasini Ism,Familiyasi  <code>Ismoilova.F.</code>"
    plans = [("⭐ 1 oy - 5 000", "30"), ("🌙 2 oy - 10 000", "60"), ("🎁 3 oy - 15 000", "90"), 
             ("☀️ 6 oy - 20 000", "180"), ("💎 1 yil - 40 000", "365")]
    kb = InlineKeyboardBuilder()
    for name, days in plans:
        kb.button(text=name, callback_data=f"plan_{days}")
    kb.adjust(1)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("plan_"))
async def select_plan(callback: types.CallbackQuery, state: FSMContext):
    plan = callback.data.split("_")[1]
    await state.update_data(plan=plan)
    await callback.message.answer(f"✅ Tanlandi: {plan} kun\n📸 Chekni yuboring:")
    await state.set_state(PremiumOrder.waiting_screenshot)
    await callback.answer()

@dp.message(PremiumOrder.waiting_screenshot, F.photo)
async def handle_payment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    plan = data.get('plan', '30')

    # Try to extract amount and rate from message caption if provided
    caption_text = (message.caption or "")
    import re

    def extract_amount(text: str) -> str:
        # Try labeled amount like 'Summa: 5 000 UZS' or 'Amount:5000'
        m = re.search(r'(?i)(?:summa|amount|sum|total|сумма)[:\s]*([0-9\s\.,]+)', text)
        if m:
            raw = m.group(1)
            cleaned = re.sub(r"[\s,]+", "", raw)
            return cleaned
        # Fallback: find first large number possibly followed by currency
        m2 = re.search(r'([0-9]+(?:[ \,\.][0-9]{3})*(?:[.,][0-9]+)?)\s*(UZS|UZ|so\'m|so’м|som|сом|₽|rub|USD|usd)?', text, re.IGNORECASE)
        if m2:
            num = re.sub(r"[\s,]+", "", m2.group(1))
            currency = m2.group(2) or ""
            return f"{num} {currency.strip()}".strip()
        logger.info(f"Amount not found in caption: {text!r}")
        return "N/A"

    def extract_rate(text: str) -> str:
        # Try labeled rate like 'Kurs: 1.23'
        m = re.search(r'(?i)(?:kurs|kursi|rate)[:\s]*([0-9\s\.,]+)', text)
        if m:
            raw = m.group(1)
            return raw.strip()
        # Try pattern like '1 USD = 11 000 UZS' and compute implied rate (UZS per USD)
        m2 = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*USD\s*=\s*([0-9]+(?:[ \,\.][0-9]{3})*(?:[\.,][0-9]+)?)\s*UZS', text, re.IGNORECASE)
        if m2:
            try:
                usd = float(m2.group(1).replace(',', '.'))
                uzs = float(re.sub(r"[\s,]+", "", m2.group(2)).replace(',', '.'))
                # rate as UZS per USD
                return f"{uzs / usd:.2f}"
            except Exception:
                pass
        logger.info(f"Rate not found in caption: {text!r}")
        return "N/A"

    amount = extract_amount(caption_text)
    rate = extract_rate(caption_text)

    # Get phone from DB if available
    phone_row = db.execute("SELECT phone FROM Users WHERE id=?", (message.from_user.id,), fetchone=True)
    phone = phone_row[0] if phone_row else "N/A"

    username = message.from_user.username or "N/A"
    full_name = message.from_user.full_name or username or "N/A"
    sent_at = message.date.strftime("%Y-%m-%d %H:%M:%S") if message.date else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    deadline = (datetime.now() + timedelta(days=int(plan))).strftime("%Y-%m-%d")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data=f"accept_{message.from_user.id}_{plan}")
    kb.button(text="❌ Rad etish", callback_data=f"reject_{message.from_user.id}")
    kb.adjust(1)

    caption = (
        "💰 To'lov\n"
        f"👤 {full_name}\n"
        f"📞 {phone}\n"
        f"💬 @{username}\n"
        f"🆔 {message.from_user.id}\n"
        f"📦 {plan} kun\n"
        f"🕒 Yuborilgan: {sent_at}\n"
        f"⏳ Muddati: {deadline}\n"
        f"💸 Summa: {amount}\n"
        f"💱 Kurs: {rate}\n"
    )

    # Save last payment info to user record so admin can see it in the panel
    try:
        db.execute(
            "UPDATE Users SET last_payment_amount=?, last_payment_rate=? WHERE id=?",
            (amount, rate, message.from_user.id), commit=True
        )
    except Exception as e:
        logger.error(f"Failed to save last payment info: {e}")

    try:
        await bot.send_photo(PRIMARY_ADMIN, message.photo[-1].file_id,
            caption=caption,
            reply_markup=kb.as_markup())
        await message.answer("✅ Yuborildi! Admin tomonidan tasdiqlanishini kuting.", reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        logger.error(f"Error sending payment to admin: {e}")
        await message.answer("❌ Xatolik ", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# ==================== ADMIN ====================
ADMIN_PAGE_SIZE = 10

def _admin_page_keyboard(page: int):
    """Bitta admin sahifasi uchun user tugmalari + Prev/Next navigatsiya."""
    total = db.execute("SELECT COUNT(*) FROM Users", fetchone=True)[0] or 0
    pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    users = db.execute(
        "SELECT id, full_name, is_premium, view_count FROM Users ORDER BY id LIMIT ? OFFSET ?",
        (ADMIN_PAGE_SIZE, page * ADMIN_PAGE_SIZE), fetchall=True)
    kb = InlineKeyboardBuilder()
    for u in users:
        icon = "💎" if u[2] else "👤"
        kb.button(text=f"{icon} {u[1]} ({u[3]})", callback_data=f"user_{u[0]}")
    kb.adjust(1)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(text="◀️ Prev", callback_data=f"admin_users_{page - 1}"))
    if page < pages - 1:
        nav.append(types.InlineKeyboardButton(text="Next ▶️", callback_data=f"admin_users_{page + 1}"))
    if nav:
        kb.row(*nav)
    return kb.as_markup(), total, page, pages

@dp.message(F.text == "👨‍💼 USERS Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != PRIMARY_ADMIN:
        return

    markup, total, page, pages = _admin_page_keyboard(0)
    await message.answer(f"👥 Users: {total} (sahifa {page + 1}/{pages})", reply_markup=markup)

@dp.callback_query(F.data.startswith("admin_users_"))
async def admin_panel_page(callback: types.CallbackQuery):
    if callback.from_user.id != PRIMARY_ADMIN:
        await callback.answer()
        return
    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 0
    markup, total, page, pages = _admin_page_keyboard(page)
    await callback.message.edit_text(f"👥 Users: {total} (sahifa {page + 1}/{pages})", reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data.startswith("user_"))
async def manage_user(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    # Select explicit columns to avoid confusion if DB schema changes
    u = db.execute(
        "SELECT id, full_name, phone, username, is_premium, premium_until, premium_plan_days, premium_given_at, last_payment_amount, last_payment_rate, interval_min, view_count FROM Users WHERE id=?",
        (uid,), fetchone=True
    )

    if not u:
        await callback.answer("User not found", show_alert=True)
        return

    (user_id, full_name, phone, username, is_prem_flag, premium_until, premium_plan_days, premium_given_at, last_payment_amount, last_payment_rate, interval_min, view_count) = u
    username_display = username or "N/A"
    status = "💎 Premium" if is_prem_flag else "🆓 Oddiy"

    text = (
        f"<b>👤ISM   {full_name}</b>\n"
        f"📞TELEFON   {phone}\n"
        f"💬USERNAME   @{username_display}\n"
        f"🆔ID-raqam   {user_id}\n"
        f"⭐OBUNA   {status}"
    )

    # Show premium metadata if available
    if is_prem_flag:
        plan_text = f"{premium_plan_days} kun" if premium_plan_days else "Noma'lum"
        given_text = premium_given_at or "N/A"
        until_text = premium_until or "N/A"
        text += f"\n⏳Tugash Muddati: {until_text}\n📦Tur: {plan_text}\n🗓Berilgan: {given_text}"

    # Show last payment details if available
    if last_payment_amount or last_payment_rate:
        text += f"\n💸Summa: {last_payment_amount or 'N/A'}\n💱Kurs: {last_payment_rate or 'N/A'}"

    text += f"\n🕒INTERVAL   {interval_min}s\n👁SO'ROVLAR   {view_count}"

    kb = InlineKeyboardBuilder()
    if not is_prem_flag:
        kb.button(text="🎁 Give Premium", callback_data=f"give_{uid}")
    else:
        kb.button(text="🚫 Remove Premium", callback_data=f"take_{uid}")
    kb.button(text="🔙 Back", callback_data="back_admin")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("give_"))
async def give_premium_menu(callback: types.CallbackQuery):
    uid = callback.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    plans = [("🌙 1 oy", "30"), ("🌙 2 oy", "60"), ("🌙 3 oy", "90"), ("☀️ 1 yil", "365")]
    for name, days in plans:
        kb.button(text=name, callback_data=f"accept_{uid}_{days}")
    kb.adjust(1)
    await callback.message.edit_text("Muddat:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("accept_"))
async def accept_payment(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    # Expect format: accept_<uid>_<days>
    if len(parts) < 3:
        await callback.answer("❌ Invalid callback data", show_alert=True)
        return
    uid, days = int(parts[1]), int(parts[2])
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    given_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        "UPDATE Users SET is_premium=1, premium_until=?, premium_plan_days=?, premium_given_at=? WHERE id=?",
        (until, days, given_at, uid), commit=True
    )
    await bot.send_message(uid, f"🎉 Premium faol ({days} kun)!")
    await callback.answer("✅ Tasdiqlandi")
    await callback.message.delete()

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    await bot.send_message(uid, "❌ Chek rad etildi! Iltimos, to'lovni qayta amalga oshiring. Yoki admin bilan bog'laning. @c0mrade_p2p")
    await callback.message.delete()

@dp.callback_query(F.data.startswith("take_"))
async def take_premium(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    # Clear premium flags and metadata
    db.execute("UPDATE Users SET is_premium=0, premium_until=NULL, premium_plan_days=NULL, premium_given_at=NULL WHERE id=?", (uid,), commit=True)
    # Notify the user that admin will remove their premium
    await bot.send_message(uid, "Admin sizdan premium obunasini olib qoydi😞")
    await callback.answer("✅ Olib tashlandi")
    await callback.message.delete()

@dp.callback_query(F.data == "back_admin")
async def back_admin(callback: types.CallbackQuery):
    await callback.message.delete()

# ==================== BACK TO MAIN ====================
@dp.message(F.text == "🏠 Asosiy menyu")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu", reply_markup=main_menu(message.from_user.id))

# ==================== CATCH ALL ====================
@dp.message(F.text)
async def catch_all(message: types.Message):
    await message.answer("Tushunarsiz buyruq")

# ==================== MAIN ====================
async def main():
    db.create_tables()
    
    # Avto-xabardorlik schedulerni ishga tushirish
    from utils.scheduler import start_scheduler
    
    # Ikkalasini parallel ishga tushirish
    async def run_bot():
        logger.info("🤖 Bot started!")
        await dp.start_polling(bot)
    
    async def run_scheduler():
        await start_scheduler()
    
    # Ikkalasini bir vaqtda ishga tushirish
    await asyncio.gather(
        run_bot(),
        run_scheduler()
    )

if __name__ == "__main__":
    asyncio.run(main())