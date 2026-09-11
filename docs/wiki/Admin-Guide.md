# Admin Guide

Only `PRIMARY_ADMIN` (see [Configuration](Configuration.md)) sees the **👨‍💼 USERS Admin Panel** button.

## User list (paginated)

- Shows **10 users per page** with `◀️ Prev` / `Next ▶️` navigation and a `Users: N (sahifa x/y)` counter — safe for thousands of users.
- Each row shows 💎 (premium) or 👤 (regular), the name and total lookup count. Tapping a user opens their card: contact, username, ID, subscription type/expiry, last payment amount & rate, interval, lookups.

## Premium approvals

When a user sends a payment screenshot you receive a photo with their name, phone, plan length, amount and rate, plus two buttons:

- **✅ Tasdiqlash** — activates premium for the chosen days; the user gets `🎉 Premium faol!`
- **❌ Rad etish** — rejects; the user is told to retry or contact you.

You can also **🎁 Give Premium** (pick 1/2/3/12 months) or **🚫 Remove Premium** directly from any user card.

## Notes

- Approving/rejecting deletes the admin message to keep the chat clean.
- Non-admins tapping the panel button get no response (silent ignore).
- The card number and holder name shown to buyers are hardcoded in `main.py` (`premium_plans`) — update them there when they change.
