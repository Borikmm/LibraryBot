from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from .config import TOKEN
from .user_service import UserService
from .book_service import BookService
from .quote_service import QuoteService
from .stats_service import StatsService
from .scheduler import Scheduler
from .handlers import Handlers, TITLE, AUTHOR, TOTAL_PAGES, NORM
import logging

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
        self.app.add_handler(CallbackQueryHandler(self.handlers.button_callback))

        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("change_book", self.handlers.change_book_start)],
            states={
                TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_title)],
                AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_author)],
                TOTAL_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_total)],
                NORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_norm)],
            },
            fallbacks=[CommandHandler("cancel", self.handlers.cancel)]
        )
        self.app.add_handler(conv_handler)
        
        # Обработчик текстовых сообщений (только для отметки)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_text))


    def run(self):
        self.scheduler.start()
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
