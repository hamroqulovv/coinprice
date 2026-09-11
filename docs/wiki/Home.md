# CoinPrice Bot Wiki 👋

**CoinPrice Bot** is a Telegram bot that shows live cryptocurrency prices in **USD 🇺🇸 / RUB 🇷🇺 / UZS 🇺🇿** and sends automatic alerts when prices move. Built with Python, aiogram 3 and SQLite.

> 🗣️ The bot speaks **Uzbek**. This wiki is in English for developers and operators.

## Start here

| Page | What you'll learn |
|---|---|
| [Getting Started](Getting-Started.md) | Install and run the bot in 5 minutes |
| [User Guide](User-Guide.md) | Every button and flow, as your users see them |
| [How Prices Work](How-Prices-Work.md) | Sources, median logic, fiat rates, caches |
| [Configuration](Configuration.md) | Every `.env` variable explained |
| [Admin Guide](Admin-Guide.md) | Admin panel and user list |
| [Deployment](Deployment.md) | Docker, systemd, backups, Heroku notes |
| [Database](Database.md) | Tables, migrations, constraints |
| [Development](Development.md) | Code map, async design, tests & CI |
| [FAQ](FAQ.md) | Common questions and fixes |

## 30-second summary

1. User sends `/start`, shares their phone number → registered.
2. User taps **📊 Narxlarni ko'rish**, types `BTC` → gets USD/RUB/UZS prices.
3. User taps **🔔 Kuzatuvga qo'shish** → coin added to their watchlist.
4. Every 20 seconds the scheduler re-checks prices and messages the user **only if something moved ≥ 0.01%**.
5. Everything is free — unlimited lookups, alerts and intervals for everyone.
