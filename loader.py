from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from data import config
from utils.db_api.sqlite import Database


bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
# Absolute path: CWD'dan qat'iy nazar DB har doim loyiha root'da.
# NOTE: FSM MemoryStorage - restart'da state'lar yo'qoladi (by design).
db = Database(path_to_db=str(Path(__file__).resolve().parent / "main.db"))