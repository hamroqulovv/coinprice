import asyncio
import html
import logging
import sqlite3
from aiogram import types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import bot, dp, db
from utils.api.crypto import get_real_prices, suggest_coins
from utils.format import format_price
import re

COIN_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{0,19}$")

# Menyu tugmalari: CoinSearch state'da bosilsa search o'rniga
# tegishli handler ishlashi uchun search_coin'dan exclude qilinadi.
MENU_BUTTONS = frozenset({
    "📊 Narxlarni ko'rish",
    "🔔 Avto-xabardorlik",
    "👤 Profile",
    "🆘 Yordam",
    "👨‍💼 USERS Admin Panel",
})

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from data.config import PRIMARY_ADMIN, ADMINS
MIN_INTERVAL = 10

# ==================== STATES ====================
class Register(StatesGroup):
    phone = State()

class EditProfile(StatesGroup):
    name = State()
    interval = State()

class CoinSearch(StatesGroup):
    waiting_for_symbol = State()

# ==================== KEYBOARDS ====================
def main_menu(user_id):
    kb = [[KeyboardButton(text="🔔 Avto-xabardorlik"), KeyboardButton(text="👤 Profile")],
          [KeyboardButton(text="🆘 Yordam")]]
    if is_admin(user_id):
        kb.append([KeyboardButton(text="👨‍💼 USERS Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Asosiy menyu")]], resize_keyboard=True)

def is_registered(user_id):
    """Return True if the user exists in the Users table."""
    return bool(db.execute("SELECT 1 FROM Users WHERE id=?", (user_id,), fetchone=True))


def is_admin(user_id):
    """PRIMARY_ADMIN + ADMINS ro'yxatidagi qo'shimcha adminlar."""
    try:
        return user_id == PRIMARY_ADMIN or user_id in (ADMINS or [])
    except Exception:
        return user_id == PRIMARY_ADMIN

# ==================== START & REGISTRATION ====================
async def _enter_search(message: types.Message, state: FSMContext):
    """Default rejim: coin qidiruv (start'dan keyin darhol narx ko'rish)."""
    await state.set_state(CoinSearch.waiting_for_symbol)
    await message.answer(
        "💰 <b>Coin qidiruv</b>\n\nIstalgan coin/token belgisini kiriting 👇\n"
        "<i>Masalan: BTC, ETH, SOL, PEPE, WIF, 1INCH, POPCAT...</i>",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id),
    )

@dp.message(Command("start"))
async def start_bot(message: types.Message, state: FSMContext):
    await state.clear()
    user = db.execute("SELECT full_name FROM Users WHERE id=?", (message.from_user.id,), fetchone=True)

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
        await message.answer(f"👋 Xush kelibsiz, <b>{html.escape(user[0] or '', quote=False)}</b>!", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
        await _enter_search(message, state)

@dp.message(Register.phone, F.contact)
async def get_phone(message: types.Message, state: FSMContext):
    """Register the user immediately using the shared contact and Telegram full name."""
    # Begona kontaktni o'z nomidan yozib qo'yishdan himoya
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        return await message.answer("⚠️ Iltimos, o'z raqamingizni ulashing 👇")
    phone = message.contact.phone_number
    full_name = message.from_user.full_name or message.from_user.username or "N/A"
    username = message.from_user.username or "N/A"

    try:
        # INSERT OR IGNORE: kontaktni ikki marta bosish race'ida
        # ikkinchi urinish ham muvaffaqiyat hisoblanadi.
        db.execute(
            "INSERT OR IGNORE INTO Users (id, phone, username, full_name, interval_min, is_premium, view_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message.from_user.id, phone, username, full_name, MIN_INTERVAL, 0, 0),
            commit=True
        )
        await message.answer("✅ <b>Ro'yxatdan o'tdingiz!</b>", reply_markup=main_menu(message.from_user.id), parse_mode="HTML")
        logger.info(f"New user: {message.from_user.id}")
        await _enter_search(message, state)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await message.answer("❌ Xatolik! /start ni qayta yuboring.")
        await state.clear()


@dp.message(Register.phone)
async def get_phone_fallback(message: types.Message):
    """Kontakt o'rniga boshqa narsa yuborilsa - qayta so'rash (state saqlanadi)."""
    kb = [[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]]
    await message.answer(
        "📱 Iltimos, pastdagi tugma orqali raqamingizni ulashing 👇",
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


# ==================== COIN SEARCH ====================
@dp.message(F.text == "📊 Narxlarni ko'rish")
async def show_coins_search(message: types.Message, state: FSMContext):
    await state.clear()    # Ensure user is registered before allowing coin search
    if not is_registered(message.from_user.id):
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))
    db.execute("UPDATE Users SET view_count = view_count + 1 WHERE id=?", (message.from_user.id,), commit=True)
    await _enter_search(message, state)

