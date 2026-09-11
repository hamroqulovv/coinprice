# CoinPrice Bot

Telegram bot that shows crypto prices in **USD / RUB / UZS** and sends automatic price-change alerts. Built with Python + aiogram 3, SQLite storage, Docker-ready.

## Features
- **Any coin/token lookup** — prices aggregated as the median of Binance, Bybit, Coinbase, CoinGecko (+ CoinMarketCap if key set), with CoinGecko search and DexScreener fallback for long-tail tokens. Outliers are filtered automatically.
- **Three currencies** — USD market price × official fiat rates (UZS via CBU, RUB via CBR, each with fallback source and 10-min cache).
- **Watchlist + auto-notify** — users subscribe to coins; the scheduler checks every 20s and messages only when a price moves ≥0.01% (per-user interval, min 40s).
- **Registration** — phone-number onboarding, profile with editable name/interval.
- **Free limit** — 5 lookups/day for free users; premium removes the limit.
- **Premium** — manual card payment, screenshot sent to admin for approval.
- **Admin panel** — paginated user list, per-user details, give/remove premium.

## Price sources
- Lookup order per coin: **Binance → Bybit → Coinbase → CoinGecko → DexScreener** (+ CoinMarketCap if key set); the median of all successful sources wins, outliers are dropped.
- Well-known tickers use a hardcoded CoinGecko-id fast path (no extra call). Unknown tickers are resolved dynamically via CoinGecko `/search` (exact symbol match, lowest `market_cap_rank` wins; result cached permanently, confirmed misses cached 1 hour).
- A coin can still be "not found" if it is listed nowhere supported or its ticker is ambiguous/misspelled — the bot suggests similar symbols in that case.
- CoinGecko's free `/search` is rate-limited; the cache absorbs repeats, but a burst of many *distinct* new coins in a row can be throttled (the bot retries once, then skips that source for the tick).

## Tech
- Python 3.11+, aiogram 3.4.1, aiohttp (async HTTP), SQLite (`main.db`)
- Tests: pytest (`tests/`), CI on push/PR (`.github/workflows/tests.yml`)

## Local run
```bash
git clone <repo-url>
cd coinprice
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # fill in values, see below
python main.py
```

## Configuration (`.env`)
| Var | Required | Description |
|---|---|---|
| `BOT_TOKEN` | yes | Telegram bot token |
| `PRIMARY_ADMIN` | yes | Main admin Telegram ID (single int) |
| `ADMINS` | yes | Extra admin IDs, comma-separated |
| `CHANNELS` | no | Optional channel list |
| `COINBASE_BASE_URL` | no* | Default `https://api.coinbase.com/v2/prices` |
| `BINANCE_URL` | no* | Default `https://api.binance.com/api/v3/ticker/price` |
| `COINGECKO_URL` | no* | Default `https://api.coingecko.com/api/v3/simple/price` |
| `UZS_RATE_URL` | no* | Default CBU JSON endpoint |
| `RUB_RATE_URL` | no* | Default CBR JSON endpoint |
| `COINMARKETCAP_API_KEY` / `COINMARKETCAP_URL` | no | Enables CoinMarketCap as an extra source |

\* Has a built-in default; set explicitly to override.

## Docker
```bash
docker compose up -d --build
docker compose logs -f
```
`main.db` is persisted via a host volume (see `docker-compose.yml`). For VM/systemd deploys see `deploy/crypto-bot.service`; full guides in `DEPLOY.md` / `DEPLOY_UZ.md`.

## Tests
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

## Database
SQLite `main.db` (auto-created on start via `db.create_tables()`): `Users` (profile, premium, limits) and `CryptoPreferences` (`UNIQUE(user_id, coin_symbol)`, last notified price for the scheduler).

## Security
Never commit `.env` or API keys. On ephemeral hosts (Heroku/Cloud Run) SQLite is lost — use an external DB.

## License
GNU General Public License v3.0 — see `LICENSE`.
