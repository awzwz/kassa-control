"""Настройки сервиса. Все значения берутся из переменных окружения (см. .env.example)."""
import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# Ключ для заголовка X-API-Key. Без него сервис отказывается стартовать.
API_KEY = os.environ.get("API_KEY", "")

# Куда складываем загруженные видео, базу задач и результаты.
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
DB_PATH = DATA_DIR / "jobs.sqlite"
UPLOAD_DIR = DATA_DIR / "uploads"

MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 200)

# Внутренний предел на одно видео. У жюри 300 с, себе оставляем запас на загрузку и очередь.
DEADLINE_SEC = _int("DEADLINE_SEC", 240)

# Сколько хранить результаты (видео удаляется сразу после обработки).
RESULT_TTL_HOURS = _int("RESULT_TTL_HOURS", 24)

# Как часто обработчик заглядывает в очередь.
WORKER_POLL_SEC = float(os.environ.get("WORKER_POLL_SEC", "0.5"))

PIPELINE_VERSION = "0.1-stub"
