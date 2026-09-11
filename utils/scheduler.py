"""
Avto-xabardorlik tizimi - FAQAT narx o'zgarganda yuboradi
"""
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from loader import bot, db
from utils.api.crypto import get_real_prices

logger = logging.getLogger(__name__)

# Oxirgi narxlar CryptoPreferences.last_price ustunida saqlanadi (DB),
# shuning uchun restart'da "first time" spam-xabarlar yuborilmaydi.
# user_next_send ataylab memory'da: restart'da yo'qolsa ham faqat keyingi
# tekshirish vaqti qayta hisoblanadi, noto'g'ri xabar yuborilmaydi.
user_next_send = {}

# Bir vaqtda nechta userga xabar yuborish (Telegram rate-limit himoyasi)
USER_CONCURRENCY = 5

# Telegram bitta xabar limiti (4096) dan xavfsiz kichik chunk o'lchami
MAX_MESSAGE_LEN = 3500
# Doimiy yuborib bo'lmaydigan userlar (bloklagan/o'chirilgan) uchun backoff
DEAD_USER_BACKOFF = timedelta(hours=6)


def _format_coin_block(line):
    """Bitta coin uchun xabar bloki (matn)."""
    p = line['price']

    # main.py format_price() bilan bir xil mantik -
    # display consistency uchun (accuracy yo'qolmasligi uchun)
    if p['usd'] >= 1:
        usd_str = f"${p['usd']:,.2f}"
    elif p['usd'] >= 0.01:
        usd_str = f"${p['usd']:,.4f}"
    elif p['usd'] >= 0.0001:
        usd_str = f"${p['usd']:,.6f}"
    else:
        usd_str = f"${p['usd']:.8f}"

    if p['rub'] >= 1:
        rub_str = f"{p['rub']:,.2f} ₽"
    elif p['rub'] >= 0.01:
        rub_str = f"{p['rub']:,.4f} ₽"
    else:
        rub_str = f"{p['rub']:.6f} ₽"

    if p['uzs'] >= 1000:
        uzs_str = f"{int(round(p['uzs'])):,} so'm"
    elif p['uzs'] >= 1:
        uzs_str = f"{p['uzs']:,.2f} so'm"
    else:
        uzs_str = f"{p['uzs']:.4f} so'm"

    nm = p.get('name')
    title = f"{line['emoji']} <b>{line['coin']}</b>" + (f" ({nm})" if nm and nm.upper() != line['coin'] else "")
    block = title + "\n"
    block += f"   💵 {usd_str}\n"

    if line['change'] is not None:
        block += f"   📊 {line['sign']}{line['change']:.2f}%\n"

    block += f"   🇺🇿 {uzs_str}\n"
    block += f"   🇷🇺 {rub_str}\n\n"
    return block


def _split_alerts(message_lines, interval_sec):
    """4096 limitdan oshmasligi uchun xabarlarni chunk'larga bo'lish."""
    header = "📊 <b>Narx o'zgarishlari</b>\n\n"
    footer = f"🕒 <i>Keyingi tekshirish: {interval_sec}s</i>"
    chunks, cur = [], header
    for line in message_lines:
        block = _format_coin_block(line)
        if len(cur) + len(block) > MAX_MESSAGE_LEN and len(cur) > len(header):
            chunks.append(cur)
            cur = header
        cur += block
    cur += footer
    chunks.append(cur)
    return chunks

# Interval pastki chegarasi (sekund). main.MIN_INTERVAL bilan sinxron ushlang:
# DB'dagi NULL/eskiqiymatlar shu yergacha ko'tariladi, spam/hot-loop bo'lmaydi.
SCHED_MIN_INTERVAL = 10


def calculate_price_change(old_price, new_price):
    """
    Narx o'zgarishini foizda hisoblash
    """
    if not old_price or old_price == 0:
        return 100.0
    
    change = ((new_price - old_price) / old_price) * 100
    return abs(change)


