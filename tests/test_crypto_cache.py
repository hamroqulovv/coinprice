"""Unit tests for the global crypto price cache (task 3).

External price sources are mocked - no network access. Verifies that a
second lookup of the same coin within the TTL does NOT hit external APIs
again (this is what lets one scheduler tick serve all users with one
fetch per distinct coin).
"""
import asyncio
from unittest.mock import patch

import utils.api.crypto as crypto


async def _null_source(coin):
    return None, None


def _run(coro):
    return asyncio.run(coro)


def test_usd_median_aggregates_mocked_sources():
    crypto._crypto_cache.clear()
    try:
        async def fake_binance(coin):
            return 100.0, "Binance"

        async def fake_bybit(coin):
            return 102.0, "Bybit"

        async def fake_coinbase(coin):
            return {"usd": 104.0, "rub": None}, "Coinbase"

        with patch.object(crypto, "get_from_binance", side_effect=fake_binance), \
             patch.object(crypto, "get_from_bybit", side_effect=fake_bybit), \
             patch.object(crypto, "get_from_coinbase", side_effect=fake_coinbase), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko_search", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            price, sources = _run(crypto.get_usd_median("TST"))
        # median(100, 102, 104) == 102
        assert price == 102.0
        assert "Binance" in sources and "Bybit" in sources and "Coinbase" in sources
    finally:
        crypto._crypto_cache.clear()


def test_usd_median_cache_avoids_refetch():
    crypto._crypto_cache.clear()
    calls = []
    try:
        async def counting_binance(coin):
            calls.append(coin)
            return 50.0, "Binance"

        with patch.object(crypto, "get_from_binance", side_effect=counting_binance), \
             patch.object(crypto, "get_from_bybit", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinbase", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko_search", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            price1, _ = _run(crypto.get_usd_median("CCH"))
            assert price1 == 50.0
            assert len(calls) == 1
            # Second lookup inside TTL: cache hit, no new external call
            price2, _ = _run(crypto.get_usd_median("CCH"))
            assert price2 == 50.0
            assert len(calls) == 1
    finally:
        crypto._crypto_cache.clear()
