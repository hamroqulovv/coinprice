# Admin Guide

Only `PRIMARY_ADMIN` + `ADMINS` (see [Configuration](Configuration.md)) see the **👨‍💼 USERS Admin Panel** button. Extra entry: `/admin` command (works even with a stale keyboard).

## Stats

The panel shows **👥 Userlar**, **📩 Bugungi so'rovlar** (today), **📩 Oylik so'rovlar** (this month) and **📩 Jami so'rovlar** (lifetime). Counters update on every coin lookup ([Database](Database.md): `view_count` / `daily_views`+`last_view_date` / `month_views`+`last_view_month`).

## Users (paginated)

- **👥 Userlar** button: **10 users per page** with `◀️ Prev` / `Next ▶️` navigation — safe for thousands of users.
- Each row shows the name and lifetime lookup count. Tapping a user opens their card: contact, username, ID, interval, lookups (jami / oy / bugun), watchlist size.
- Card actions: **❌ O'chirish** (two-tap confirm, also removes watchlist entries), **🔙 Orqaga**.

## Notes

- Non-admins get a `⛔ Bu bo'lim faqat adminlar uchun.` reply instead of silence — every tap is answered, check `bot.log` (`Admin panel denied for user ...`) if access looks wrong.
- If the button does nothing at all: make sure only ONE bot instance polls the token (local + hosting together steal each other's updates) and `PRIMARY_ADMIN` matches your Telegram ID.
