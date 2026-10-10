import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .domain import validate_timezone

BASE_DIR = Path(__file__).resolve().parent.parent
QUOTES_FILE = BASE_DIR / "scripts" / "data" / "quotes.txt"


@dataclass(frozen=True)
class Settings:
    token: str
    database_url: str
    timezone: str = "Asia/Chita"
    health_host: str = "127.0.0.1"
    port: int = 10000

    @classmethod
    def load(cls):
        load_dotenv(BASE_DIR / ".env")
        if not os.getenv("DATABASE_URL"):
            load_dotenv(BASE_DIR / ".local" / "db.env")
        token, dsn = os.getenv("BOT_TOKEN"), os.getenv("DATABASE_URL")
        if not token:
            raise RuntimeError("Укажи BOT_TOKEN в локальном .env или переменных окружения сервера.")
        if not dsn or not dsn.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("Укажи DATABASE_URL для PostgreSQL.")
        timezone = validate_timezone(os.getenv("BOT_TIMEZONE", "Asia/Chita"))
        return cls(
            token,
            dsn,
            timezone,
            os.getenv("HEALTH_HOST", "127.0.0.1"),
            int(os.getenv("PORT", "10000")),
        )
