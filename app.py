from flask import Flask
from threading import Thread
import os
import logging
import asyncio

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
    try:
        from bot.bot import LibraryBot
        bot = LibraryBot()
        logger.info("Бот запускается...")
        
        # Создаём новый цикл событий и устанавливаем его для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Запускаем бота (он будет использовать этот цикл)
        bot.run()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Поток бота запущен")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
