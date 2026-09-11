# Crypto Price News Bot (Crypto Bot)

**📌 Qisqacha:**
Crypto Bot — Telegram bot bo'lib, foydalanuvchilarga kripto-valyuta kurslari va yangiliklar asosida avtomatik xabardor qilish xizmatini taqdim etadi. Loyihada foydalanuvchi boshqaruvi, premium obuna, avtomatik kuzatuvlar va admin panel mavjud.

---

## 🎯 Xususiyatlar
- Real vaqt narxlarni so'rash (USD / RUB / UZS)
- Avtomatik xabardorliklar (interval asosida)
- Foydalanuvchi ro'yxatdan o'tkazish (telefon), profil va tahrirlash
- Premium obuna va admin tomonidan tasdiqlash tizimi
- Foydalanuvchi uchun kunlik limitlar (bepul: 5 ta ko'rish)
- Admin panel: foydalanuvchilar ro'yxati, premium berish/olib tashlash, foydalanuvchi ma'lumotlari
- Docker bilan joylashtirish uchun tayyor

---

## 🧭 Texnologiyalar
- Python 3.11
- aiogram (Telegram bot framework)
- SQLite (mahalliy DB) — `main.db`
- apscheduler (jadval vazifalari)
- Docker / docker-compose (joylashtirish)

---

## ⚙️ Talablar
- Python 3.11+
- Git
- (Joylashtirish uchun) Docker & docker-compose yoki systemd

---

## 🚀 Mahalliy ishga tushirish (development)
1. Klonlash:
```bash
git clone <repo-url>
cd crypto_bot
```

2. Virtual muhit yaratish va o'rnatish:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Konfiguratsiya:
```bash
cp .env.example .env
# .env faylini tahrirlab: BOT_TOKEN, PRIMARY_ADMIN, ADMINS -> toʻldiring
```

4. DB yaratish (dastlabki ishga tushirish `main.py` ichida `db.create_tables()` chaqiradi):
```bash
python main.py
```
Bot loglarda ishlayotgani haqida xabar ko'rasiz.

---

## 🐳 Docker bilan joylashtirish (recommended)
1. Docker image yaratish:
```bash
docker build -t crypto-bot:latest .
```

2. Docker-compose bilan ishga tushirish:
```bash
docker compose up -d --build
```

3. Yoki to'g'ridan-to'g'ri run:
```bash
docker run -d --name crypto-bot --env-file .env -v "$(pwd)/main.db:/app/main.db" -v "$(pwd)/data:/app/data" --restart unless-stopped crypto-bot:latest
```

4. Loglarni tekshirish:
```bash
docker compose logs -f
# yoki
docker logs -f crypto-bot
```

🔔 Eslatma: SQLite `main.db` faylini hostga mount qilish orqali saqlang (yuqoridagi `-v` bandi bilan).

---

## 🔧 Muhim environment o'zgaruvchilari (`.env`)
- `BOT_TOKEN` — Telegram bot token (obligator)
- `PRIMARY_ADMIN` — asosiy adminning Telegram IDsi (integer)
- `ADMINS` — qo'shimcha adminlar (vergul bilan ajratilgan IDlar)
- `CHANNELS` — ixtiyoriy, kanal ro'yxati (vergul bilan)

Masalan `.env`:
```
BOT_TOKEN="<token>"
PRIMARY_ADMIN="123456789"
ADMINS="123456789,987654321"
CHANNELS="" 
```

---

## 🧾 Ma'lumotlar bazasi
- Foydalanuvchi va preferensiyalar SQLite `main.db` ichida saqlanadi.
- Agar siz bulutda (Heroku, Cloud Run) joylashtirsangiz, SQLite ephemeraldir — tashqi DB (Postgres) ishlatish tavsiya etiladi.

---

## 🧪 Test & Kod sifati
- Unit testlar `tests/` papkasida (`pytest`): `format_price`, `calculate_price_change`, narx keshi.
- Testlarni ishga tushirish:
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
- Har bir push/PR da testlar avtomatik ishlaydi (`.github/workflows/tests.yml`).
- Kod formatlash: `black` va `flake8` tavsiya etiladi.

---

## 🛠️ Admin funksiyalari
- `👨‍💼 USERS Admin Panel` orqali barcha foydalanuvchilarni ko'rish
- Har bir foydalanuvchi uchun profiling, premium berish/olib tashlash, so'rovlar hisobini ko'rish
- Premium to'lovlarni admin tasdiqlaydi (`accept_...` callback) — bu yerda muddati, plan va yuborilgan sana saqlanadi

---

## 📦 Deploy Qo'llanma (qisqacha)
- `.env` ni to'ldiring.
- Docker orqali container ishga tushiring (`docker compose up -d --build`).
- Systemd yordamida xizmat sifatida ishga tushirish uchun `deploy/crypto-bot.service` namunasi keltirilgan.
- Zaxira (`main.db`) ni hostga nusxalab qo'yishni tashkil qiling.

---

## 🤝 Hissa qo'shish (Contributing)
1. Fork qiling va yangi branch oching (`feature/my-feature`).
2. O'zgarishlarni qiling va test yozing.
3. Pull request yuboring — qisqacha izoh va changelog kiriting.

---

## ⚠️ Xavfsizlik va maxfiylik
- Hech qachon `BOT_TOKEN` yoki API kalitlarini ommaga oshkor qilmang.
- Xavfsizlik muammolari yoki xatoliklar yuz bersa, issues orqali murojaat qiling.

---

## 📄 Litsenziya
- Loyiha uchun standart MIT litsenziyasini tavsiya qilaman — agar hohlasangiz, `LICENSE` faylini qo'shib beraman.

---

## 📬 Kontakt
- Muallif: Loyihaning GitHub sahifasida ko'rsatilgan kontaktlar orqali bog'laning.

---

Oʻzgartirishlar yoki qoʻshimchalar kiritishni xohlaysizmi? README ni loyihangizga moslab yanada kengaytirib beraman (misol: kod bo'limlari, API hujjatlari yoki screenshotlar).