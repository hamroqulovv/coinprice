# Database

SQLite file `main.db` in the project root, created and migrated automatically on every start (`db.create_tables()` in `main.py`). Raw `sqlite3`, no ORM.

## Tables

**`Users`** — one row per Telegram user:

| Column | Meaning |
|---|---|
| `id` | Telegram user ID (primary key) |
| `phone`, `username`, `full_name` | Contact details (name is editable) |
| `interval_min` | Alert interval in **seconds** (default 40) |
| `view_count` | Lifetime lookups |

**`CryptoPreferences`** — watchlist, one row per (user, coin):

| Column | Meaning |
|---|---|
| `user_id`, `coin_symbol` | Who watches what — `UNIQUE(user_id, coin_symbol)` blocks duplicates at the DB level |
| `last_price` | Last notified USD price — survives restarts, so users never get a bogus "first time" alert after a deploy |
| `last_checked_at` | When it was last updated |

## Migrations

All migrations are `IF NOT EXISTS` / `ADD COLUMN`-in-`try/except` style: safe to run on every boot, on fresh and legacy DBs alike. Duplicate watchlist rows from older versions are deduplicated automatically.

> Legacy columns from the removed premium system (`is_premium`, `daily_views`, …) may still exist in old databases — they are simply unused.

## Reset / inspect

```bash
sqlite3 main.db "SELECT COUNT(*) FROM Users;"
sqlite3 main.db "SELECT * FROM CryptoPreferences LIMIT 5;"
```
