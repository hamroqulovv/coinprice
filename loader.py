from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from data import config

if config.DATABASE_URL:
    from utils.db_api.postgres import PostgresDatabase

    db = PostgresDatabase(config.DATABASE_URL)
else:
    from utils.db_api.sqlite import Database

    db = Database(path_to_db=str(Path(__file__).resolve().parent / "main.db"))


bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
# NOTE: FSM MemoryStorage - restart'da state'lar yo'qoladi (by design).
# NOTE: absolute DB path - CWD'dan qat'iy nazar DB har doim loyiha root'da.