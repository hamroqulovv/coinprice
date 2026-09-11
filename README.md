# 🪙 CoinPrice Bot

<p align="center">
  <strong>Live crypto prices in USD / RUB / UZS, right inside Telegram.</strong><br>
  Watchlist alerts · Premium subscriptions · Admin panel
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/aiogram-3.4.1-green" alt="aiogram 3.4.1">
  <img src="https://img.shields.io/badge/license-GPL--3.0-orange" alt="GPL-3.0">
  <img src="https://img.shields.io/badge/docker-ready-blue" alt="Docker ready">
</p>

---

## 📖 Table of Contents
- [✨ Features](#-features)
- [💱 How prices work](#-how-prices-work)
- [🚀 Quick start](#-quick-start)
- [⚙️ Configuration](#️-configuration)
- [🐳 Docker](#-docker)
- [🧪 Tests](#-tests)
- [🗄️ Database](#️-database)
- [🔐 Security](#-security)
- [📄 License](#-license)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Any coin/token** | Look up thousands of coins — from BTC to the newest memecoins |
| 💱 **3 currencies** | Every price shown in USD, RUB and UZS |
| 🔔 **Smart alerts** | Subscribe to coins and get notified only when a price moves ≥ 0.01% |
| 📝 **Profiles** | Phone-number onboarding, editable name and alert interval |
| 💎 **Premium** | 5 free lookups/day — unlimited with premium (manual payment + admin approval) |
| 🛠️ **Admin panel** | Paginated user list, per-user details, give/remove premium |

---

## 💱 How prices work

1. **Multiple sources, one honest price.** Each coin is fetched in parallel from **Binance → Bybit → Coinbase → CoinGecko → DexScreener** (+ CoinMarketCap if you add a key). The **median** wins and outliers are dropped automatically — so one glitching exchange can't show you a wrong price.
2. **Unknown tickers resolve themselves.** Popular coins use a built-in fast path; anything else is resolved live via CoinGecko search (exact symbol match, highest market-cap rank wins) and cached.
3. **Real fiat rates.** UZS comes from Uzbekistan's Central Bank, RUB from Russia's Central Bank (each with a backup source, refreshed every 10 minutes).
4. **Not found?** The bot suggests similar symbols — just check the exact ticker spelling.

> ⚠️ CoinGecko's free search API is rate-limited: a burst of many *brand-new* coins in a row may be throttled (the bot retries once, then skips that source for the moment). Repeats are served from cache.

---

## 🚀 Quick start

```bash
git clone https://github.com/hamroqulovv/coinprice.git
cd coinprice

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # fill in your values (see below)
python main.py
```

You should see `🤖 Bot started!` in the logs — open your bot in Telegram and press **Start**.

---

## ⚙️ Configuration

All settings live in `.env`:

| Variable | Required | What it is |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `PRIMARY_ADMIN` | ✅ | Your Telegram numeric ID (owner of the admin panel) |
| `ADMINS` | ✅ | Extra admin IDs, comma-separated |
| `CHANNELS` | ⬜ | Optional channel list |
| `COINBASE_BASE_URL` | ⬜ | Override, default `https://api.coinbase.com/v2/prices` |
| `BINANCE_URL` | ⬜ | Override, default `https://api.binance.com/api/v3/ticker/price` |
| `COINGECKO_URL` | ⬜ | Override, default `https://api.coingecko.com/api/v3/simple/price` |
| `UZS_RATE_URL` | ⬜ | Override, default CBU JSON endpoint |
| `RUB_RATE_URL` | ⬜ | Override, default CBR JSON endpoint |
| `COINMARKETCAP_API_KEY` / `COINMARKETCAP_URL` | ⬜ | Adds CoinMarketCap as an extra price source |

⬜ = optional, has a working built-in default.

---

## 🐳 Docker

```bash
docker compose up -d --build
docker compose logs -f
```

`main.db` is persisted through a host volume (see `docker-compose.yml`).
Running on a plain VM instead? Use the systemd unit in `deploy/crypto-bot.service`.
Step-by-step guides: [`DEPLOY.md`](DEPLOY.md) · [`DEPLOY_UZ.md`](DEPLOY_UZ.md 🇺🇿)

---

## 🧪 Tests

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

Tests live in `tests/` and run automatically on every push/PR via [`.github/workflows/tests.yml`](.github/workflows/tests.yml).

---

## 🗄️ Database

SQLite file `main.db`, created automatically on first start:

- **`Users`** — profile, premium status, daily usage counters
- **`CryptoPreferences`** — watchlist with `UNIQUE(user_id, coin_symbol)` and the last notified price (so restarts never re-spam old alerts)

---

## 🔐 Security

- Never commit `.env` or API keys — both are git-ignored.
- On ephemeral hosts (Heroku, Cloud Run) SQLite does not survive restarts — use an external database there.

---

## 📄 License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
