from .data_manager import DataManager
from .config import USERS_FILE
from typing import Dict, Optional
from datetime import date

class UserService:
    def __init__(self):
        self.file = USERS_FILE
        self.users: Dict[str, dict] = DataManager.load_or_create(self.file, {})

    def save(self):
        DataManager.save_json(self.file, self.users)

    def get_user(self, user_id: int) -> Optional[dict]:
        uid = str(user_id)
        return self.users.get(uid)

    def add_user(self, user_id: int, username: str = None, role: str = "reader") -> dict:
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "role": role,
                "books_read": 0,
                "username": username,
                "streak": 0,
                "max_streak": 0,
                "last_mark_date": None
            }
            self.save()
        else:
            if username and self.users[uid].get("username") != username:
                self.users[uid]["username"] = username
                self.save()
        return self.users[uid]

    def set_role(self, user_id: int, role: str):
        uid = str(user_id)
        if uid in self.users:
            self.users[uid]["role"] = role
            self.save()

    def increment_books_read(self, user_id: int):
        uid = str(user_id)
        if uid in self.users:
            self.users[uid]["books_read"] += 1
            self.save()

    def get_all_users(self) -> Dict[str, dict]:
        return self.users

    def is_admin(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return user and user.get("role") == "admin"

    def mark_read(self, user_id: int) -> None:
        uid = str(user_id)
        if uid not in self.users:
            return
        today = date.today().isoformat()
        user = self.users[uid]
        last = user.get("last_mark_date")
        if last == today:
            return
        yesterday = date.today().replace(day=date.today().day-1).isoformat()
        if last == yesterday:
            user["streak"] += 1
        else:
            user["streak"] = 1
        user["last_mark_date"] = today
        if user["streak"] > user["max_streak"]:
            user["max_streak"] = user["streak"]
        self.save()