import sqlite3

class Database:
    def __init__(self, path_to_db="main.db"):
        self.path_to_db = path_to_db

    @property
    def connection(self):
        return sqlite3.connect(self.path_to_db)

    def execute(self, sql: str, parameters: tuple = None, fetchone=False, fetchall=False, commit=False):
        if not parameters:
            parameters = ()
        connection = self.connection
        cursor = connection.cursor()
        data = None
        cursor.execute(sql, parameters)

        if commit:
            connection.commit()
        if fetchall:
            data = cursor.fetchall()
        if fetchone:
            data = cursor.fetchone()
        connection.close()
        return data

    def create_tables(self):
        # Users jadvalini yaratish
        sql_users = """
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY,
            phone TEXT,
            username TEXT,
            full_name TEXT,
            is_premium BOOLEAN DEFAULT 0,
            premium_until DATETIME,
            interval_min INTEGER DEFAULT 40,
            view_count INTEGER DEFAULT 0
        );
        """
        self.execute(sql_users, commit=True)
        # Add daily tracking columns if they do not exist (for existing DBs)
        try:
            self.execute("ALTER TABLE Users ADD COLUMN daily_views INTEGER DEFAULT 0", commit=True)
        except Exception:
            pass
        try:
            self.execute("ALTER TABLE Users ADD COLUMN last_view_date TEXT", commit=True)
        except Exception:
            pass
        # Add premium metadata columns for new installs or existing DBs
        try:
            self.execute("ALTER TABLE Users ADD COLUMN premium_plan_days INTEGER", commit=True)
        except Exception:
            pass
        try:
            self.execute("ALTER TABLE Users ADD COLUMN premium_given_at DATETIME", commit=True)
        except Exception:
            pass
        # Track last payment amount and exchange rate for admin view
        try:
            self.execute("ALTER TABLE Users ADD COLUMN last_payment_amount TEXT", commit=True)
        except Exception:
            pass
        try:
            self.execute("ALTER TABLE Users ADD COLUMN last_payment_rate TEXT", commit=True)
        except Exception:
            pass
        
        # CryptoPreferences jadvalini yaratish
        sql_prefs = """
        CREATE TABLE IF NOT EXISTS CryptoPreferences (
            user_id INTEGER,
            coin_symbol TEXT,
            last_price REAL,
            last_checked_at DATETIME,
            UNIQUE(user_id, coin_symbol)
        );
        """
        self.execute(sql_prefs, commit=True)
        # Mavjud DB'lar uchun yangi ustunlar (scheduler holati DB'da saqlanadi)
        try:
            self.execute("ALTER TABLE CryptoPreferences ADD COLUMN last_price REAL", commit=True)
        except Exception:
            pass
        try:
            self.execute("ALTER TABLE CryptoPreferences ADD COLUMN last_checked_at DATETIME", commit=True)
        except Exception:
            pass
        # Mavjud DB'lardagi duplicate kuzatuvlarni tozalash
        # (race'da ikki marta bosish bir xil (user, coin) ni 2 marta yozishi mumkin)
        try:
            self.execute("""
                DELETE FROM CryptoPreferences WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM CryptoPreferences GROUP BY user_id, coin_symbol
                )
            """, commit=True)
        except Exception:
            pass
        # Mavjud DB'lar uchun uniqueness (yangi DB'da CREATE TABLE'dagi
        # UNIQUE orqali allaqachon bor; IF NOT EXISTS tufayli idempotent)
        try:
            self.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_prefs_user_coin "
                "ON CryptoPreferences(user_id, coin_symbol)",
                commit=True,
            )
        except Exception:
            pass

    def clear_user_preferences(self, user_id):
        sql = "DELETE FROM CryptoPreferences WHERE user_id=?"
        self.execute(sql, (user_id,), commit=True)