import asyncio
import logging
import sqlite3
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
MIN_INTERVAL = 10

# ==================== STATES ====================
class Register(StatesGroup):
    phone = State()
    name = State()

class EditProfile(StatesGroup):
    name = State()
    interval = State()

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
            "🤖 <b>Assalomu alaykum!</b>\n\n"
            "Bu <b>Crypto Narx</b> boti — jonli kripto narxlar va avto-xabardorliklar.\n"
            "Boshlash uchun telefon raqamingizni yuboring 👇",
            reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
            parse_mode="HTML"
        )
        await state.set_state(Register.phone)
    else:
        await message.answer(f"👋 Xush kelibsiz, <b>{user[3]}</b>!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

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
        await message.answer("✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n📊 Narxlarni ko'rish uchun menyudan foydalaning.", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
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
        "💰 <b>Coin qidiruv</b>\n\nIstalgan coin/token belgisini kiriting 👇\n"
        "<i>Masalan: BTC, ETH, SOL, PEPE, WIF, 1INCH, POPCAT...</i>",
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
        return await message.answer("❌ Noto'g'ri belgi. Masalan: <b>BTC</b>, <b>1INCH</b>, <b>PEPE</b>", parse_mode="HTML")

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
                    lines.append(f"• <b>{s['symbol']}</b> — {s['name']}")
                return await message.answer(
                    f"❌ <b>{coin}</b> topilmadi.\n\nBalki shulardan birini nazarda tutgandirsiz:\n"
                    + "\n".join(lines)
                    + "\n\nBelgisini aniq yozib qayta urining.",
                    parse_mode="HTML",
                )
            return await message.answer(f"❌ <b>{coin}</b> topilmadi.\nImloni tekshiring yoki coingecko.com dan aniq tickerni ko'rib qayta urining.", parse_mode="HTML")

        d = data[0]
        usd_str = format_price(d.get('usd', 0), 'USD')
        rub_str = format_price(d.get('rub', 0), 'RUB')
        uzs_str = format_price(d.get('uzs', 0), 'UZS')
        coin_name = d.get('name')
        title = f"💰 <b>{coin}</b>" + (f" <i>({coin_name})</i>" if coin_name and coin_name.upper() != coin else "")

        text = f"{title}\n\n💵 <b>USD:</b> <code>{usd_str}</code>\n🇷🇺 <b>RUB:</b> <code>{rub_str}</code>\n🇺🇿 <b>UZS:</b> <code>{uzs_str}</code>"
        # Yagona manbali (ekzotik) coinlar uchun ogohlantirish
        src = (d.get('source') or '')
        if src and '+' not in src:
            text += f"\n\n🔎 Manba: {src} (kam likvid - narx taxminiy)"

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
        await message.answer("❌ Kechirasiz, xatolik yuz berdi. Birozdan so'ng qayta urining.")

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
        text += "Hozircha kuzatuvda coin yo'q.\n📊 Avval narx qidirib, <b>🔔 Kuzatuvga qo'shish</b> ni bosing."
        kb = InlineKeyboardBuilder()
    else:
        text += f"🕒 Interval: <b>{interval}s</b>\n📊 Kuzatuvda: <b>{len(coins)} ta</b>\n\nO'chirish uchun bosing 👇"
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
    u = db.execute("SELECT full_name, phone, interval_min, view_count FROM Users WHERE id=?",
                  (message.from_user.id,), fetchone=True)

    if not u:
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))

    # Unpack the selected columns (order: full_name, phone, interval_min, view_count)
    full_name, phone, interval_min, view_count = u
    username = message.from_user.username or "N/A"
    user_id = message.from_user.id

    text = (
        f"👤 <b>Profil</b>\n\n"
        f"📝 Ism: <b>{full_name}</b>\n"
        f"📞 Telefon: <code>{phone}</code>\n"
        f"💬 Username: @{username}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🕒 Interval: {interval_min}s\n"
        f"👁 So'rovlar: {view_count}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Ismni tahrirlash", callback_data="edit_name")
    kb.button(text="🕒 Intervalni tahrirlash", callback_data="edit_interval")
    kb.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "edit_name")
async def edit_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Yangi ismingizni kiriting:", reply_markup=back_keyboard())
    await state.set_state(EditProfile.name)
    await callback.answer()

@dp.message(EditProfile.name)
async def update_name(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    
    db.execute("UPDATE Users SET full_name=? WHERE id=?", (message.text, message.from_user.id), commit=True)
    await message.answer("✅ Yangilandi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "edit_interval")
async def edit_interval(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(f"🕒 Yangi intervalni soniyada kiriting (min: {MIN_INTERVAL}s):", reply_markup=back_keyboard())
    await state.set_state(EditProfile.interval)
    await callback.answer()

@dp.message(EditProfile.interval)
async def update_interval(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(message.from_user.id))

    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting!")

    val = int(message.text)
    if val < MIN_INTERVAL:
        return await message.answer(f"⚠️ Minimal interval: {MIN_INTERVAL}s!")

    db.execute("UPDATE Users SET interval_min=? WHERE id=?", (val, message.from_user.id), commit=True)
    await message.answer(f"✅ Interval yangilandi: <b>{val}s</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
    await state.clear()

# ==================== ADMIN ====================
ADMIN_PAGE_SIZE = 10

def _admin_page_keyboard(page: int):
    """Bitta admin sahifasi uchun user tugmalari + Prev/Next navigatsiya."""
    total = db.execute("SELECT COUNT(*) FROM Users", fetchone=True)[0] or 0
    pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    users = db.execute(
        "SELECT id, full_name, view_count FROM Users ORDER BY id LIMIT ? OFFSET ?",
        (ADMIN_PAGE_SIZE, page * ADMIN_PAGE_SIZE), fetchall=True)
    kb = InlineKeyboardBuilder()
    for u in users:
        kb.button(text=f"👤 {u[1]} ({u[2]})", callback_data=f"user_{u[0]}")
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
        "SELECT id, full_name, phone, username, interval_min, view_count FROM Users WHERE id=?",
        (uid,), fetchone=True
    )

    if not u:
        await callback.answer("User not found", show_alert=True)
        return

    (user_id, full_name, phone, username, interval_min, view_count) = u
    username_display = username or "N/A"

    text = (
        f"👤 <b>{full_name}</b>\n\n"
        f"📞 Telefon: <code>{phone}</code>\n"
        f"💬 Username: @{username_display}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🕒 Interval: {interval_min}s\n"
        f"👁 So'rovlar: {view_count}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back", callback_data="back_admin")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "back_admin")
async def back_admin(callback: types.CallbackQuery):
    await callback.message.delete()

# ==================== BACK TO MAIN ====================
@dp.message(F.text == "🏠 Asosiy menyu")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Asosiy menyu", reply_markup=main_menu(message.from_user.id))

# ==================== CATCH ALL ====================
@dp.message(F.text)
async def catch_all(message: types.Message):
    await message.answer("❓ Tushunarsiz buyruq. Iltimos, pastdagi menyudan foydalaning 👇", reply_markup=main_menu(message.from_user.id))

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