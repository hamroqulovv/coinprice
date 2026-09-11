Deployment guide (no code changes required)

Overview
--------
This document explains how to deploy the bot without modifying the project source. Options covered:
- Docker + docker-compose (recommended)
- Systemd service (for a Linux VM)
- Heroku / Cloud Run notes (stateless - SQLite caveat)

Prerequisites
-------------
- Create a copy of `.env.example` as `.env` and fill values: `BOT_TOKEN`, `PRIMARY_ADMIN`, `ADMINS`, optional `CHANNELS`.
- If using the Docker approach, install Docker and docker-compose.

Docker (recommended)
--------------------
1. Build the image:
   docker build -t crypto-bot:latest .

2. Run with env file (starts bot). `main.db` must exist as a FILE first
   (`touch main.db`) — otherwise Docker creates a directory with that name
   and SQLite fails to open:
   docker run -d --name crypto-bot --env-file .env -v "$(pwd)/main.db:/app/main.db" -v "$(pwd)/data:/app/data" --restart unless-stopped crypto-bot:latest

3. Or use docker compose (recommended):
   touch main.db
   docker compose up -d --build

Notes:
- SQLite database `main.db` is kept on the host at the project root; the container mounts it into `/app/main.db` so data persists.
- The bot runs in polling mode by default. If you want to use webhooks, set up a reverse proxy and expose a port (requires code adjustments for webhooks).

Systemd (VM deployment)
------------------------
1. Copy project to `/opt/crypto-bot` and create a virtualenv there. Ensure dependencies are installed.
2. Create the systemd service file `/etc/systemd/system/crypto-bot.service` with content from `deploy/crypto-bot.service` in this repo (copy and adjust EnvFile path if needed).
3. Start and enable:
   sudo systemctl daemon-reload
   sudo systemctl enable --now crypto-bot.service

Heroku / Cloud Run notes
-------------------------
- Heroku ephemeral filesystem will not persist the SQLite DB between dyno restarts. For production, prefer Docker on a VM or use an external database (Postgres) and update the code to use it.
- If you still want to try Heroku, set `BOT_TOKEN` and other envs in the dashboard and add the project by pushing to Heroku Git remote. Use the `Procfile` included.

Healthchecks & Logging
----------------------
- The bot logs to stdout; use Docker logs or systemd journal to monitor.

Backups
-------
- Periodically back up `main.db` from the host system or use a cron job to copy it to a safe location.

