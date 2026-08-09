from flask import Flask
from threading import Thread
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    """Запуск бота в отдельном потоке"""
    try:
        from bot.bot import LibraryBot
        bot = LibraryBot()
        logger.info("Бот запускается...")
        bot.run()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Поток бота запущен")
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
