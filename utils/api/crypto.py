import asyncio
import logging
from datetime import datetime, timedelta
from statistics import median
import os

import aiohttp


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (used when .env is missing / has placeholder text).
# These are verified public endpoints - see .env
# ---------------------------------------------------------------------------
DEFAULTS = {
    "COINBASE_BASE_URL": "https://api.coinbase.com/v2/prices",
    "BINANCE_URL": "https://api.binance.com/api/v3/ticker/price",
    "COINGECKO_URL": "https://api.coingecko.com/api/v3/simple/price",
    "UZS_RATE_URL": "https://cbu.uz/uz/arkhiv-kursov-valyut/json/",
    "RUB_RATE_URL": "https://www.cbr-xml-daily.ru/daily_json.js",
    "COINMARKETCAP_URL": "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
    # Secondary fiat source (free, no key) - used as fallback for UZS/RUB
    "ER_API_URL": "https://open.er-api.com/v6/latest/USD",
}

PLACEHOLDERS = {
    "coinbase url", "binance url", "coingecko url",
    "cbu url", "cbr-xml-daily url",
    "coinmarketcap api", "coinmarketcap url",
    "", "none", "null",
}

HEADERS = {"User-Agent": "coin-price-bot/1.1"}

# Fiat cache: CBU/CBR update DAILY, so 10 min TTL is plenty and reduces
# failure surface. Stale value is returned on fetch error.
# Crypto cache: 15s TTL so all users in one scheduler tick see same price
# and we don't hammer APIs (rate-limit protection = fewer outliers).
_rate_cache = {
    "uzs": {"rate": 11800.0, "updated": None, "source": "default"},
    "rub": {"rate": 84.5, "updated": None, "source": "default"},
}
_crypto_cache = {}  # coin -> {"price": float, "sources": str, "updated": datetime, "name": str|None}
# Gecko id cache: {"id": str|None, "name": str|None, "updated": datetime, "confirmed": bool}
# - success (id set): permanent, mapping deyarli o'zgarmaydi
# - confirmed not-found (200 + zero match): 1 soat (transient xatolar cache'lanmaydi)
_gecko_search_cache = {}  # SYMBOL -> entry

FIAT_TTL = timedelta(minutes=10)
CRYPTO_TTL = timedelta(seconds=15)
GECKO_NEG_TTL = timedelta(hours=1)

# Coin-level concurrency cap (respects free-tier rate limits)
_COIN_SEMAPHORE = asyncio.Semaphore(5)

# Shared aiohttp session (one per event loop)
_SESSION = None


async def _session():
    """Lazy shared ClientSession, recreated if closed or on a new loop."""
    global _SESSION
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if (
        _SESSION is None
        or _SESSION.closed
        or getattr(_SESSION, "_loop", None) is not loop
    ):
        if _SESSION is not None and not _SESSION.closed:
            try:
                await _SESSION.close()
            except Exception:
                pass
        _SESSION = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(limit=20),
        )
    return _SESSION


async def close_http_session():
    """Close the shared session (shutdown / tests)."""
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        try:
            await _SESSION.close()
        except Exception:
            pass
    _SESSION = None


async def _fetch(url, params=None, extra_headers=None):
    """GET JSON via shared session. Returns (status, json_or_None).

    Non-200 responses return (status, None). 429 is retried once after 2s.
    """
    session = await _session()
    try:
        async with session.get(url, params=params, headers=extra_headers) as r:
            status = r.status
            if status == 429:
                await asyncio.sleep(2)
                async with session.get(url, params=params, headers=extra_headers) as r2:
                    status = r2.status
                    if status != 200:
                        return status, None
                    try:
                        return status, await r2.json()
                    except Exception:
                        return status, None
            if status != 200:
                return status, None
            try:
                return status, await r.json()
            except Exception:
                return status, None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.debug(f"HTTP error {url}: {e}")
        return None, None


def _get_env(name):
    val = os.getenv(name, "").strip().strip("'\"")
    if not val or val.lower() in PLACEHOLDERS:
        return DEFAULTS.get(name)
    # bare "coinmarketcap API" style placeholder for the key
    if name == "COINMARKETCAP_API_KEY" and len(val) < 20:
        return None
    return val


def _is_sane_usd(price):
    try:
        p = float(price)
        return 0 < p < 10_000_000
    except Exception:
        return False


