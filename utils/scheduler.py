"""
Avto-xabardorlik tizimi - FAQAT narx o'zgarganda yuboradi
"""
import asyncio
import logging
from datetime import datetime, timedelta
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
            # Kuzatuvda coin bor foydalanuvchilarni olish
            users = db.execute(
                "SELECT id, interval_min FROM Users WHERE id IN (SELECT DISTINCT user_id FROM CryptoPreferences)",
                fetchall=True
            )
            
            if not users:
                await asyncio.sleep(10)
                continue
            
            current_time = datetime.now()

            # 1-pass: intervali kelgan userlar va ularning coinlarini yig'amiz.
            # last_price DB'dan o'qiladi (restart'dan omon qoladi).
            due_users = []  # list of (user_id, interval_sec, coin_list, last_map)
            for user in users:
                user_id = user[0]
                interval_sec = user[1]

                # Keyingi tekshirish vaqtini sozlash
                if user_id not in user_next_send:
                    user_next_send[user_id] = current_time

                # Vaqt yetib kelganmi?
                if current_time < user_next_send[user_id]:
                    continue

                try:
                    # Coinlar + oxirgi ma'lum narxlarni olish
                    rows = db.execute(
                        "SELECT coin_symbol, last_price FROM CryptoPreferences WHERE user_id=?",
                        (user_id,),
                        fetchall=True
                    )

                    if not rows:
                        continue

                    coin_list = [r[0] for r in rows]
                    last_map = {r[0]: r[1] for r in rows if r[1]}
                    due_users.append((user_id, interval_sec, coin_list, last_map))
                except Exception as e:
                    logger.error(f"Error loading watchlist for user {user_id}: {e}")
                    user_next_send[user_id] = current_time + timedelta(minutes=5)

            if not due_users:
                continue

            # 2-pass: BARCHA due userlardagi DISTINCT coinlarni BITTA call'da olamiz.
            # Har bir coin tashqi API'lardan tick boshiga atigi 1 marta so'raladi
            # (crypto.py dagi per-source cache ikkinchi himoya qatlami).
            distinct_coins = list(dict.fromkeys(c for _, _, cl in due_users for c in cl))
            try:
                fetched = await get_real_prices(distinct_coins)
            except Exception as e:
                logger.error(f"Scheduler batch price fetch error: {e}")
                continue
            price_by_coin = dict(zip(distinct_coins, fetched))

            # 3-pass: userlar parallel qayta ishlanadi (Semaphore + gather).
            # Bitta userga xabar yuborish (network I/O) boshqalarni bloklamaydi.
            semaphore = asyncio.Semaphore(USER_CONCURRENCY)

            async def _process_user(user_id, interval_sec, coin_list, last_map):
                async with semaphore:
                    try:
                        # O'zgarishlarni tekshirish
                        changes_detected = []
                        message_lines = []
                        checked_at = current_time.strftime("%Y-%m-%d %H:%M:%S")

                        for coin in coin_list:
                            coin_data = price_by_coin.get(coin)
                            if not coin_data:
                                continue

                            new_price = coin_data['usd']
                            old_price = last_map.get(coin)

                            # Narx o'zgarishini hisoblash (minimal 0.01% o'zgarish)
                            if old_price:
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

                            # Oxirgi narxni DB'ga saqlash (restart'dan omon qoladi)
                            try:
                                db.execute(
                                    "UPDATE CryptoPreferences SET last_price=?, last_checked_at=? WHERE user_id=? AND coin_symbol=?",
                                    (new_price, checked_at, user_id, coin),
                                    commit=True,
                                )
                            except Exception as e:
                                logger.error(f"Error saving last_price for user {user_id}, coin {coin}: {e}")

                        # Agar o'zgarish bo'lsa - xabar yuborish
                        if changes_detected:
                            message_text = "📊 <b>Narx o'zgarishlari</b>\n\n"

                            for line in message_lines:
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
                                message_text += title + "\n"
                                message_text += f"   💵 {usd_str}\n"

                                if line['change'] is not None:
                                    message_text += f"   📊 {line['sign']}{line['change']:.2f}%\n"

                                message_text += f"   🇺🇿 {uzs_str}\n"
                                message_text += f"   🇷🇺 {rub_str}\n\n"

                            message_text += f"🕒 <i>Keyingi tekshirish: {interval_sec}s</i>"

                            await bot.send_message(user_id, message_text, parse_mode="HTML")
                            logger.info(f"✅ Sent {len(changes_detected)} price changes to user {user_id}")
                        else:
                            # O'zgarish yo'q - silent log
                            logger.debug(f"No changes for user {user_id}")

                        # Keyingi tekshirish vaqti
                        user_next_send[user_id] = current_time + timedelta(seconds=interval_sec)

                    except Exception as e:
                        logger.error(f"Error for user {user_id}: {e}")
                        user_next_send[user_id] = current_time + timedelta(minutes=5)

            await asyncio.gather(
                *(_process_user(u, iv, cl, lm) for u, iv, cl, lm in due_users)
            )
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        
        # Har 10 soniyada tekshirish (jonli narxlar uchun)
        await asyncio.sleep(10)


async def start_scheduler():
    """Scheduler'ni ishga tushirish"""
    logger.info("🚀 Smart price notification system started!")
    logger.info("📊 Will notify ONLY when prices change (≥0.01%)")
    await send_price_updates()