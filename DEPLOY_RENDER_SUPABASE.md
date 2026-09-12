# Deploy: Render (free) + Supabase Postgres (free) — $0

Bot needs two things Render free can't give alone: no-sleep compute and
persistent disk. So: **compute on Render, database on Supabase.**

## 1. Supabase — free Postgres (5 min)

1. [supabase.com](https://supabase.com) → New project (region **EU West** — closest to you and Render Frankfurt).
2. Project Settings → Database → **Connection string → Transaction pooler** (port `6543`, IPv4). Copy the URI:
   ```
   postgresql://postgres.[ref]:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres
   ```
3. Tables are created automatically on first bot start (`create_tables()`).
4. Free limits that matter: 500MB DB (ours is KBs), 7-day pause on inactivity (our bot writes every 10s, so never pauses while running), no auto-backups (see §5).

## 2. Render — free Web Service, Blueprint'SIZ (5 min, $0)

> Nega Blueprint emas? Blueprint faylining o'zi tekin (IaC yaml),
> lekin unda `plan:` yozilmasa Render default **Starter ($7/oy)** qo'yadi —
> shuning uchun "Blueprint pulli"dek ko'rinadi. Manual **New → Web Service
> → Instance Type: Free** esa 100% tekin, karta ham so'ramaydi.
> Hozir `render.yaml` da `plan: free` aniq yozilgan, xohlasangiz Blueprint
> bilan ham deploy qilsa bo'ladi — lekin quyidagi qo'lda yo'l tavsiya etiladi.

1. [dashboard.render.com](https://dashboard.render.com) → **New → Web Service** → shu repo'ni tanlang.
2. Sozlamalar (muhim — aynan shunday kiriting):
   - **Name:** `coinprice-bot` (xohlagan nom)
   - **Region:** `Frankfurt` (Supabase EU West ga eng yaqin)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** `Free` (512MB / 0.1 CPU, 750 soat/oy — 1 servis 24/7 ga yetadi)
   - **Health Check Path:** `/health`
3. **Environment Variables** (Advanced → Add):
   - `BOT_TOKEN` = @BotFather token
   - `PRIMARY_ADMIN` = sizning Telegram ID
   - `ADMINS` = qo'shimcha adminlar (bo'sh qoldirsa bo'ladi)
   - `DATABASE_URL` = 1-qadamdagi Supabase pooler URI (port `6543`)
   - `PYTHON_VERSION` = `3.11` (runtime.txt bilan bir xil)
4. **Create Web Service** → Deploy. Free = karta so'ramaydi.

## 3. Keep-alive — UptimeRobot (3 min, free)

Render sleeps free services after 15 min without inbound traffic. A polling bot gets no traffic, so:

1. [uptimerobot.com](https://uptimerobot.com) → Add Monitor → **HTTP(s)**.
2. URL: `https://coinprice-bot.onrender.com/health`, interval **5 minutes**.
3. That's it — the ping counts as traffic, the bot never sleeps.

## 4. Verify

- Render logs: `🤖 Bot started!` + `🏥 Health endpoint started`.
- Open `https://<your-app>.onrender.com/health` → `{"status": "ok"}`.
- Telegram: `/start` → type `BTC` → price arrives.

## 5. Backups (Supabase free has none)

`.github/workflows/backup-db.yml` runs `pg_dump` weekly and keeps it as a workflow artifact (90 days). Setup once:

1. Repo → Settings → Secrets → Actions → New secret: `DATABASE_URL` (use the **direct** connection string, port `5432`, not the pooler).
2. Done — check the Actions tab after the first Sunday run.

## 6. Limits & escape hatch

- If UptimeRobot misses pings for 15+ min, Render sleeps; next message wakes it in ~1 min.
- If the bot is down 7+ days, Supabase pauses → resume in 1 click in the dashboard.
- Outgrowing free? Render Starter (~$7/mo) removes sleep; Supabase Pro ($25/mo) adds backups. No code changes needed — same `DATABASE_URL` pattern.