async def get_real_prices(coins):
    """
    Kripto narxlarini olish - bir nechta manbadan MEDIANA.
    Single-source ishonchsiz: bitta API glitch/stale qaytarsa ham median
    uni rad etadi. UZS/RUB har doim USD * rasmiy kursdan hisoblanadi
    (Coinbase RUB spot kabi aralash FX ishlatilmaydi - consistency uchun).
    Mustaqil coinlar parallel fetch qilinadi (semaphore bilan).
    """
    # Real valyuta kurslarini parallel yangilash (10 min cache + fallback chain)
    usd_to_uzs, usd_to_rub = await asyncio.gather(get_uzs_rate(), get_rub_rate())

    logger.info(f"📊 Kurslar: 1 USD = {usd_to_uzs} UZS, {usd_to_rub} RUB")

    async def _one(coin):
        coin = coin.upper().strip().lstrip("$")
        if not coin:
            return None
        async with _COIN_SEMAPHORE:
            price_usd, sources = await get_usd_median(coin)
        if price_usd and price_usd > 0:
            # Full precision saqlaymiz - rounding faqat display da (format_price)
            price_uzs = price_usd * usd_to_uzs
            price_rub = price_usd * usd_to_rub

            usd_precision = 8 if price_usd < 0.01 else 4

            logger.info(f"✅ {coin}: ${price_usd:.8f} ({sources})")
            return {
                "usd": price_usd,  # Raw qiymat (median)
                "usd_formatted": f"{price_usd:.{usd_precision}f}",
                "uzs": price_uzs,
                "rub": price_rub,
                "source": sources,
                "uzs_rate": usd_to_uzs,
                "rub_rate": usd_to_rub,
                "name": get_coin_display_name(coin),
            }
        logger.error(f"❌ {coin}: topilmadi")
        return None

    return list(await asyncio.gather(*(_one(c) for c in coins)))


async def get_usd_median(coin):
    """Barcha manbalardan narx yig'ib medianani qaytaradi. Returns (price, sources_str)."""
    # Short crypto cache - same tick consistency + rate-limit protection
    now = datetime.now()
    cached = _crypto_cache.get(coin)
    if cached and cached.get("updated") and (now - cached["updated"]) < CRYPTO_TTL:
        return cached["price"], cached["sources"]

    fetchers = (
        (get_from_binance, "Binance"),
        (get_from_bybit, "Bybit"),
        (get_from_coinbase, "Coinbase"),
        (get_from_coingecko, "CoinGecko"),
        (get_from_dexscreener, "DexScreener"),
        (get_from_coinmarketcap, "CoinMarketCap"),
    )

    # Mustaqil manbalar parallel so'raladi
    results = await asyncio.gather(
        *(fn(coin) for fn, _ in fetchers), return_exceptions=True
    )

    candidates = []  # list of (price, source_name)
    display_name = None
    for (fn, name), res in zip(fetchers, results):
        if isinstance(res, Exception):
            logger.debug(f"{name} median collect error for {coin}: {res}")
            continue
        try:
            raw, _ = res
            # Normalize: dict {"usd":.., "name":..} vs float
            if isinstance(raw, dict):
                price = raw.get("usd")
                if not display_name and raw.get("name"):
                    display_name = raw.get("name")
            else:
                price = raw
            if price and _is_sane_usd(price):
                candidates.append((float(price), name))
        except Exception as e:
            logger.debug(f"{name} median collect error for {coin}: {e}")

    if not candidates:
        return None, None

    prices = sorted(p for p, _ in candidates)

    if len(prices) == 1:
        final = prices[0]
        sources = candidates[0][1]
    elif len(prices) == 2:
        # 2 manba >2% farq qilsa - ogohlantirish, median (=mean) olamiz
        diff = abs(prices[0] - prices[1]) / prices[0] * 100 if prices[0] else 0
        if diff > 2.0:
            logger.warning(f"⚠️ {coin}: 2 source diverge {diff:.2f}%: {candidates}")
        final = float(median(prices))
        sources = "+".join(sorted({s for _, s in candidates}))
    else:
        m = float(median(prices))
        # Outlier >3% dan chetda bo'lsa - tashlab qayta median
        filtered = [p for p in prices if abs(p - m) / m * 100 <= 3.0] or prices
        if len(filtered) != len(prices):
            logger.warning(f"⚠️ {coin}: outlier dropped: {candidates} -> median {m}")
        final = float(median(filtered))
        sources = "+".join(sorted({s for _, s in candidates}))

    _crypto_cache[coin] = {"price": final, "sources": sources, "updated": now, "name": display_name}
    return final, sources


