"""
Avto-xabardorlik tizimi - FAQAT narx o'zgarganda yuboradi
"""
import asyncio
import logging
from datetime import datetime, timedelta
from loader import bot, db
from utils.api.crypto import get_real_prices

logger = logging.getLogger(__name__)

# Har bir foydalanuvchi uchun oxirgi narxlar
user_last_prices = {}
user_next_send = {}


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
                await asyncio.sleep(20)
                continue
            
            current_time = datetime.now()
            
            for user in users:
                user_id = user[0]
                interval_sec = user[1]
                
                # Keyingi tekshirish vaqtini sozlash
                if user_id not in user_next_send:
                    user_next_send[user_id] = current_time
                
                # Vaqt yetib kelganmi?
                if current_time >= user_next_send[user_id]:
                    try:
                        # Coinlarni olish
                        coins = db.execute(
                            "SELECT coin_symbol FROM CryptoPreferences WHERE user_id=?",
                            (user_id,),
                            fetchall=True
                        )
                        
                        if not coins:
                            continue
                        
                        coin_list = [c[0] for c in coins]
                        
                        # Yangi narxlarni olish
                        new_prices = get_real_prices(coin_list)
                        
                        # Foydalanuvchining oxirgi narxlarini olish
                        if user_id not in user_last_prices:
                            user_last_prices[user_id] = {}
                        
                        # O'zgarishlarni tekshirish
                        changes_detected = []
                        message_lines = []
                        
                        for i, coin in enumerate(coin_list):
                            if not new_prices[i]:
                                continue
                            
                            new_price = new_prices[i]['usd']
                            old_price = user_last_prices[user_id].get(coin)
                            
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
                                        'price': new_prices[i],
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
                                    'price': new_prices[i],
                                    'change': None,
                                    'diff': None,
                                    'sign': ""
                                })
                            
                            # Oxirgi narxni saqlash
                            user_last_prices[user_id][coin] = new_price
                        
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
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        
        # Har 20 soniyada tekshirish
        await asyncio.sleep(20)


async def start_scheduler():
    """Scheduler'ni ishga tushirish"""
    logger.info("🚀 Smart price notification system started!")
    logger.info("📊 Will notify ONLY when prices change (≥0.01%)")
    await send_price_updates()