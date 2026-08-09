from .book_service import BookService
from .user_service import UserService

class StatsService:
    def __init__(self, book_service: BookService, user_service: UserService):
        self.book = book_service
        self.users = user_service

    def get_stats_text(self) -> str:
        book = self.book.get_current()
        if not book:
            return "Книга не выбрана. Обратитесь к администратору."
        total_pages = book["total_pages"]
        current_page = book["current_page"]
        norm = book["norm_pages"]
        progress = self.book.get_progress_percent()
        days = self.book.days_since_start()
        finish = self.book.estimated_finish_date()
        lines = [
            f"📚 Текущая книга: {book.get('title')} ({book.get('author')})",
            f"📄 Страниц всего: {total_pages}",
            f"📖 Прочитано: {current_page} ({progress}%)",
            f"📅 Норма в день: {norm} стр.",
            f"⏳ Читаем уже {days} дн.",
        ]
        if finish:
            lines.append(f"📆 Плановое окончание: {finish.strftime('%d.%m.%Y')}")

        all_users = self.users.get_all_users()
        if all_users:
            lines.append("\n👥 Активность читателей:")
            for uid, data in all_users.items():
                username = data.get("username", uid)
                books = data.get("books_read", 0)
                max_streak = data.get("max_streak", 0)
                lines.append(f"  - {username}: прочитано книг – {books}, рекорд беспрерывного чтения – {max_streak} дн.")
        else:
            lines.append("\nНет зарегистрированных пользователей.")

        history = self.book.history
        if history:
            lines.append(f"\n📚 Всего прочитано книг: {len(history)}")
            for i, h in enumerate(history[-5:], 1):
                lines.append(f"  {i}. {h['title']} – {h['duration_days']} дн.")
        else:
            lines.append("\nИстория книг пуста.")
        return "\n".join(lines)