def get_coin_display_name(coin):
    """Oxirgi median yig'ishda topilgan to'liq nom (masalan: Pepe). Bo'lmasa None."""
    c = _crypto_cache.get(coin.upper().strip().lstrip("$"), {})
    return c.get("name")


async def get_from_coinbase(coin):
    """
    Coinbase Spot Price API - USD only.
    NOTE: RUB Coinbase spot ATAYLAB ishlatilmaydi - u Coinbase o'z FX kursi
    bilan hisoblanadi va CBR kursidan 2-5% farq qiladi (inconsistent).
    RUB har doim USD * CBR dan hisoblanadi.
    https://api.coinbase.com/v2/prices/{coin}-USD/spot
    """
    try:
        base = _get_env("COINBASE_BASE_URL")
        status, data_usd = await _fetch(f"{base}/{coin}-USD/spot")

        if status == 200 and data_usd:
            if "data" in data_usd and "amount" in data_usd["data"]:
                price_usd = float(data_usd["data"]["amount"])

                if _is_sane_usd(price_usd):
                    return {"usd": price_usd, "rub": None}, "Coinbase"

    except Exception as e:
        logger.debug(f"Coinbase error for {coin}: {e}")

    return None, None


async def get_from_coinmarketcap(coin):
    """
    CoinMarketCap API - aggregated VWAP, eng aniq "bozor" narxi.
    API kalit talab qiladi; kalit bo'lmasa skip.
    """
    try:
        # Check for API key
        api_key = _get_env("COINMARKETCAP_API_KEY")
        if not api_key:
            return None, None

        # Kriptovalyuta symbol mapping (migratsiyalar hisobga olingan)
        SYMBOL_MAPPING = {
            "NOT": "NOT",      # Notcoin
            "POLY": "POL",     # Polygon MATIC -> POL migratsiya
            "MATIC": "POL",
            "POL": "POL",
            "RENDER": "RENDER",  # RNDR -> RENDER migratsiya
            "RNDR": "RENDER",
            "TON": "TON",
            "BTC": "BTC",
            "ETH": "ETH",
            "SOL": "SOL",
            "DOGE": "DOGE",
            "XRP": "XRP",
            "ADA": "ADA",
            "BNB": "BNB",
            "USDT": "USDT",
            "USDC": "USDC",
            "SHIB": "SHIB",
            "TRX": "TRX",
            "DOT": "DOT",
            "LINK": "LINK",
            "UNI": "UNI",
            "LTC": "LTC",
            "BCH": "BCH",
            "AVAX": "AVAX",
            "XLM": "XLM",
            "ATOM": "ATOM",
            "ETC": "ETC",
            "FIL": "FIL",
            "HBAR": "HBAR",
            "VET": "VET",
            "ALGO": "ALGO",
            "ICP": "ICP",
            "NEAR": "NEAR",
            "APT": "APT",
            "SUI": "SUI",
            "ARB": "ARB",
            "OP": "OP",
            "PEPE": "PEPE",
            "WLD": "WLD",
            "JUP": "JUP",
            "BONK": "BONK",
            "WIF": "WIF",
            "PYTH": "PYTH",
            "FLOKI": "FLOKI",
            "RUNE": "RUNE",
            "GRT": "GRT",
            "IMX": "IMX",
            "INJ": "INJ",
            "TIA": "TIA",
            "SEI": "SEI",
            "FET": "FET",
            "SAND": "SAND",
            "MANA": "MANA",
            "AXS": "AXS",
            "XMR": "XMR",
            "STX": "STX",
        }

        # Symbol mapping or original symbol
        symbol = SYMBOL_MAPPING.get(coin, coin)

        # CoinMarketCap API endpoint
        url = _get_env("COINMARKETCAP_URL")
        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': api_key,
        }
        params = {
            'symbol': symbol,
            'convert': 'USD'
        }

        logger.debug(f"CoinMarketCap: Requesting price for {coin} (symbol: {symbol})")

        status, data = await _fetch(url, params=params, extra_headers=headers)

        if status == 200 and data:
            # Debug uchun ma'lumot
            logger.debug(f"CoinMarketCap response status: {status}")

            # Check if data exists
            if 'data' in data and symbol in data['data']:
                coin_data = data['data'][symbol]

                # Har doim birinchi elementni olish
                if isinstance(coin_data, list) and len(coin_data) > 0:
                    coin_info = coin_data[0]

                    if 'quote' in coin_info and 'USD' in coin_info['quote']:
                        price = coin_info['quote']['USD'].get('price')

                        if price is not None and _is_sane_usd(price):
                            logger.info(f"✅ CoinMarketCap: {coin} narxi: ${price}")
                            return float(price), "CoinMarketCap"

            # Agar symbol mapping bilan topilmasa, original symbol bilan urinib ko'ramiz
            if symbol != coin:
                logger.debug(f"CoinMarketCap: {symbol} bilan topilmadi, {coin} bilan urinib ko'ramiz")
                params['symbol'] = coin
                status, data = await _fetch(url, params=params, extra_headers=headers)

                if status == 200 and data:
                    if 'data' in data and coin in data['data']:
                        coin_data = data['data'][coin]

                        if isinstance(coin_data, list) and len(coin_data) > 0:
                            coin_info = coin_data[0]

                            if 'quote' in coin_info and 'USD' in coin_info['quote']:
                                price = coin_info['quote']['USD'].get('price')

                                if price is not None and _is_sane_usd(price):
                                    logger.info(f"✅ CoinMarketCap: {coin} narxi: ${price}")
                                    return float(price), "CoinMarketCap"

        elif status == 400:
            logger.debug(f"CoinMarketCap: Symbol {symbol} not found (400 error)")
        elif status == 401:
            logger.warning("CoinMarketCap: Invalid API key (401 error)")
        elif status == 429:
            logger.debug("CoinMarketCap: Rate limit exceeded (429 error)")
        elif status == 404:
            logger.debug(f"CoinMarketCap: {symbol} not found (404 error)")
        else:
            logger.debug(f"CoinMarketCap: Unexpected status code {status}")

    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.debug(f"CoinMarketCap timeout for {coin}")
    except Exception as e:
        logger.debug(f"CoinMarketCap error for {coin}: {e}")

    return None, None


