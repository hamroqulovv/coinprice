"""Pytest bootstrap: dummy env so imports work without a real .env (CI).

`data/config.py` calls `load_dotenv()` but never overrides already-set
variables, so these defaults only apply when no `.env` file exists.
"""
import os

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("PRIMARY_ADMIN", "1")
os.environ.setdefault("ADMINS", "1")
