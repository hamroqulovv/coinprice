# Getting Started

Run the bot locally in about 5 minutes.

## Requirements

- Python **3.11+**
- Git
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your own Telegram numeric ID (to become admin) — get it from [@userinfobot](https://t.me/userinfobot)

## Steps

```bash
git clone https://github.com/hamroqulovv/coinprice.git
cd coinprice

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # then fill it in (see below)
python main.py
```

You should see:

```
🤖 Bot started!
🚀 Smart price notification system started!
Run polling for bot @YourBot ...
```

Open your bot in Telegram, press **Start**, share your phone number — done. 🎉

## Minimal `.env`

Only three values are truly mandatory to start chatting:

```ini
BOT_TOKEN=123456:ABC-your-token
PRIMARY_ADMIN=123456789
ADMINS=123456789
```

> Price-API URLs all have built-in defaults — the bot works without setting them. See [Configuration](Configuration.md) for the full table.

## Next

- [Configuration](Configuration.md) — every variable explained
- [Deployment](Deployment.md) — run it 24/7 with Docker or systemd