# Binance symbol fallbacks (rename/delist migratsiyalar)
BINANCE_SYMBOL_FALLBACKS = {
    "POLY": ["POLUSDT", "MATICUSDT"],
    "MATIC": ["POLUSDT", "MATICUSDT"],
    "POL": ["POLUSDT", "MATICUSDT"],
    "RENDER": ["RENDERUSDT", "RNDRUSDT"],
    "RNDR": ["RENDERUSDT", "RNDRUSDT"],
}


async def get_from_binance(coin):
    """
    Binance Spot API - eng likvid bozor (real-time trade narxi).
    USDT juftlik ~ USD, farq 0.1% atrofida - median ichida tekislanadi.
    """
    try:
        url = _get_env("BINANCE_URL")

        symbols_to_try = BINANCE_SYMBOL_FALLBACKS.get(
            coin, [f"{coin}USDT"]
        )

        for symbol in symbols_to_try:
            try:
                status, data = await _fetch(url, params={"symbol": symbol})

                if status == 200 and data:
                    price = float(data.get("price", 0))
                    if _is_sane_usd(price):
                        return price, "Binance"
                elif status == 400:
                    continue  # invalid symbol - keyingi fallbackni urinish
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"Binance error for {coin}: {e}")

    return None, None


async def get_from_bybit(coin):
    """
    Bybit Spot v5 - 4-chi mustaqil manba (median tiebreaker).
    Free, no key: GET /v5/market/tickers?category=spot&symbol={COIN}USDT
    TON kabi delisted/rename coinlarda "Not supported" qaytarsa skip.
    """
    try:
        symbols_to_try = BINANCE_SYMBOL_FALLBACKS.get(
            coin, [f"{coin}USDT"]
        )
        for symbol in symbols_to_try:
            try:
                status, data = await _fetch(
                    "https://api.bybit.com/v5/market/tickers",
                    params={"category": "spot", "symbol": symbol},
                )
                if status == 200 and data:
                    lst = (data.get("result") or {}).get("list") or []
                    if lst:
                        price = float(lst[0].get("lastPrice", 0))
                        if _is_sane_usd(price):
                            return price, "Bybit"
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Bybit error for {coin}: {e}")

    return None, None


