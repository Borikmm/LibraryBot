import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", 0))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
QUOTES_FILE = os.path.join(DATA_DIR, "quotes.txt")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CURRENT_BOOK_FILE = os.path.join(DATA_DIR, "current_book.json")
HISTORY_FILE = os.path.join(DATA_DIR, "books_history.json")

MORNING_TIME = "06:00"
AFTERNOON_TIME = "13:00"
EVENING_TIME = "21:00"
