import requests
import logging
from datetime import datetime, timedelta
from statistics import median
import os


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
_crypto_cache = {}  # coin -> {"price": float, "sources": str, "updated": datetime}
_gecko_search_cache = {}  # SYMBOL -> {"id": str, "name": str, "updated": datetime}

FIAT_TTL = timedelta(minutes=10)
CRYPTO_TTL = timedelta(seconds=15)
GECKO_SEARCH_TTL = timedelta(hours=24)


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


def get_real_prices(coins):
    """
    Kripto narxlarini olish - bir nechta manbadan MEDIANA.
    Single-source ishonchsiz: bitta API glitch/stale qaytarsa ham median
    uni rad etadi. UZS/RUB har doim USD * rasmiy kursdan hisoblanadi
    (Coinbase RUB spot kabi aralash FX ishlatilmaydi - consistency uchun).
    """
    results = []

    # Real valyuta kurslarini yangilash (10 min cache + fallback chain)
    usd_to_uzs = get_uzs_rate()
    usd_to_rub = get_rub_rate()

    logger.info(f"📊 Kurslar: 1 USD = {usd_to_uzs} UZS, {usd_to_rub} RUB")

    for idx, coin in enumerate(coins):
        coin = coin.upper().strip().lstrip("$")
        if not coin:
            results.append(None)
            continue

        # Rate-limit himoyasi: coinlar orasida qisqa pauza (birinchi coindan tashqari)
        if idx > 0:
            import time as _t
            _t.sleep(0.4)

        price_usd, sources = get_usd_median(coin)

        if price_usd and price_usd > 0:
            # Full precision saqlaymiz - rounding faqat display da (format_price)
            price_uzs = price_usd * usd_to_uzs
            price_rub = price_usd * usd_to_rub

            usd_precision = 8 if price_usd < 0.01 else 4

            results.append({
                "usd": price_usd,  # Raw qiymat (median)
                "usd_formatted": f"{price_usd:.{usd_precision}f}",
                "uzs": price_uzs,
                "rub": price_rub,
                "source": sources,
                "uzs_rate": usd_to_uzs,
                "rub_rate": usd_to_rub,
                "name": get_coin_display_name(coin),
            })
            logger.info(f"✅ {coin}: ${price_usd:.8f} ({sources})")
        else:
            logger.error(f"❌ {coin}: topilmadi")
            results.append(None)

    return results


def get_usd_median(coin):
    """Barcha manbalardan narx yig'ib medianani qaytaradi. Returns (price, sources_str)."""
    # Short crypto cache - same tick consistency + rate-limit protection
    now = datetime.now()
    cached = _crypto_cache.get(coin)
    if cached and cached.get("updated") and (now - cached["updated"]) < CRYPTO_TTL:
        return cached["price"], cached["sources"]

    candidates = []  # list of (price, source_name)
    display_name = None

    for fn, name in (
        (get_from_binance, "Binance"),
        (get_from_bybit, "Bybit"),
        (get_from_coinbase, "Coinbase"),
        (get_from_coingecko, "CoinGecko"),
        (get_from_coingecko_search, "GeckoSearch"),
        (get_from_dexscreener, "DexScreener"),
        (get_from_coinmarketcap, "CoinMarketCap"),
    ):
        try:
            raw, _ = fn(coin)
            # Normalize: Coinbase dict {"usd":..} vs others float
            # DexScreener/GeckoSearch dict {"usd":.., "name":..} ham bo'lishi mumkin
            if isinstance(raw, dict):
                price = raw.get("usd")
                if not display_name and raw.get("name"):
                    display_name = raw.get("name")
            else:
                price = raw
            if price and _is_sane_usd(price):
                candidates.append((float(price), name))
                # Bitta manba topilsa ham davom etamiz (median uchun),
                # lekin 4+ manba yig'ilsa tezlik uchun to'xtash mumkin
                if len(candidates) >= 5:
                    break
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


def get_from_coinbase(coin):
    """
    Coinbase Spot Price API - USD only.
    NOTE: RUB Coinbase spot ATAYLAB ishlatilmaydi - u Coinbase o'z FX kursi
    bilan hisoblanadi va CBR kursidan 2-5% farq qiladi (inconsistent).
    RUB har doim USD * CBR dan hisoblanadi.
    https://api.coinbase.com/v2/prices/{coin}-USD/spot
    """
    try:
        base = _get_env("COINBASE_BASE_URL")
        url_usd = f"{base}/{coin}-USD/spot"
        response_usd = requests.get(url_usd, headers=HEADERS, timeout=8)

        if response_usd.status_code == 200:
            data_usd = response_usd.json()

            if "data" in data_usd and "amount" in data_usd["data"]:
                price_usd = float(data_usd["data"]["amount"])

                if _is_sane_usd(price_usd):
                    return {"usd": price_usd, "rub": None}, "Coinbase"

    except Exception as e:
        logger.debug(f"Coinbase error for {coin}: {e}")

    return None, None


