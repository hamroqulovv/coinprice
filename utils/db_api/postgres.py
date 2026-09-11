"""PostgreSQL backend (Supabase) - same shape as utils/db_api/sqlite.py.

Used when DATABASE_URL is set (Render/Supabase deploy). Local dev without
DATABASE_URL keeps using SQLite, nothing changes there.

Notes:
- asyncpg + pool. Supabase pooler (PgBouncer, transaction mode) does NOT
  support prepared statements -> statement_cache_size=0 is required.
- Call sites keep writing SQLite-style `?` placeholders and
  `INSERT OR IGNORE`; both are translated to Postgres dialect here, so
  main.py / scheduler.py stay backend-agnostic.
- Rows are returned as plain tuples (like sqlite3), not asyncpg Records.
"""
import logging
import re

import asyncpg

logger = logging.getLogger(__name__)

_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.IGNORECASE)


def _translate(sql: str):
    """SQLite -> Postgres: `INSERT OR IGNORE` + `?` placeholders.

    Returns translated SQL. `ON CONFLICT DO NOTHING` needs no conflict
    target and works for both PRIMARY KEY and UNIQUE violations.
    """
    suffix = ""
    m = _OR_IGNORE.match(sql)
    if m:
        sql = "INSERT INTO " + sql[m.end():]
        suffix = " ON CONFLICT DO NOTHING"
    out = []
    idx = 0
    for ch in sql:
        if ch == "?":
            idx += 1
            out.append(f"${idx}")
        else:
            out.append(ch)
    return "".join(out) + suffix


class PostgresDatabase:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool = None

    async def connect(self):
        """Create the pool. Called once at bot startup (main)."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=5,
                command_timeout=30,
                # Supabase pooler (transaction mode) can't use prepared statements
                statement_cache_size=0,
            )

    async def close(self):
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def execute(self, sql: str, parameters: tuple = None, fetchone=False, fetchall=False, commit=False):
        # NOTE: asyncpg autocommits single statements; `commit` kept only
        # for signature parity with the SQLite backend.
        q, _ = _translate(sql), parameters
        params = tuple(parameters or ())
        async with self._pool.acquire() as conn:
            if fetchall:
                rows = await conn.fetch(q, *params)
                return [tuple(r) for r in rows]
            if fetchone:
                row = await conn.fetchrow(q, *params)
                return tuple(row) if row is not None else None
            await conn.execute(q, *params)
            return None

    async def execute_many(self, sql: str, seq_of_parameters, commit=True):
        rows = list(seq_of_parameters)
        if not rows:
            return None
        q, _ = _translate(sql), None
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for params in rows:
                    await conn.execute(q, *tuple(params or ()))
        return None

    async def _migrate(self, sql: str):
        """Idempotent migration; unexpected errors are logged, not swallowed."""
        try:
            await self.execute(sql, commit=True)
        except asyncpg.DuplicateColumnError:
            return
        except asyncpg.DuplicateTableError:
            return
        except asyncpg.DuplicateObjectError:
            return  # e.g. index already exists
        except asyncpg.PostgresError as e:
            logger.warning(f"Migration failed, continuing: {e} [{sql.strip()[:70]}]")

    async def create_tables(self):
        # NOTE: Telegram IDs need BIGINT ( exceed int32); prices DOUBLE PRECISION.
        # interval_min is a historic name - value is in SECONDS (main.MIN_INTERVAL).
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                id BIGINT PRIMARY KEY,
                phone TEXT,
                username TEXT,
                full_name TEXT,
                is_premium BOOLEAN DEFAULT FALSE,
                premium_until TIMESTAMP,
                interval_min INTEGER DEFAULT 10,
                view_count INTEGER DEFAULT 0,
                daily_views INTEGER DEFAULT 0,
                last_view_date TEXT,
                premium_plan_days INTEGER,
                premium_given_at TIMESTAMP,
                last_payment_amount TEXT,
                last_payment_rate TEXT
            );
            """,
            commit=True,
        )
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS CryptoPreferences (
                user_id BIGINT,
                coin_symbol TEXT,
                last_price DOUBLE PRECISION,
                last_checked_at TIMESTAMP,
                UNIQUE(user_id, coin_symbol)
            );
            """,
            commit=True,
        )
        await self.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prefs_user_coin "
            "ON CryptoPreferences(user_id, coin_symbol)",
            commit=True,
        )
