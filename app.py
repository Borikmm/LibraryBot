from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

# Функция для запуска вашего бота
def run_bot():
    # Импортируйте и запустите ваш основной файл с ботом
    from main import bot
    bot.run()

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    t = Thread(target=run_bot)
    t.start()
    # Запускаем веб-сервер, чтобы Render не уснул
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))