async def send_price_updates():
    """
    Narxlarni doimiy tekshirish va o'zgarishda xabar yuborish
    """
    while True:
        try:
            # Kuzatuvlar BITTA query'da olinadi (har user uchun alohida
            # SELECT o'rniga - N+1 muammosi bo'lmasligi uchun).
            try:
                pref_rows = db.execute(
                    "SELECT user_id, coin_symbol, last_price FROM CryptoPreferences",
                    fetchall=True,
                ) or []
            except Exception as e:
                logger.error(f"Scheduler watchlist load error: {e}")
                await asyncio.sleep(10)
                continue
            by_user = {}
            for uid, sym, lp in pref_rows:
                by_user.setdefault(uid, []).append((sym, lp))

            # GC: kuzatuvi qolmagan userlar memory'dan tozalanadi.
            for uid in list(user_next_send):
                if uid not in by_user:
                    user_next_send.pop(uid, None)

            try:
                users = db.execute(
                    "SELECT id, interval_min FROM Users WHERE id IN (SELECT DISTINCT user_id FROM CryptoPreferences)",
                    fetchall=True,
                ) or []
            except Exception as e:
                logger.error(f"Scheduler users load error: {e}")
                await asyncio.sleep(10)
                continue

            if not users:
                await asyncio.sleep(10)
                continue

            current_time = datetime.now()

            # 1-pass: intervali kelgan userlar va ularning coinlarini yig'amiz.
            # last_price DB'dan o'qiladi (restart'dan omon qoladi).
            due_users = []  # list of (user_id, interval_sec, coin_list, last_map)
            for user in users:
                user_id = user[0]
                try:
                    interval_sec = int(user[1]) if user[1] is not None else SCHED_MIN_INTERVAL
                except (TypeError, ValueError):
                    logger.warning(f"Bad interval_min for user {user_id}: {user[1]!r}, using {SCHED_MIN_INTERVAL}s")
                    interval_sec = SCHED_MIN_INTERVAL
                if interval_sec < SCHED_MIN_INTERVAL:
                    logger.warning(f"Too small interval_min for user {user_id}: {interval_sec}s, floored to {SCHED_MIN_INTERVAL}s")
                    interval_sec = SCHED_MIN_INTERVAL

                # Keyingi tekshirish vaqtini sozlash
                if user_id not in user_next_send:
                    user_next_send[user_id] = current_time

                # Vaqt yetib kelganmi?
                if current_time < user_next_send[user_id]:
                    continue

                watched = by_user.get(user_id)
                if not watched:
                    user_next_send[user_id] = current_time + timedelta(minutes=5)
                    continue

                coin_list = [sym for sym, _ in watched]
                last_map = {sym: lp for sym, lp in watched if lp is not None}
                due_users.append((user_id, interval_sec, coin_list, last_map))

            if not due_users:
                await asyncio.sleep(10)
                continue

            # 2-pass: BARCHA due userlardagi DISTINCT coinlarni BITTA call'da olamiz.
            # Har bir coin tashqi API'lardan tick boshiga atigi 1 marta so'raladi
            # (crypto.py dagi per-source cache ikkinchi himoya qatlami).
            distinct_coins = list(dict.fromkeys(c for _, _, cl, _ in due_users for c in cl))
            try:
                fetched = await get_real_prices(distinct_coins)
            except Exception as e:
                logger.error(f"Scheduler batch price fetch error: {e}")
                await asyncio.sleep(10)
                continue
            price_by_coin = dict(zip(distinct_coins, fetched))

            # 3-pass: userlar parallel qayta ishlanadi (Semaphore + gather).
            # Bitta userga xabar yuborish (network I/O) boshqalarni bloklamaydi.
            semaphore = asyncio.Semaphore(USER_CONCURRENCY)

            async def _process_user(user_id, interval_sec, coin_list, last_map):
                try:
                    async with semaphore:
                        now = datetime.now()
                        checked_at = now.strftime("%Y-%m-%d %H:%M:%S")

                        # O'zgarishlarni tekshirish (har bir coin alohida -
                        # bitta yaroqsiz coin butun user'ni to'xtatmaydi)
                        changes_detected = []
                        message_lines = []
                        pending_saves = []

                        for coin in coin_list:
                            try:
                                coin_data = price_by_coin.get(coin)
                                if not coin_data:
                                    continue

                                new_price = coin_data.get('usd')
                                if not isinstance(new_price, (int, float)) or not new_price > 0:
                                    continue
                                old_price = last_map.get(coin)

                                # Narx o'zgarishini hisoblash (minimal 0.01% o'zgarish)
                                if old_price is not None:
                                    change_percent = calculate_price_change(old_price, new_price)

                                    # 0.01% dan katta o'zgarish bo'lsa
                                    if change_percent >= 0.01:
                                        price_diff = new_price - old_price
                                        emoji = "📈" if price_diff > 0 else "📉"
                                        sign = "+" if price_diff > 0 else ""

                                        changes_detected.append(coin)
                                        message_lines.append({
                                            'coin': coin,
                                            'emoji': emoji,
                                            'price': coin_data,
                                            'change': change_percent,
                                            'diff': price_diff,
                                            'sign': sign
                                        })
                                else:
                                    # Birinchi marta - har doim yuborish
                                    changes_detected.append(coin)
                                    message_lines.append({
                                        'coin': coin,
                                        'emoji': "💰",
                                        'price': coin_data,
                                        'change': None,
                                        'diff': None,
                                        'sign': ""
                                    })
                            except Exception as e:
                                logger.error(f"Skipping coin {coin} for user {user_id}: {e}")
                                continue

                            pending_saves.append((new_price, checked_at, user_id, coin))

                        # Oxirgi narxlar BITTA transaction'da saqlanadi
                        # (restart'dan omon qoladi, lock contention kamayadi)
                        if pending_saves:
                            try:
                                db.execute_many(
                                    "UPDATE CryptoPreferences SET last_price=?, last_checked_at=? WHERE user_id=? AND coin_symbol=?",
                                    pending_saves,
                                    commit=True,
                                )
                            except Exception as e:
                                logger.error(f"Error saving last_prices for user {user_id}: {e}")

                        # Agar o'zgarish bo'lsa - xabar yuborish (chunk'larda)
                        if changes_detected:
                            for chunk in _split_alerts(message_lines, interval_sec):
                                try:
                                    await bot.send_message(user_id, chunk, parse_mode="HTML")
                                except TelegramRetryAfter as e:
                                    logger.warning(f"FloodWait for user {user_id}, sleeping {e.retry_after}s")
                                    await asyncio.sleep(e.retry_after)
                                    await bot.send_message(user_id, chunk, parse_mode="HTML")
                            logger.info(f"✅ Sent {len(changes_detected)} price changes to user {user_id}")
                        else:
                            # O'zgarish yo'q - silent log
                            logger.debug(f"No changes for user {user_id}")

                        # Keyingi tekshirish vaqti (fresh timestamp asosida)
                        user_next_send[user_id] = datetime.now() + timedelta(seconds=interval_sec)

                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    # Bloklagan/o'chirilgan user: uzoq backoff, log spam yo'q
                    logger.warning(f"Unreachable user {user_id}, backing off: {e}")
                    user_next_send[user_id] = datetime.now() + DEAD_USER_BACKOFF
                except TelegramNetworkError as e:
                    logger.error(f"Network error for user {user_id}: {e}")
                    user_next_send[user_id] = datetime.now() + timedelta(minutes=5)
                except Exception as e:
                    logger.error(f"Error for user {user_id}: {e}")
                    user_next_send[user_id] = datetime.now() + timedelta(minutes=5)

            results = await asyncio.gather(
                *(_process_user(u, iv, cl, lm) for u, iv, cl, lm in due_users),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, BaseException) and not isinstance(res, asyncio.CancelledError):
                    logger.error(f"Scheduler user task failed: {res!r}")
                elif isinstance(res, asyncio.CancelledError):
                    raise res
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        
        # Har 10 soniyada tekshirish (jonli narxlar uchun)
        await asyncio.sleep(10)


async def start_scheduler():
    """Scheduler'ni ishga tushirish"""
    logger.info("🚀 Smart price notification system started!")
    logger.info("📊 Will notify ONLY when prices change (≥0.01%)")
    await send_price_updates()