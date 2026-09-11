# User Guide

Everything a normal user can do. The bot has **no slash commands except `/start`** — everything happens through keyboard buttons.

## 1. Registration (`/start`)

1. Send `/start`.
2. New users see a **📱 Raqamni ulashish** button — tapping it shares their phone number (Telegram contact).
3. The bot registers them instantly using their Telegram name and shows the main menu.

Main menu buttons:

| Button | Opens |
|---|---|
| 📊 Narxlarni ko'rish | Price search |
| 🔔 Avto-xabardorlik | Watchlist & alert interval |
| 👤 Profile | Profile, settings, premium |
| 👨‍💼 USERS Admin Panel | Admin only (see [Admin Guide](Admin-Guide.md)) |

## 2. Checking a price (📊)

1. Tap **📊 Narxlarni ko'rish**.
2. Type any ticker: `BTC`, `ETH`, `PEPE`, `1INCH`, `POPCAT`… (letters and digits allowed).
3. The bot replies with the price in three currencies, e.g.:

```
💰 BTC
💵 USD: $77,821.34
🇷🇺 RUB: 6,564,292.29 ₽
🇺🇿 UZS: 917,005,425 so'm
[ 🔔 Kuzatuvga qo'shish ]
```

- Tapping **🔔 Kuzatuvga qo'shish** adds the coin to the watchlist (button becomes **✅ Kuzatuvda**).
- Unknown tickers get a "not found" message plus similar-symbol suggestions.
- 🆓 Free users: **5 lookups per day**, then the bot offers 💎 Premium.

## 3. Auto-notifications (🔔)

The **🔔 Avto-xabardorlik** screen shows your alert interval (e.g. `40s`), how many coins you watch, an **❌ per-coin remove** button and **🕒 Intervalni o'zgartirish**.

How alerts work:

- The bot re-checks your coins on your interval (minimum **40 seconds**).
- You get a message **only when a price changed ≥ 0.01%** since the last check — no spam when the market is flat.
- Each alert shows the new price in all three currencies plus the change percent (📈/📉).
- Changing the interval requires **Premium** (admins are exempt).

## 4. Profile (👤)

Shows name, phone, username, ID, subscription status, interval and total lookup count. From here you can:

- **📝 Ismni tahrirlash** — change display name (🏠 Asosiy menyu cancels).
- **🕒 Intervalni tahrirlash** — set a new alert interval in seconds (Premium only, min 40s).
- **💎 Premium** — open the subscription plans.

## 5. Premium (💎)

1. Pick a plan: 1 / 2 / 3 / 6 / 12 months.
2. Pay to the shown card number and **send a screenshot** of the receipt to the bot.
3. The screenshot (with your name, plan and timestamp) goes to the admin.
4. Once approved you get `🎉 Premium faol (N kun)!`; if rejected, the bot tells you and gives the admin's contact.

Anything unclear? Check the [FAQ](FAQ.md).
