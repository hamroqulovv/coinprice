# How Prices Work

## The short version

Each coin is fetched from **several exchanges at once** and the **median** price wins. One glitching exchange can never show you a wrong number.

## Source chain (per coin)

```
Binance · Bybit · Coinbase · CoinGecko · DexScreener · (+ CoinMarketCap if you set an API key)
```

- All reachable sources are queried **in parallel** (`asyncio.gather`).
- **Trust tiers:** aggregated venues (CoinGecko/Coinbase/CMC) outrank single-exchange USDT quotes (a stale listing like Binance's TON pair is dropped automatically); unverified DEX listings count **only** when nothing else answers.
- The median of the trusted set is the price; anything further than **3%** off is discarded.
- Popular tickers (BTC, ETH, …) use a hardcoded CoinGecko-id fast path — no extra network call, no added latency.

## Unknown / small-cap tickers

If a ticker isn't in the built-in list, the bot resolves it live via CoinGecko `/search`:

1. Exact symbol match (case-insensitive).
2. If several projects share the ticker, the one with the best (lowest) `market_cap_rank` wins.
3. Result cached **permanently**; confirmed "doesn't exist" cached for **1 hour** (network errors are never cached, so transients are retried).
4. DexScreener covers DEX-only memecoins that aren't on any central exchange.

If nothing anywhere knows the ticker, the user gets a clear "not found" message with similar-symbol suggestions.

## The three currencies

- **USD** — the median market price described above.
- **UZS** — USD × official rate from Uzbekistan's Central Bank (CBU), fallback: open.er-api.com.
- **RUB** — USD × official rate from Russia's Central Bank (CBR), fallback: open.er-api.com.

> Fiat rates change once a day, so they are cached for **10 minutes**. Crypto prices are cached for **15 seconds** so every user in one scheduler tick sees the same number.

## Rate limits

- Coin-level parallelism is capped (semaphore of 5); CoinGecko free `/search` is additionally throttled by the cache.
- A burst of many *brand-new* tickers in a row can still hit CoinGecko limits — the bot retries once, then skips that source for the tick instead of failing the lookup.
