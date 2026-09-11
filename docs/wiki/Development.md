# Development

## Project map

```
main.py                  # ALL bot handlers, keyboards, premium & admin flows
loader.py                # Bot + Dispatcher + Database singletons
data/config.py           # .env parsing (BOT_TOKEN, PRIMARY_ADMIN, ADMINS, CHANNELS)
utils/api/crypto.py      # price engine: median, resolver, fiat rates, caches
utils/scheduler.py       # background alert loop (20s tick)
utils/db_api/sqlite.py   # thin sqlite3 wrapper + migrations
tests/                   # pytest suite (27 tests)
.github/workflows/       # CI: pytest on push/PR
Dockerfile, docker-compose.yml, Procfile, deploy/crypto-bot.service
```

## Key design points

- **Fully async I/O.** All HTTP goes through one shared `aiohttp` session (`utils/api/crypto.py`). Never use `requests` here — it blocks the event loop for every user.
- **Scheduler tick (every 20s):** collect due users → fetch each *distinct* coin **once** → process users concurrently (`Semaphore(5)` + `gather`) → compare against `CryptoPreferences.last_price` → send only on ≥ 0.01% moves.
- **Bot + scheduler run together** via `asyncio.gather(dp.start_polling(bot), start_scheduler())` in `main.py`.
- **FSM states** (`aiogram`): `Register.phone`, `EditProfile.name/interval`, `PremiumOrder.waiting_screenshot`, `CoinSearch.waiting_for_symbol`. Memory storage — states reset on restart (by design).
- **Only `/start` is a command.** Everything else is keyboard text or `callback_data` (`notify_*`, `remove_*`, `plan_*`, `accept_*`, `reject_*`, `user_*`, `admin_users_*`, …).

## Tests & CI

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

Covers `format_price` (all currencies + edges), `calculate_price_change`, the price cache (mocked sources) and the CoinGecko resolver (mocked HTTP). CI (`.github/workflows/tests.yml`) runs the suite on Python 3.11 for every push/PR.

## Contributing

1. Fork + branch (`feature/my-feature`).
2. One focused commit per change, conventional messages (`fix:`, `feat:`, `perf:`, `docs:`…).
3. `python -m py_compile` + `pytest` green before pushing; open a PR with a short description.