async def get_from_coingecko(coin):
    """
    CoinGecko API - aggregated fallback manba.
    """

    # Coinlarning CoinGecko ID mapping (yangilangan)
    COIN_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "SOL": "solana",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "DOT": "polkadot",
        "MATIC": "polygon-ecosystem-token",
        "POLY": "polygon-ecosystem-token",
        "POL": "polygon-ecosystem-token",
        "TRX": "tron",
        "TON": "the-open-network",
        "NOT": "notcoin",
        "USDT": "tether",
        "USDC": "usd-coin",
        "SHIB": "shiba-inu",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "LTC": "litecoin",
        "BCH": "bitcoin-cash",
        "PEPE": "pepe",
        "ARB": "arbitrum",
        "OP": "optimism",
        "NEAR": "near",
        "APT": "aptos",
        "SUI": "sui",
        "STX": "blockstack",
        "INJ": "injective-protocol",
        "TIA": "celestia",
        "SEI": "sei-network",
        "FET": "fetch-ai",
        "RENDER": "render-token",
        "RNDR": "render-token",
        "GRT": "the-graph",
        "IMX": "immutable-x",
        "RUNE": "thorchain",
        "ATOM": "cosmos",
        "FIL": "filecoin",
        "HBAR": "hedera-hashgraph",
        "VET": "vechain",
        "ALGO": "algorand",
        "ICP": "internet-computer",
        "SAND": "the-sandbox",
        "MANA": "decentraland",
        "AXS": "axie-infinity",
        "XLM": "stellar",
        "XMR": "monero",
        "ETC": "ethereum-classic",
        "WLD": "worldcoin-wld",
        "JUP": "jupiter-exchange-solana",
        "BONK": "bonk",
        "WIF": "dogwifcoin",
        "PYTH": "pyth-network",
        "FLOKI": "floki",
    }

    # Fast path: mashhur coinlar network'siz topiladi
    coin_id = COIN_IDS.get(coin)
    coin_name = None
    if coin_id is None:
        # Noma'lum ticker -> dinamik resolver (/search + cache)
        coin_id = await resolve_coingecko_id(coin)
        if coin_id is None:
            return None, None
        coin_name = _gecko_search_cache.get(coin.upper().strip().lstrip("$"), {}).get("name")

    try:
        url = _get_env("COINGECKO_URL")

        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "false"
        }

        status, data = await _fetch(url, params=params)

        if status == 200 and data:
            if coin_id in data and "usd" in data[coin_id]:
                price = float(data[coin_id]["usd"])
                if _is_sane_usd(price):
                    if coin_name:
                        return {"usd": price, "name": coin_name}, "CoinGecko"
                    return price, "CoinGecko"

    except Exception as e:
        logger.debug(f"CoinGecko error for {coin}: {e}")

    return None, None


async def resolve_coingecko_id(symbol):
    """Ticker symbol (masalan 'MAGMA') ni CoinGecko coin id ga
    (masalan 'magma-finance') aylantirish - /search endpoint orqali.

    Bir xil ticker bir nechta loyihada bo'lsa, eng kichik (non-null)
    market_cap_rank tanlanadi; rank bo'lmasa CoinGecko tartibidagi
    birinchisi olinadi. Topilmasa yoki xatoda None qaytadi (raise yo'q).

    Cache: muvaffaqiyatli mapping permanent; 200 + zero-match 1 soat;
    xato/timeout cache'lanmaydi (keyingi safar qayta uriniladi).
    """
    try:
        sym = (symbol or "").upper().strip().lstrip("$")
        if not sym:
            return None
        now = datetime.now()
        cached = _gecko_search_cache.get(sym)
        if cached:
            if cached.get("id"):
                return cached["id"]
            if cached.get("confirmed") and (now - cached["updated"]) < GECKO_NEG_TTL:
                return None
        status, data = await _fetch(
            "https://api.coingecko.com/api/v3/search",
            params={"query": sym},
        )
        if status != 200 or not data:
            return None  # transient - cache'lanmaydi
        coins = data.get("coins", []) or []
        exact = [c for c in coins if str(c.get("symbol", "")).upper() == sym]
        if not exact:
            _gecko_search_cache[sym] = {"id": None, "name": None, "updated": now, "confirmed": True}
            return None

        def _rank(c):
            mr = c.get("market_cap_rank")
            return mr if isinstance(mr, int) and mr > 0 else 10_000_000

        best = sorted(exact, key=_rank)[0]
        coin_id = best.get("id") or None
        if not coin_id:
            return None  # malformed - cache'lanmaydi
        _gecko_search_cache[sym] = {
            "id": coin_id,
            "name": best.get("name") or best.get("symbol"),
            "updated": now,
            "confirmed": True,
        }
        return coin_id
    except Exception as e:
        logger.debug(f"resolve_coingecko_id error for {symbol}: {e}")
        return None


