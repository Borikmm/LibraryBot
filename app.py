import os
import threading
import logging

from flask import Flask


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 LibraryBot is running!", 200


@app.route("/health")
def health():
    return "OK", 200


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))

    logger.info(
        "Запускаем Flask на порту %s",
        port,
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


def main():
    # Flask работает в отдельном потоке.
    # Telegram bot остаётся в главном потоке,
    # где python-telegram-bot сможет нормально
    # работать с asyncio event loop.
    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True,
        name="flask-server",
    )

    web_thread.start()

    logger.info("Flask health server запущен")

    from bot.bot import LibraryBot

    bot = LibraryBot()

    logger.info("Бот запускается...")

    # ВАЖНО:
    # Telegram bot запускается в ГЛАВНОМ потоке.
    bot.run()


if __name__ == "__main__":
    main()