def get_from_coinmarketcap(coin):
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

        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # Debug uchun ma'lumot
            logger.debug(f"CoinMarketCap response status: {response.status_code}")

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
                response = requests.get(url, headers=headers, params=params, timeout=8)

                if response.status_code == 200:
                    data = response.json()

                    if 'data' in data and coin in data['data']:
                        coin_data = data['data'][coin]

                        if isinstance(coin_data, list) and len(coin_data) > 0:
                            coin_info = coin_data[0]

                            if 'quote' in coin_info and 'USD' in coin_info['quote']:
                                price = coin_info['quote']['USD'].get('price')

                                if price is not None and _is_sane_usd(price):
                                    logger.info(f"✅ CoinMarketCap: {coin} narxi: ${price}")
                                    return float(price), "CoinMarketCap"

        elif response.status_code == 400:
            logger.debug(f"CoinMarketCap: Symbol {symbol} not found (400 error)")
        elif response.status_code == 401:
            logger.warning("CoinMarketCap: Invalid API key (401 error)")
        elif response.status_code == 429:
            logger.debug("CoinMarketCap: Rate limit exceeded (429 error)")
        elif response.status_code == 404:
            logger.debug(f"CoinMarketCap: {symbol} not found (404 error)")
        else:
            logger.debug(f"CoinMarketCap: Unexpected status code {response.status_code}")

    except requests.exceptions.Timeout:
        logger.debug(f"CoinMarketCap timeout for {coin}")
    except requests.exceptions.RequestException as e:
        logger.debug(f"CoinMarketCap request error for {coin}: {e}")
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


def get_from_binance(coin):
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
                response = requests.get(
                    url, params={"symbol": symbol}, headers=HEADERS, timeout=8
                )

                if response.status_code == 200:
                    data = response.json()
                    price = float(data.get("price", 0))
                    if _is_sane_usd(price):
                        return price, "Binance"
                elif response.status_code == 400:
                    continue  # invalid symbol - keyingi fallbackni urinish
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"Binance error for {coin}: {e}")

    return None, None


def get_from_bybit(coin):
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
                r = requests.get(
                    "https://api.bybit.com/v5/market/tickers",
                    params={"category": "spot", "symbol": symbol},
                    headers=HEADERS,
                    timeout=8,
                )
                if r.status_code == 200:
                    data = r.json()
                    lst = (data.get("result") or {}).get("list") or []
                    if lst:
                        price = float(lst[0].get("lastPrice", 0))
                        if _is_sane_usd(price):
                            return price, "Bybit"
                # 429 bo'lsa 1 marta kutib retry
                if r.status_code == 429:
                    import time as _t
                    _t.sleep(1.5)
                    continue
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Bybit error for {coin}: {e}")

    return None, None


def get_from_coingecko(coin):
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

    coin_id = COIN_IDS.get(coin, coin.lower())

    try:
        url = _get_env("COINGECKO_URL")

        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "false"
        }

        response = requests.get(url, params=params, headers=HEADERS, timeout=8)

        if response.status_code == 429:
            # Free tier rate limit - 2s kutib 1 marta retry
            import time as _t
            _t.sleep(2)
            response = requests.get(url, params=params, headers=HEADERS, timeout=8)

        if response.status_code == 200:
            data = response.json()

            if coin_id in data and "usd" in data[coin_id]:
                price = float(data[coin_id]["usd"])
                if _is_sane_usd(price):
                    return price, "CoinGecko"

    except Exception as e:
        logger.debug(f"CoinGecko error for {coin}: {e}")

    return None, None


