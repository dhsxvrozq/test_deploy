# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Подгружаем .env-файл, если он есть в корне проекта
dotenv_path = Path(__file__).parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

class ConfigError(Exception):
    pass

# --- Обязательные переменные ---
RUN_SERVER_CMD = os.getenv("RUN_SERVER_CMD")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN")
YOOTOKEN = os.getenv("YOOTOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
DSN_POSTGRES = os.getenv("DSN_POSTGRES")
PHOTO_TG_ID = os.getenv("PHOTO_TG_ID")

# --- Проверка обязательных переменных ---
def check_required():
    missing = []
    if not RUN_SERVER_CMD:
        missing.append("RUN_SERVER_CMD")
    if not TGBOT_TOKEN:
        missing.append("TGBOT_TOKEN")
    if not YOOTOKEN:
        missing.append("YOOTOKEN")
    if not PROVIDER_TOKEN:
        missing.append("PROVIDER_TOKEN")
    if not DSN_POSTGRES:
        missing.append("DSN_POSTGRES")
    if not PHOTO_TG_ID:
        missing.append("PHOTO_TG_ID")

    if missing:
        raise ConfigError(
            f"Обязательные переменные окружения не заданы: {', '.join(missing)}"
        )
