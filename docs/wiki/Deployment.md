# Deployment

## Docker (recommended)

```bash
docker build -t crypto-bot:latest .
docker compose up -d --build
docker compose logs -f
```

- The bot uses **polling** — no ports need exposing, only outbound HTTPS.
- `main.db` and `data/` are bind-mounted from the host so the database survives restarts.
- `restart: unless-stopped` keeps it alive across reboots.

## Systemd (plain VM)

```bash
# copy the project to /opt/crypto-bot, create venv + .env there
sudo cp deploy/crypto-bot.service /etc/systemd/system/crypto-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-bot.service
sudo systemctl status crypto-bot
journalctl -u crypto-bot -f
```

Needs Python 3.11+ at `/usr/bin/python3` on Ubuntu 20.04+.

## Heroku / Cloud Run (not recommended)

A `Procfile` (`worker: python main.py`) exists, but SQLite is **ephemeral** there — `main.db` is wiped on every restart/redeploy. Use an external database (requires code changes) if you go this route.

## Backups

The whole state is one file — back it up with cron:

```cron
0 3 * * * cp /opt/crypto-bot/main.db /backups/main.db_$(date +\%F)
```

## Health check

There is no HTTP endpoint (polling bot). "Healthy" = recent log lines:

```bash
docker logs -f crypto-bot          # Docker
journalctl -u crypto-bot -f        # systemd
```

Look for `🤖 Bot started!` after each (re)start.
