from .config import QUOTES_FILE
import random


class QuoteService:
    def __init__(self):
        self.quotes: list[str] = []
        self._load()

    def _load(self):
        try:
            with open(QUOTES_FILE, encoding="utf-8") as f:
                self.quotes = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.quotes = ["Мотивационная цитата не найдена."]

    def get_random(self) -> str:
        if not self.quotes:
            return "Цитат пока нет."
        return random.choice(self.quotes)