async def suggest_coins(query, limit=5):
    """Gecko search orqali o'xshash coinlar ro'yxati (topilmaganda taklif uchun)."""
    try:
        q = (query or "").upper().strip().lstrip("$")
        if not q:
            return []
        status, data = await _fetch(
            "https://api.coingecko.com/api/v3/search",
            params={"query": q},
        )
        if status != 200 or not data:
            return []
        out = []
        for c in (data.get("coins", []) or [])[:limit]:
            sym = str(c.get("symbol", "")).upper()
            name = c.get("name", "")
            if sym:
                out.append({"symbol": sym, "name": name})
        return out
    except Exception as e:
        logger.debug(f"suggest_coins error for {query}: {e}")
        return []


async def get_from_dexscreener(coin):
    """
    DexScreener search API - DEX dagi HAR QANDAY token (memecoinlar ham).
    Free, key shart emas: GET /latest/dex/search?q={symbol}
    Eng yuqori likvidlikdagi juftlik narxi olinadi.
    Returns ({"usd":.., "name":..}, "DexScreener") yoki (None, None).
    """
    symbol = coin.upper().strip().lstrip("$")
    if not symbol:
        return None, None
    try:
        status, data = await _fetch(
            "https://api.dexscreener.com/latest/dex/search",
            params={"q": symbol},
        )
        if status != 200 or not data:
            return None, None
        pairs = (data.get("pairs", []) or [])
        if not pairs:
            return None, None

        # Aniq symbol match ustun, keyin likvidlik/volum bo'yicha
        exact = [
            p for p in pairs
            if str((p.get("baseToken") or {}).get("symbol", "")).upper() == symbol
            and p.get("priceUsd")
        ]
        pool = exact or [p for p in pairs if p.get("priceUsd")]
        if not pool:
            return None, None

        def _score(p):
            try:
                liq = ((p.get("liquidity") or {}).get("usd")) or 0
                vol = ((p.get("volume") or {}).get("h24")) or 0
                return (float(liq), float(vol))
            except Exception:
                return (0, 0)

        best = sorted(pool, key=_score, reverse=True)[0]
        price = float(best.get("priceUsd", 0))
        name = (best.get("baseToken") or {}).get("name") or (best.get("baseToken") or {}).get("symbol")
        if _is_sane_usd(price):
            return {"usd": price, "name": name}, "DexScreener"
    except Exception as e:
        logger.debug(f"DexScreener error for {coin}: {e}")

    return None, None


async def _fetch_er_rate(ccy):
    """Secondary fiat source: open.er-api.com (free, no key). Returns rate or None."""
    try:
        _, data = await _fetch(DEFAULTS["ER_API_URL"])
        if data:
            rates = data.get("rates", {})
            rate = rates.get(ccy)
            if rate:
                # ER API gives UZS per USD directly
                return float(rate)
    except Exception as e:
        logger.debug(f"ER-API {ccy} error: {e}")
    return None