def get_from_coingecko_search(coin):
    """
    CoinGecko /search API - HAR QANDAY token uchun universal resolver.
    Hardcoded COIN_IDS da bo'lmagan yangi/mem coinlar shu orqali topiladi.
    Natija 24 soat cache'lanadi (search rate-limit juda qattiq).
    Returns ({"usd":.., "name":..}, "CoinGecko") yoki (None, None).
    """
    symbol = coin.upper().strip().lstrip("$")
    if not symbol:
        return None, None

    now = datetime.now()
    cached = _gecko_search_cache.get(symbol)
    coin_id = None
    coin_name = None

    if cached and cached.get("updated") and (now - cached["updated"]) < GECKO_SEARCH_TTL:
        coin_id = cached["id"]
        coin_name = cached.get("name")
    else:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/search",
                params={"query": symbol},
                headers=HEADERS,
                timeout=8,
            )
            if r.status_code == 429:
                import time as _t
                _t.sleep(2)
                r = requests.get(
                    "https://api.coingecko.com/api/v3/search",
                    params={"query": symbol},
                    headers=HEADERS,
                    timeout=8,
                )
            if r.status_code != 200:
                return None, None
            data = r.json()
            coins = data.get("coins", []) or []

            # 1. Aniq symbol match (case-insensitive), eng yuqori market_cap_rank
            exact = [c for c in coins if str(c.get("symbol", "")).upper() == symbol]
            pool = exact or coins
            if not pool:
                return None, None

            def _rank(c):
                mr = c.get("market_cap_rank")
                return mr if isinstance(mr, int) and mr > 0 else 10_000_000

            best = sorted(pool, key=_rank)[0]
            coin_id = best.get("id")
            coin_name = best.get("name") or best.get("symbol")
            if not coin_id:
                return None, None
            _gecko_search_cache[symbol] = {"id": coin_id, "name": coin_name, "updated": now}
        except Exception as e:
            logger.debug(f"GeckoSearch error for {coin}: {e}")
            return None, None

    # 2. Topilgan id bo'yicha narx
    try:
        url = _get_env("COINGECKO_URL")
        r = requests.get(
            url,
            params={"ids": coin_id, "vs_currencies": "usd"},
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code == 429:
            import time as _t
            _t.sleep(2)
            r = requests.get(
                url,
                params={"ids": coin_id, "vs_currencies": "usd"},
                headers=HEADERS,
                timeout=8,
            )
        if r.status_code == 200:
            data = r.json()
            if coin_id in data and "usd" in data[coin_id]:
                price = float(data[coin_id]["usd"])
                if _is_sane_usd(price):
                    return {"usd": price, "name": coin_name}, "CoinGecko"
    except Exception as e:
        logger.debug(f"GeckoSearch price error for {coin} ({coin_id}): {e}")

    return None, None


def suggest_coins(query, limit=5):
    """Gecko search orqali o'xshash coinlar ro'yxati (topilmaganda taklif uchun)."""
    try:
        q = (query or "").upper().strip().lstrip("$")
        if not q:
            return []
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": q},
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return []
        out = []
        for c in (r.json().get("coins", []) or [])[:limit]:
            sym = str(c.get("symbol", "")).upper()
            name = c.get("name", "")
            if sym:
                out.append({"symbol": sym, "name": name})
        return out
    except Exception as e:
        logger.debug(f"suggest_coins error for {query}: {e}")
        return []


def get_from_dexscreener(coin):
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
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search",
            params={"q": symbol},
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return None, None
        pairs = (r.json().get("pairs", []) or [])
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


def _fetch_er_rate(ccy):
    """Secondary fiat source: open.er-api.com (free, no key). Returns rate or None."""
    try:
        url = DEFAULTS["ER_API_URL"]
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            rates = data.get("rates", {})
            rate = rates.get(ccy)
            if rate:
                # ER API gives UZS per USD directly
                return float(rate)
    except Exception as e:
        logger.debug(f"ER-API {ccy} error: {e}")
    return None


def get_uzs_rate():
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
        response = requests.get(url, headers=HEADERS, timeout=8)

        if response.status_code == 200:
            data = response.json()
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
    er = _fetch_er_rate("UZS")
    if er and 1000 < er < 100000:
        _rate_cache["uzs"] = {"rate": er, "updated": now, "source": "ER-API"}
        logger.info(f"✅ UZS kurs yangilandi (ER-API fallback): {er}")
        return er

    # 3. Stale cache / default
    if cache["updated"]:
        logger.warning(f"⚠️ UZS: stale kurs ishlatilmoqda: {cache['rate']} ({cache.get('source')})")
    return cache["rate"]


def get_rub_rate():
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
        response = requests.get(url, headers=HEADERS, timeout=8)

        if response.status_code == 200:
            data = response.json()

            if "Valute" in data and "USD" in data["Valute"]:
                rate = float(data["Valute"]["USD"]["Value"])

                if 10 < rate < 500:  # sanity: RUB plausible range
                    _rate_cache["rub"] = {"rate": rate, "updated": now, "source": "CBR"}
                    logger.info(f"✅ RUB kurs yangilandi (CBR): {rate}")
                    return rate

    except Exception as e:
        logger.warning(f"RUB CBR xato: {e}")

    # 2. ER-API secondary
    er = _fetch_er_rate("RUB")
    if er and 10 < er < 500:
        _rate_cache["rub"] = {"rate": er, "updated": now, "source": "ER-API"}
        logger.info(f"✅ RUB kurs yangilandi (ER-API fallback): {er}")
        return er

    if cache["updated"]:
        logger.warning(f"⚠️ RUB: stale kurs ishlatilmoqda: {cache['rate']} ({cache.get('source')})")
    return cache["rate"]


# TEST FUNCTION
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("="*60)
    print("🚀 CRYPTO PRICE CHECKER - MULTI-SOURCE MEDIAN")
    print("="*60)

    # Check if CoinMarketCap API key is available
    cmc_api_key = _get_env('COINMARKETCAP_API_KEY')
    if cmc_api_key:
        print(f"✅ CoinMarketCap API key found: {cmc_api_key[:10]}...")
    else:
        print("⚠️  CoinMarketCap API key not found - median without CMC")

    # Test coinlar
    test_coins = ["BTC", "ETH", "SOL", "TON", "DOGE", "NOT", "SHIB"]

    print(f"\n🔍 Testing {len(test_coins)} coins...\n")
    print("USD = median(Binance, Coinbase, CoinGecko[, CMC])")
    print("UZS = USD * CBU | RUB = USD * CBR")
    print()

    results = get_real_prices(test_coins)

    print("\n" + "="*60)
    print("📊 NATIJALAR:")
    print("="*60 + "\n")

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

    print("="*60)
