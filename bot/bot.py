from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from .config import TOKEN
from .user_service import UserService
from .book_service import BookService
from .quote_service import QuoteService
from .stats_service import StatsService
from .scheduler import Scheduler
from .handlers import Handlers
import logging
import asyncio

logging.basicConfig(level=logging.INFO)

class LibraryBot:
    def __init__(self):
        self.app = Application.builder().token(TOKEN).build()
        self.user_svc = UserService()
        self.book_svc = BookService()
        self.quote_svc = QuoteService()
        self.stats_svc = StatsService(self.book_svc, self.user_svc)
        self.handlers = Handlers(self.user_svc, self.book_svc, self.stats_svc)
        self.scheduler = Scheduler(self.app, self.quote_svc)
        self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.handlers.start_command))
        self.app.add_handler(CommandHandler("cancel", self.handlers.cancel))
        self.app.add_handler(CallbackQueryHandler(self.handlers.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_text))

    async def run_async(self):
        """Асинхронный запуск бота"""
        self.scheduler.start()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        await self.app.updater.idle()

    def run(self):
        """Синхронный запуск (для локального тестирования)"""
        asyncio.run(self.run_async())
