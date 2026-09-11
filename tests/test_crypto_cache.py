"""Unit tests for the per-source crypto price cache.

External price sources are mocked - no network access. Verifies that a
second lookup of the same coin within the source TTL does NOT hit external
APIs again (this is what lets one scheduler tick serve all users with one
fetch per distinct coin, and keeps manual lookups live).
"""
import asyncio
from unittest.mock import patch

import utils.api.crypto as crypto


async def _null_source(coin):
    return None, None


def _run(coro):
    return asyncio.run(coro)


def _clear():
    crypto._source_cache.clear()
    crypto._name_cache.clear()


def test_source_ttls_fast_exchanges_live_slow_aggregators_cached():
    assert crypto._SOURCE_TTLS["Binance"] <= 5.0
    assert crypto._SOURCE_TTLS["Bybit"] <= 5.0
    assert crypto._SOURCE_TTLS["Coinbase"] <= 5.0
    assert crypto._SOURCE_TTLS["CoinGecko"] >= 60.0


def test_usd_median_aggregates_mocked_sources():
    _clear()
    try:
        async def fake_binance(coin):
            return 103.5, "Binance"

        async def fake_bybit(coin):
            return 104.5, "Bybit"

        async def fake_coinbase(coin):
            return {"usd": 104.0, "rub": None}, "Coinbase"

        with patch.object(crypto, "get_from_binance", side_effect=fake_binance), \
             patch.object(crypto, "get_from_bybit", side_effect=fake_bybit), \
             patch.object(crypto, "get_from_coinbase", side_effect=fake_coinbase), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            price, sources = _run(crypto.get_usd_median("TST"))
        # median(103.5, 104.0, 104.5) == 104.0 (all within trust tolerance)
        assert price == 104.0
        assert "Binance" in sources and "Bybit" in sources and "Coinbase" in sources
    finally:
        _clear()


def test_single_exchange_outlier_dropped():
    """Binance stale quote far from aggregated venues must not win."""
    _clear()
    try:
        async def stale_binance(coin):
            return 1.60, "Binance"

        async def true_coinbase(coin):
            return {"usd": 1.37575, "rub": None}, "Coinbase"

        with patch.object(crypto, "get_from_binance", side_effect=stale_binance), \
             patch.object(crypto, "get_from_bybit", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinbase", side_effect=true_coinbase), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            price, sources = _run(crypto.get_usd_median("TON"))
        assert price == 1.37575
        assert "Binance" not in sources
    finally:
        _clear()


def test_dex_only_last_resort():
    """Unverified DEX price used only when nothing else answers."""
    _clear()
    try:
        async def dex_only(coin):
            return {"usd": 0.59, "name": "X"}, "DexScreener"

        with patch.object(crypto, "get_from_binance", side_effect=_null_source), \
             patch.object(crypto, "get_from_bybit", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinbase", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=dex_only), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            price, sources = _run(crypto.get_usd_median("XXX"))
        assert price == 0.59
        assert sources == "DexScreener"
    finally:
        _clear()


def test_usd_median_cache_avoids_refetch():
    _clear()
    calls = []
    try:
        async def counting_binance(coin):
            calls.append(coin)
            return 50.0, "Binance"

        with patch.object(crypto, "get_from_binance", side_effect=counting_binance), \
             patch.object(crypto, "get_from_bybit", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinbase", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
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
        _clear()


def test_misses_are_not_cached():
    """Transient (None,None) must NOT be cached - next tick retries."""
    _clear()
    calls = []
    try:
        async def flaky(coin):
            calls.append(coin)
            if len(calls) == 1:
                return None, None
            return 77.0, "Binance"

        with patch.object(crypto, "get_from_binance", side_effect=flaky), \
             patch.object(crypto, "get_from_bybit", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinbase", side_effect=_null_source), \
             patch.object(crypto, "get_from_coingecko", side_effect=_null_source), \
             patch.object(crypto, "get_from_dexscreener", side_effect=_null_source), \
             patch.object(crypto, "get_from_coinmarketcap", side_effect=_null_source):
            assert _run(crypto.get_usd_median("FLU")) == (None, None)
            price, _ = _run(crypto.get_usd_median("FLU"))
            assert price == 77.0
            assert len(calls) == 2
    finally:
        _clear()
