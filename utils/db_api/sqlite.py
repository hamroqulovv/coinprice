import logging
import sqlite3

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path_to_db="main.db"):
        self.path_to_db = path_to_db

    @property
    def connection(self):
        # timeout: concurrent writer'lar bir-birini kutadi (fail o'rniga).
        # WAL: reader'lar writer'ni bloklamaydi - scheduler + handler'lar
        # bir vaqtda ishlaganda "database is locked" bo'lmaydi.
        connection = sqlite3.connect(self.path_to_db, timeout=30.0)
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("PRAGMA busy_timeout=30000;")
            connection.execute("PRAGMA synchronous=NORMAL;")
        except sqlite3.Error as e:
            logger.debug(f"PRAGMA setup skipped: {e}")
        return connection

    def execute(self, sql: str, parameters: tuple = None, fetchone=False, fetchall=False, commit=False):
        if not parameters:
            parameters = ()
        connection = self.connection
        try:
            cursor = connection.cursor()
            cursor.execute(sql, parameters)

            data = None
            if fetchall:
                data = cursor.fetchall()
            elif fetchone:
                data = cursor.fetchone()
            if commit:
                connection.commit()
            return data
        finally:
            connection.close()

    def execute_many(self, sql: str, seq_of_parameters, commit=True):
        """Bitta transaction'da ko'p yozuv (scheduler last_price batch)."""
        connection = self.connection
        try:
            cursor = connection.cursor()
            cursor.executemany(sql, seq_of_parameters)
            if commit:
                connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def _migrate(self, sql: str):
        """Idempotent migratsiya: allaqachon qo'llangan bo'lsa jim,
        kutilmagan xatoda ogohlantiradi (jim yutib yubormaydi)."""
        try:
            self.execute(sql, commit=True)
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                return
            logger.warning(f"Migration issue, continuing: {e} [{sql.strip()[:70]}]")
        except sqlite3.Error as e:
            logger.warning(f"Migration failed, continuing: {e} [{sql.strip()[:70]}]")

    def create_tables(self):
        # Users jadvalini yaratish
        # NOTE: interval_min tarixiy nom - qiymat SEKUNDlarda (main.MIN_INTERVAL).
        sql_users = """
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY,
            phone TEXT,
            username TEXT,
            full_name TEXT,
            is_premium BOOLEAN DEFAULT 0,
            premium_until DATETIME,
            interval_min INTEGER DEFAULT 10,
            view_count INTEGER DEFAULT 0
        );
        """
        self.execute(sql_users, commit=True)
        # Add daily tracking columns if they do not exist (for existing DBs)
        self._migrate("ALTER TABLE Users ADD COLUMN daily_views INTEGER DEFAULT 0")
        self._migrate("ALTER TABLE Users ADD COLUMN last_view_date TEXT")
        # Add premium metadata columns for new installs or existing DBs
        self._migrate("ALTER TABLE Users ADD COLUMN premium_plan_days INTEGER")
        self._migrate("ALTER TABLE Users ADD COLUMN premium_given_at DATETIME")
        # Track last payment amount and exchange rate for admin view
        self._migrate("ALTER TABLE Users ADD COLUMN last_payment_amount TEXT")
        self._migrate("ALTER TABLE Users ADD COLUMN last_payment_rate TEXT")

        # CryptoPreferences jadvalini yaratish.
        # Uniqueness yagona joyda: uq_prefs_user_coin index (fresh + legacy
        # DB'larda bir xil enforcement, ikkinchi redundant index yo'q).
        # uq index WHERE user_id=? so'rovlarini ham tezlashtiradi (leftmost).
        sql_prefs = """
        CREATE TABLE IF NOT EXISTS CryptoPreferences (
            user_id INTEGER,
            coin_symbol TEXT,
            last_price REAL,
            last_checked_at DATETIME
        );
        """
        self.execute(sql_prefs, commit=True)
        # Mavjud DB'lar uchun yangi ustunlar (scheduler holati DB'da saqlanadi)
        self._migrate("ALTER TABLE CryptoPreferences ADD COLUMN last_price REAL")
        self._migrate("ALTER TABLE CryptoPreferences ADD COLUMN last_checked_at DATETIME")
        # Mavjud DB'lardagi duplicate kuzatuvlarni tozalash - FAQAT duplicate
        # bo'lsa (har boot'da full-table scan/lock bo'lmasligi uchun).
        # (race'da ikki marta bosish bir xil (user, coin) ni 2 marta yozishi mumkin)
        try:
            dupes = self.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT user_id || char(9) || coin_symbol)"
                " FROM CryptoPreferences",
                fetchone=True,
            )
            if dupes and dupes[0] > 0:
                self.execute(
                    "DELETE FROM CryptoPreferences WHERE rowid NOT IN ("
                    " SELECT MAX(rowid) FROM CryptoPreferences"
                    " GROUP BY user_id, coin_symbol)",
                    commit=True,
                )
                logger.info(f"Deduplicated {dupes[0]} watchlist rows")
        except sqlite3.Error as e:
            logger.warning(f"Watchlist dedup skipped: {e}")
        self._migrate(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prefs_user_coin "
            "ON CryptoPreferences(user_id, coin_symbol)"
        )
