# FAQ

**The bot says "not found" for my coin.**
Check the exact ticker spelling (letters + digits, e.g. `1INCH` not `1-INCH`). The bot suggests similar symbols — if yours is genuinely unlisted everywhere supported, it can't be priced. Verify on [coingecko.com](https://www.coingecko.com).

**"Free limit (5) reached" but I barely used it?**
The counter resets daily. Premium removes it entirely.

**I restarted the bot and everyone got spammed.**
That was fixed: last notified prices live in the DB (`CryptoPreferences.last_price`), so restarts are silent. If you see it on an old version, update.

**Prices differ slightly from my exchange app.**
The bot shows the **median across exchanges**, not one venue's price — small differences are expected and intentional.

**TON shows a weird price.**
A stale third-party listing once quoted TON ~17% off; the outlier filter now drops it automatically.

**Bot doesn't respond at all.**
1. Is the process running? Look for `🤖 Bot started!` in logs.
2. Only **one** instance can poll Telegram — a second copy (local + server) silently starves.
3. Check `BOT_TOKEN` in `.env`.

**`int(None)` / crash on startup?**
`BOT_TOKEN`, `PRIMARY_ADMIN` and `ADMINS` must all be set in `.env` — there are no defaults for those three.

**How do I change the payment card number?**
It's in `main.py`, function `premium_plans` — update the number and holder name there.

**Where is my data?**
One file: `main.db` next to `main.py`. Back it up regularly (see [Deployment](Deployment.md)).