async def get_uzs_rate():
    """
    USD → UZS (O'zbekiston Markaziy Banki, rasmiy).
    Chain: CBU primary -> ER-API secondary -> stale cache -> default.
    CBU kuniga 1 marta yangilanadi, shuning uchun 10 min cache.
    """
    global _rate_cache

    now = datetime.now()
    cache = _rate_cache["uzs"]

    # Cache yangimi?
    if cache["updated"] and (now - cache["updated"]) < FIAT_TTL:
        return cache["rate"]

    # 1. CBU primary
    try:
        url = _get_env("UZS_RATE_URL")
        status, data = await _fetch(url)

        if status == 200 and data:
            # CBU list qaytaradi: [{"Ccy": "USD", "Rate": "11783.47", ...}]
            items = data if isinstance(data, list) else data.get("rates", [])
            for currency in items:
                if isinstance(currency, dict) and currency.get("Ccy") == "USD":
                    rate = float(str(currency.get("Rate", "")).replace(",", "").strip())
                    if 1000 < rate < 100000:  # sanity: UZS plausible range
                        _rate_cache["uzs"] = {"rate": rate, "updated": now, "source": "CBU"}
                        logger.info(f"✅ UZS kurs yangilandi (CBU): {rate}")
                        return rate

    except Exception as e:
        logger.warning(f"UZS CBU xato: {e}")

    # 2. ER-API secondary
    er = await _fetch_er_rate("UZS")
    if er and 1000 < er < 100000:
        _rate_cache["uzs"] = {"rate": er, "updated": now, "source": "ER-API"}
        logger.info(f"✅ UZS kurs yangilandi (ER-API fallback): {er}")
        return er

    # 3. Stale cache / default
    if cache["updated"]:
        logger.warning(f"⚠️ UZS: stale kurs ishlatilmoqda: {cache['rate']} ({cache.get('source')})")
    return cache["rate"]


async def get_rub_rate():
    """
    USD → RUB (Rossiya Markaziy Banki, rasmiy).
    Chain: CBR primary -> ER-API secondary -> stale cache -> default.
    """
    global _rate_cache

    now = datetime.now()
    cache = _rate_cache["rub"]

    if cache["updated"] and (now - cache["updated"]) < FIAT_TTL:
        return cache["rate"]

    # 1. CBR primary
    try:
        url = _get_env("RUB_RATE_URL")
        status, data = await _fetch(url)

        if status == 200 and data:
            if "Valute" in data and "USD" in data["Valute"]:
                rate = float(data["Valute"]["USD"]["Value"])

                if 10 < rate < 500:  # sanity: RUB plausible range
                    _rate_cache["rub"] = {"rate": rate, "updated": now, "source": "CBR"}
                    logger.info(f"✅ RUB kurs yangilandi (CBR): {rate}")
                    return rate

    except Exception as e:
        logger.warning(f"RUB CBR xato: {e}")

    # 2. ER-API secondary
    er = await _fetch_er_rate("RUB")
    if er and 10 < er < 500:
        _rate_cache["rub"] = {"rate": er, "updated": now, "source": "ER-API"}
        logger.info(f"✅ RUB kurs yangilandi (ER-API fallback): {er}")
        return er

    if cache["updated"]:
        logger.warning(f"⚠️ RUB: stale kurs ishlatilmoqda: {cache['rate']} ({cache.get('source')})")
    return cache["rate"]


# TEST FUNCTION
async def _demo():
    print("=" * 60)
    print("🚀 CRYPTO PRICE CHECKER - MULTI-SOURCE MEDIAN (async)")
    print("=" * 60)

    # Check if CoinMarketCap API key is available
    cmc_api_key = _get_env('COINMARKETCAP_API_KEY')
    if cmc_api_key:
        print(f"✅ CoinMarketCap API key found: {cmc_api_key[:10]}...")
    else:
        print("⚠️  CoinMarketCap API key not found - median without CMC")

    # Test coinlar
    test_coins = ["BTC", "ETH", "SOL", "TON", "DOGE", "NOT", "SHIB"]

    print(f"\n🔍 Testing {len(test_coins)} coins...\n")
    print("USD = median(Binance, Bybit, Coinbase, CoinGecko[, CMC])")
    print("UZS = USD * CBU | RUB = USD * CBR")
    print()

    results = await get_real_prices(test_coins)

    print("\n" + "=" * 60)
    print("📊 NATIJALAR:")
    print("=" * 60 + "\n")

    for i, coin in enumerate(test_coins):
        if results[i]:
            r = results[i]
            print(f"💰 {coin} ({r.get('source', 'Unknown')})")
            print(f"   💵 USD: ${r['usd']:,.8f}")
            print(f"   🇺🇿 UZS: {r['uzs']:,.2f} so'm (rate {r.get('uzs_rate')})")
            print(f"   🇷🇺 RUB: {r['rub']:,.4f} ₽ (rate {r.get('rub_rate')})")
            print()
        else:
            print(f"❌ {coin}: TOPILMADI\n")

    print("=" * 60)
    await close_http_session()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(_demo())
