# Configuration

All settings live in `.env` (copy from `.env.example`). Nothing secret is hardcoded.

## Required

| Variable | Example | Meaning |
|---|---|---|
| `BOT_TOKEN` | `123456:ABC…` | Token from [@BotFather](https://t.me/BotFather) |
| `PRIMARY_ADMIN` | `123456789` | Owner's Telegram ID — full admin access |
| `ADMINS` | `123456789,987654321` | Extra admin IDs (comma-separated, no spaces) — same admin panel access |

## Optional

| Variable | Default (built in) | Meaning |
|---|---|---|
| `CHANNELS` | — | Reserved for future channel features |
| `COINBASE_BASE_URL` | `https://api.coinbase.com/v2/prices` | Coinbase spot API root |
| `BINANCE_URL` | `https://api.binance.com/api/v3/ticker/price` | Binance spot ticker |
| `COINGECKO_URL` | `https://api.coingecko.com/api/v3/simple/price` | CoinGecko price endpoint |
| `UZS_RATE_URL` | `https://cbu.uz/uz/arkhiv-kursov-valyut/json/` | USD→UZS official rate (CBU) |
| `RUB_RATE_URL` | `https://www.cbr-xml-daily.ru/daily_json.js` | USD→RUB official rate (CBR) |
| `ER_API_URL` | `https://open.er-api.com/v6/latest/USD` | Fallback fiat source when CBU/CBR fail |
| `COINMARKETCAP_API_KEY` | — | Enables CoinMarketCap as an extra source |
| `COINGECKO_API_KEY` | — | Free demo key (coingecko.com): higher rate limits, fewer throttled low-cap lookups |
| `COINMARKETCAP_URL` | `…/v1/cryptocurrency/quotes/latest` | CMC endpoint (needs the key) |

Override a default only if you mirror the API or the official URL changes.

## Example

```ini
BOT_TOKEN=123456:ABC-your-token-here
PRIMARY_ADMIN=123456789
ADMINS=123456789
```
