"""Unit tests for the CoinGecko resolver (resolve_coingecko_id).

HTTP is fully mocked (crypto._fetch) - no real network access.
"""
import asyncio
import os
from unittest.mock import patch

import utils.api.crypto as crypto


def _run(coro):
    return asyncio.run(coro)


def setup_function(_):
    crypto._gecko_search_cache.clear()


def teardown_function(_):
    crypto._gecko_search_cache.clear()


def _search_response(coins):
    return (200, {"coins": coins})


def test_fast_path_never_calls_resolver():
    """BTC is in COIN_IDS: price fetch only, no /search call."""
    calls = []

    async def fake_fetch(url, params=None, extra_headers=None):
        calls.append((url, (params or {}).get("query"), (params or {}).get("ids")))
        if params and "ids" in params:
            return 200, {"bitcoin": {"usd": 50000.0}}
        return 404, None

    with patch.object(crypto, "_fetch", side_effect=fake_fetch), \
         patch.object(crypto, "resolve_coingecko_id",
                      side_effect=AssertionError("resolver must not be called")) as _:
        price, source = _run(crypto.get_from_coingecko("BTC"))
    assert price == 50000.0
    assert source == "CoinGecko"
    # only the price call, never /search
    assert all(q is None for _, q, _ in calls)
    assert len(calls) == 1


def test_single_match_resolves():
    async def fake_fetch(url, params=None, extra_headers=None):
        if params and "query" in params:
            return _search_response([
                {"id": "magma-finance", "symbol": "magma", "name": "Magma Finance",
                 "market_cap_rank": 500},
            ])
        return 200, {"magma-finance": {"usd": 0.42}}

    with patch.object(crypto, "_fetch", side_effect=fake_fetch):
        assert _run(crypto.resolve_coingecko_id("MAGMA")) == "magma-finance"


def test_multiple_matches_pick_lowest_rank():
    async def fake_fetch(url, params=None, extra_headers=None):
        return _search_response([
            {"id": "magma-other", "symbol": "magma", "name": "Magma Other",
             "market_cap_rank": 900},
            {"id": "magma-finance", "symbol": "magma", "name": "Magma Finance",
             "market_cap_rank": 100},
            {"id": "magma-xyz", "symbol": "magma", "name": "Magma XYZ",
             "market_cap_rank": None},
        ])

    with patch.object(crypto, "_fetch", side_effect=fake_fetch):
        assert _run(crypto.resolve_coingecko_id("MAGMA")) == "magma-finance"


def test_zero_matches_returns_none():
    async def fake_fetch(url, params=None, extra_headers=None):
        return _search_response([
            {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1},
        ])

    with patch.object(crypto, "_fetch", side_effect=fake_fetch):
        assert _run(crypto.resolve_coingecko_id("ZZZNOTREAL")) is None


def test_cache_avoids_second_http_call():
    calls = []

    async def fake_fetch(url, params=None, extra_headers=None):
        calls.append(url)
        return _search_response([
            {"id": "magma-finance", "symbol": "magma", "name": "Magma Finance",
             "market_cap_rank": 500},
        ])

    with patch.object(crypto, "_fetch", side_effect=fake_fetch):
        assert _run(crypto.resolve_coingecko_id("MAGMA")) == "magma-finance"
        assert _run(crypto.resolve_coingecko_id("MAGMA")) == "magma-finance"
    assert len(calls) == 1


def test_network_error_returns_none_without_poisoning_cache():
    calls = []

    async def flaky_fetch(url, params=None, extra_headers=None):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("boom")
        return _search_response([
            {"id": "magma-finance", "symbol": "magma", "name": "Magma Finance",
             "market_cap_rank": 500},
        ])

    with patch.object(crypto, "_fetch", side_effect=flaky_fetch):
        # error -> None, and must NOT be cached ...
        assert _run(crypto.resolve_coingecko_id("MAGMA")) is None
        # ... so the retry really hits HTTP again and succeeds
        assert _run(crypto.resolve_coingecko_id("MAGMA")) == "magma-finance"
    assert len(calls) == 2


def test_resolver_used_for_unknown_symbol_price():
    """End of chain: unknown symbol resolves then prices via resolved id."""
    async def fake_fetch(url, params=None, extra_headers=None):
        if params and "query" in params:
            return _search_response([
                {"id": "magma-finance", "symbol": "magma", "name": "Magma Finance",
                 "market_cap_rank": 500},
            ])
        return 200, {"magma-finance": {"usd": 0.42}}

    with patch.object(crypto, "_fetch", side_effect=fake_fetch):
        res, source = _run(crypto.get_from_coingecko("MAGMA"))
    assert source == "CoinGecko"
    assert res == {"usd": 0.42, "name": "Magma Finance"}


def test_demo_headers_empty_without_key():
    old = os.environ.get("COINGECKO_API_KEY")
    os.environ.pop("COINGECKO_API_KEY", None)
    try:
        assert crypto._gecko_demo_headers() == {}
    finally:
        if old is not None:
            os.environ["COINGECKO_API_KEY"] = old


def test_demo_headers_set_with_key():
    old = os.environ.get("COINGECKO_API_KEY")
    os.environ["COINGECKO_API_KEY"] = "CG-" + "x" * 30
    try:
        assert crypto._gecko_demo_headers() == {"x-cg-demo-api-key": "CG-" + "x" * 30}
    finally:
        if old is not None:
            os.environ["COINGECKO_API_KEY"] = old
        else:
            os.environ.pop("COINGECKO_API_KEY", None)
