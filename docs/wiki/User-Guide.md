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
| 👤 Profile | Profile and settings |
| 🆘 Yordam | Help + admin contact (@hamroqulovv) |
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
- Everything is free — unlimited lookups for everyone.

## 3. Auto-notifications (🔔)

The **🔔 Avto-xabardorlik** screen shows your alert interval (e.g. `10s`), how many coins you watch, an **❌ per-coin remove** button and **🕒 Intervalni o'zgartirish**.

How alerts work:

- The bot re-checks your coins on your interval (minimum **10 seconds**).
- You get a message **only when a price changed ≥ 0.01%** since the last check — no spam when the market is flat.
- Each alert shows the new price in all three currencies plus the change percent (📈/📉).
- You can change the interval anytime (minimum **10 seconds**).

## 4. Profile (👤)

Shows name, phone, username, ID, interval and total lookup count. From here you can:

- **📝 Ismni tahrirlash** — change display name (🏠 Asosiy menyu cancels).
- **🕒 Intervalni tahrirlash** — set a new alert interval in seconds (min 10s).

Anything unclear? Check the [FAQ](FAQ.md).
