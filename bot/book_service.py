from .data_manager import DataManager
from .config import CURRENT_BOOK_FILE, HISTORY_FILE
from datetime import datetime, date
from typing import Dict, List, Optional

class BookService:
    def __init__(self):
        self.current_file = CURRENT_BOOK_FILE
        self.history_file = HISTORY_FILE
        self.book: Dict = DataManager.load_or_create(self.current_file, {})
        self.history: List[Dict] = DataManager.load_or_create(self.history_file, [])

    def save_current(self):
        DataManager.save_json(self.current_file, self.book)

    def save_history(self):
        DataManager.save_json(self.history_file, self.history)

    def get_current(self) -> Dict:
        return self.book

    def set_book(self, title: str, author: str, total_pages: int, norm_pages: int):
        self.book = {
            "title": title,
            "author": author,
            "total_pages": total_pages,
            "norm_pages": norm_pages,
            "current_page": 0,
            "start_date": date.today().isoformat(),
            "last_update": None
        }
        self.save_current()

    def update_book(self, title: str, author: str, total_pages: int, norm_pages: int,
                    start_date: str, current_page: int = 0, last_update: Optional[str] = None):
        """Update the current book without resetting its reading progress."""
        if not self.book:
            return False
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            raise ValueError("Некорректная дата начала")
        if total_pages <= 0 or norm_pages <= 0:
            raise ValueError("Количество страниц и норма должны быть больше нуля")
        if current_page < 0 or current_page > total_pages:
            raise ValueError("Текущая страница должна быть от 0 до общего количества страниц")
        if last_update is not None:
            try:
                date.fromisoformat(last_update)
            except ValueError:
                raise ValueError("Некорректная дата последней отметки")

        self.book.update({
            "title": title,
            "author": author,
            "total_pages": total_pages,
            "norm_pages": norm_pages,
            "current_page": current_page,
            "start_date": start.isoformat(),
            "last_update": last_update,
        })
        self.save_current()
        return True

    def update_progress(self, user_id: int) -> bool:
        if not self.book:
            return False
        today = date.today().isoformat()
        if self.book.get("last_update") == today:
            return False
        norm = self.book.get("norm_pages", 0)
        self.book["current_page"] += norm
        if self.book["current_page"] > self.book["total_pages"]:
            self.book["current_page"] = self.book["total_pages"]
        self.book["last_update"] = today
        self.save_current()
        if self.book["current_page"] >= self.book["total_pages"]:
            self._finish_book()
        return True

    def _finish_book(self):
        if not self.book:
            return
        end_date = date.today().isoformat()
        start = datetime.fromisoformat(self.book["start_date"])
        end = datetime.fromisoformat(end_date)
        duration = (end - start).days
        record = {
            "title": self.book["title"],
            "author": self.book["author"],
            "start_date": self.book["start_date"],
            "end_date": end_date,
            "duration_days": duration,
            "readers": []
        }
        self.history.append(record)
        self.save_history()
        self.book = {}
        self.save_current()

    def get_progress_percent(self) -> int:
        if not self.book or self.book["total_pages"] == 0:
            return 0
        return int(self.book["current_page"] / self.book["total_pages"] * 100)

    def days_since_start(self) -> int:
        if not self.book or "start_date" not in self.book:
            return 0
        start = datetime.fromisoformat(self.book["start_date"])
        delta = datetime.now() - start
        return delta.days

    def estimated_finish_date(self) -> Optional[date]:
        if not self.book or self.book["norm_pages"] == 0:
            return None
        remaining = self.book["total_pages"] - self.book["current_page"]
        days_needed = (remaining + self.book["norm_pages"] - 1) // self.book["norm_pages"]
        from datetime import timedelta
        return date.today() + timedelta(days=days_needed)
