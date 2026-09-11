"""Pytest bootstrap.

Dummy env FIRST so `data/config.py` (which validates strictly) imports
without a real `.env` (CI). NOTE: `load_dotenv()` never overrides existing
vars, so these dummies intentionally WIN over any local `.env` during tests
- test isolation, no network, no real token touched.
"""
import os

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("PRIMARY_ADMIN", "1")
os.environ.setdefault("ADMINS", "1")

import pytest  # noqa: E402

import utils.api.crypto as crypto  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_price_caches():
    """Cross-test isolation for all module-level caches."""
    crypto._source_cache.clear()
    crypto._name_cache.clear()
    crypto._gecko_search_cache.clear()
    yield
    crypto._source_cache.clear()
    crypto._name_cache.clear()
    crypto._gecko_search_cache.clear()