@dp.message(CoinSearch.waiting_for_symbol, F.text, ~F.text.in_(MENU_BUTTONS))
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
                    lines.append(f"• <b>{html.escape(s['symbol'], quote=False)}</b> — {html.escape(s['name'], quote=False)}")
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
        safe_coin = html.escape(coin, quote=False)
        title = f"💰 <b>{safe_coin}</b>" + (f" <i>({html.escape(coin_name, quote=False)})</i>" if coin_name and coin_name.upper() != coin else "")

        text = f"{title}\n▬▬▬▬▬▬▬▬▬▬▬▬▬\n💵 <b>USD:</b> <code>{usd_str}</code>\n🇷🇺 <b>RUB:</b> <code>{rub_str}</code>\n🇺🇿 <b>UZS:</b> <code>{uzs_str}</code>"
        # Yagona manbali (ekzotik) coinlar uchun ogohlantirish
        src = (d.get('source') or '')
        if src and '+' not in src:
            text += f"\n\n🔎 Manba: {src} (kam likvid - narx taxminiy)"

        exists = db.execute("SELECT 1 FROM CryptoPreferences WHERE user_id=? AND coin_symbol=?", 
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

    coin = callback.data.split("_", 1)[1]
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
        try:
            await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
    except sqlite3.Error as e:
        logger.error(f"Watchlist DB error for user {callback.from_user.id}, coin {coin}: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)
    except Exception as e:
        logger.error(f"Watchlist unexpected error for user {callback.from_user.id}, coin {coin}: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)

@dp.callback_query(F.data.startswith("watching_"))
async def already_watching(callback: types.CallbackQuery):
    coin = callback.data.split("_", 1)[1]
    await callback.answer(f"✅ {coin} allaqachon kuzatuvda!", show_alert=True)

# ==================== AUTO-NOTIFY ====================
@dp.message(F.text == "🔔 Avto-xabardorlik")
async def auto_notify(message: types.Message):
    # Ensure the user is registered before showing auto-notify settings
    if not is_registered(message.from_user.id):
        return await message.answer("Iltimos /start bilan ro'yxatdan o'ting.", reply_markup=main_menu(message.from_user.id))

    coins = db.execute("SELECT coin_symbol FROM CryptoPreferences WHERE user_id=?",
                      (message.from_user.id,), fetchall=True)
    row = db.execute("SELECT interval_min FROM Users WHERE id=?",
                     (message.from_user.id,), fetchone=True)
    interval = (row[0] if row and row[0] else MIN_INTERVAL)
    
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

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup() if coins else None)

@dp.callback_query(F.data.startswith("remove_"))
async def remove_coin(callback: types.CallbackQuery):
    # Prevent unregistered users from removing coins
    if not is_registered(callback.from_user.id):
        await callback.answer("Iltimos /start bilan ro'yxatdan o'ting.", show_alert=True)
        return

    coin = callback.data.split("_", 1)[1]
    try:
        db.execute("DELETE FROM CryptoPreferences WHERE user_id=? AND coin_symbol=?",
                  (callback.from_user.id, coin), commit=True)
        await callback.answer(f"✅ {coin} o'chirildi!")
    except sqlite3.Error as e:
        logger.error(f"Watchlist delete error for user {callback.from_user.id}, coin {coin}: {e}")
        await callback.answer("❌ Xatolik", show_alert=True)
        return
    try:
        if callback.message:
            await callback.message.delete()
    except TelegramBadRequest:
        pass  # allaqachon o'chirilgan (ikki marta bosish)

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
        f"📝 Ism: <b>{html.escape(full_name or '', quote=False)}</b>\n"
        f"📞 Telefon: <code>{html.escape(phone or '', quote=False)}</code>\n"
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
    if not is_registered(callback.from_user.id):
        await callback.answer("Iltimos /start bilan ro'yxatdan o'ting.", show_alert=True)
        return
    if not callback.message:
        await callback.answer("❌ Xatolik", show_alert=True)
        return
    await callback.message.answer("📝 Yangi ismingizni kiriting:", reply_markup=back_keyboard())
    await state.set_state(EditProfile.name)
    await callback.answer()

@dp.message(EditProfile.name, F.text)
async def update_name(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(message.from_user.id))

    name = message.text.strip()[:64]
    if not name:
        return await message.answer("❌ Bo'sh ism bo'lmaydi!")

    db.execute("UPDATE Users SET full_name=? WHERE id=?", (name, message.from_user.id), commit=True)
    await message.answer("✅ Yangilandi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "edit_interval")
async def edit_interval(callback: types.CallbackQuery, state: FSMContext):
    if not is_registered(callback.from_user.id):
        await callback.answer("Iltimos /start bilan ro'yxatdan o'ting.", show_alert=True)
        return
    if not callback.message:
        await callback.answer("❌ Xatolik", show_alert=True)
        return
    await state.clear()
    await callback.message.answer(f"🕒 Yangi intervalni soniyada kiriting (min: {MIN_INTERVAL}s):", reply_markup=back_keyboard())
    await state.set_state(EditProfile.interval)
    await callback.answer()

@dp.message(EditProfile.interval, F.text)
async def update_interval(message: types.Message, state: FSMContext):
    if message.text == "🏠 Asosiy menyu":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(message.from_user.id))

    try:
        val = int(message.text.strip())
    except (ValueError, AttributeError):
        return await message.answer("❌ Faqat raqam kiriting!")

    if not MIN_INTERVAL <= val <= 86400:
        return await message.answer(f"⚠️ Interval {MIN_INTERVAL}s dan 86400s gacha bo'lishi kerak!")

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
        kb.button(text=f"👤 {(u[1] or '')[:32]} ({u[2]})", callback_data=f"user_{u[0]}")
    kb.adjust(1)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(text="◀️ Prev", callback_data=f"admin_users_{page - 1}"))
    if page < pages - 1:
        nav.append(types.InlineKeyboardButton(text="Next ▶️", callback_data=f"admin_users_{page + 1}"))
    if nav:
        kb.row(*nav)
    markup = kb.as_markup() if (users or nav) else None
    return markup, total, page, pages

@dp.message(F.text == "👨‍💼 USERS Admin Panel")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    markup, total, page, pages = _admin_page_keyboard(0)
    await message.answer(f"👥 Users: {total} (sahifa {page + 1}/{pages})", reply_markup=markup)

@dp.callback_query(F.data.startswith("admin_users_"))
async def admin_panel_page(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 0
    markup, total, page, pages = _admin_page_keyboard(page)
    try:
        await callback.message.edit_text(f"👥 Users: {total} (sahifa {page + 1}/{pages})", reply_markup=markup)
    except TelegramBadRequest as e:
        # Ikkita tez bosishda xabar o'zgarmagan bo'lishi mumkin
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()

@dp.callback_query(F.data.startswith("user_"))
async def manage_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    try:
        uid = int(callback.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Invalid callback data", show_alert=True)
        return
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
        f"👤 <b>{html.escape(full_name or '', quote=False)}</b>\n\n"
        f"📞 Telefon: <code>{html.escape(phone or '', quote=False)}</code>\n"
        f"💬 Username: @{username_display}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"🕒 Interval: {interval_min}s\n"
        f"👁 So'rovlar: {view_count}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Back", callback_data="back_admin")
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()

@dp.callback_query(F.data == "back_admin")
async def back_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    # Ro'yxatning birinchi sahifasiga qaytish (o'chirish o'rniga -
    # paginatsiya yo'qolmaydi, ikkinchi bosish crash qilmaydi)
    markup, total, page, pages = _admin_page_keyboard(0)
    try:
        await callback.message.edit_text(f"👥 Users: {total} (sahifa {page + 1}/{pages})", reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()

# ==================== SUPPORT ====================
@dp.message(F.text == "🆘 Yordam")
async def support(message: types.Message):
    text = (
        "🆘 <b>Yordam</b>\n\n"
        "Savol yoki muammo bo'lsa admin bilan bog'laning:\n"
        "👤 Admin: @hamroqulovv\n\n"
        "❓ <b>Ko'p so'raladiganlar:</b>\n"
        "• Narx topilmasa — ticker imlosini tekshiring\n"
        "• Bildirishnoma kelmasa — 🔔 Avto-xabardorlik bo'limini tekshiring\n"
        "• Bot ishlamasa — /start ni qayta yuboring"
    )
    if is_registered(message.from_user.id):
        await message.answer(text, parse_mode="HTML", reply_markup=main_menu(message.from_user.id))
    else:
        await message.answer(text, parse_mode="HTML")

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
    try:
        db.create_tables()
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise SystemExit(1)

    # Avto-xabardorlik schedulerni ishga tushirish
    from utils.scheduler import start_scheduler
    from utils.api.crypto import close_http_session

    # Ikkalasini parallel ishga tushirish
    async def run_bot():
        logger.info("🤖 Bot started!")
        await dp.start_polling(bot)

    async def run_scheduler():
        await start_scheduler()

    # Ikkalasini bir vaqtda ishga tushirish
    try:
        await asyncio.gather(
            run_bot(),
            run_scheduler()
        )
    finally:
        # Toza shutdown: session'lar ochiq qolmaydi
        try:
            await dp.storage.close()
        except Exception as e:
            logger.debug(f"Storage close: {e}")
        try:
            await bot.session.close()
        except Exception as e:
            logger.debug(f"Bot session close: {e}")
        try:
            await close_http_session()
        except Exception as e:
            logger.debug(f"HTTP session close: {e}")

if __name__ == "__main__":
    asyncio.run(main())