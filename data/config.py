import os
from dotenv import load_dotenv

load_dotenv()


def _required_int(name: str) -> int:
    val = (os.getenv(name) or "").strip()
    if not val:
        raise RuntimeError(f"{name} missing in .env - botni ishga tushirib bo'lmaydi")
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer Telegram ID, got: {val!r}")


def _optional_int_list(name: str) -> list:
    val = (os.getenv(name) or "").strip()
    if not val:
        return []
    ids = []
    for part in val.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            raise RuntimeError(f"{name} must be comma-separated integers, bad part: {part!r}")
    return ids


BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN or " " in BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing or invalid in .env - @BotFather dan oling")

PRIMARY_ADMIN = _required_int("PRIMARY_ADMIN")

# Qo'shimcha adminlar (is_admin() da PRIMARY_ADMIN bilan birga tekshiriladi)
ADMINS = _optional_int_list("ADMINS")

# Hozircha ishlatilmaydi (reserved for future channel features)
CHANNELS = [c.strip() for c in (os.getenv("CHANNELS") or "").split(",") if c.strip()]
