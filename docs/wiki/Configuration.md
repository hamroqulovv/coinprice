# Configuration

All settings live in `.env` (copy from `.env.example`). Nothing secret is hardcoded — the payment card number in the premium text is business info, change it in `main.py` if yours differs.

## Required

| Variable | Example | Meaning |
|---|---|---|
| `BOT_TOKEN` | `123456:ABC…` | Token from [@BotFather](https://t.me/BotFather) |
| `PRIMARY_ADMIN` | `123456789` | Owner's Telegram ID — sees the admin panel, receives payment screenshots |
| `ADMINS` | `123456789,987654321` | Extra admin IDs (comma-separated; currently only `PRIMARY_ADMIN` gates features) |

## Optional

| Variable | Default (built in) | Meaning |
|---|---|---|
| `CHANNELS` | — | Reserved for future channel features |
| `COINBASE_BASE_URL` | `https://api.coinbase.com/v2/prices` | Coinbase spot API root |
| `BINANCE_URL` | `https://api.binance.com/api/v3/ticker/price` | Binance spot ticker |
| `COINGECKO_URL` | `https://api.coingecko.com/api/v3/simple/price` | CoinGecko price endpoint |
| `UZS_RATE_URL` | CBU JSON endpoint | USD→UZS official rate |
| `RUB_RATE_URL` | CBR JSON endpoint | USD→RUB official rate |
| `COINMARKETCAP_API_KEY` | — | Enables CoinMarketCap as an extra source |
| `COINMARKETCAP_URL` | `…/v1/cryptocurrency/quotes/latest` | CMC endpoint (needs the key) |

Override a default only if you mirror the API or the official URL changes.

## Example

```ini
BOT_TOKEN=8811421563:AA…
PRIMARY_ADMIN=8992814642
ADMINS=8992814642
```
