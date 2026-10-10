from bot.bot import LibraryBot
import os
from pathlib import Path
from telegram.error import TelegramError


def main():
    pid = os.getenv("LOCAL_PID_FILE")
    if pid:
        Path(pid).write_text(str(os.getpid()), encoding="ascii")
    try:
        try:
            LibraryBot().run()
        except TelegramError as exc:
            raise RuntimeError(
                f"Telegram не удалось запустить ({type(exc).__name__}). Проверь токен и соединение."
            ) from None
    finally:
        if pid and Path(pid).exists() and Path(pid).read_text(encoding="ascii") == str(os.getpid()):
            Path(pid).unlink()


if __name__ == "__main__":
    main()
