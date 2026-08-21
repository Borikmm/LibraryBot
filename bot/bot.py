
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import TOKEN
from .user_service import UserService
from .book_service import BookService
from .quote_service import QuoteService
from .stats_service import StatsService
from .scheduler import Scheduler
from .handlers import (
    Handlers, TITLE, AUTHOR, TOTAL_PAGES, NORM,
    EDIT_TITLE, EDIT_AUTHOR, EDIT_TOTAL_PAGES, EDIT_NORM, EDIT_START_DATE, EDIT_CURRENT_PAGE,
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

class LibraryBot:
    def __init__(self):
        self.app = (
            Application.builder()
            .token(TOKEN)
            # .post_init(self._post_init)
            # .post_shutdown(self._post_shutdown)
            .build()
        )
        self.user_svc = UserService()
        self.book_svc = BookService()
        self.quote_svc = QuoteService()
        self.stats_svc = StatsService(self.book_svc, self.user_svc)
        self.handlers = Handlers(self.user_svc, self.book_svc, self.stats_svc)
        self.scheduler = Scheduler(self.app, self.quote_svc)
        self._register_handlers()

    async def _post_init(self, application):
        logger.info("Запускаем планировщик...")
        self.scheduler.start()

    async def _post_shutdown(self, application):
        logger.info("Останавливаем планировщик...")
        self.scheduler.stop()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.handlers.start_command))

        # ConversationHandler должен стоять раньше общего CallbackQueryHandler,
        # чтобы callback-кнопки change_book/edit_book могли запустить диалог.
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("change_book", self.handlers.change_book_start),
                CallbackQueryHandler(
                    self.handlers.button_callback,
                    pattern="^(change_book|edit_book)$",
                )
            ],
            states={
                TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_title)],
                AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_author)],
                TOTAL_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_total)],
                NORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.change_book_norm)],
                EDIT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_title)],
                EDIT_AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_author)],
                EDIT_TOTAL_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_total)],
                EDIT_NORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_norm)],
                EDIT_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_start_date)],
                EDIT_CURRENT_PAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.edit_book_current_page)],
            },
            fallbacks=[CommandHandler("cancel", self.handlers.cancel)],
            allow_reentry=True,
        )
        self.app.add_handler(conv_handler)

        # Остальные callback-кнопки (в частности статистика).
        self.app.add_handler(CallbackQueryHandler(self.handlers.button_callback))

        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_text)
        )

    def run(self):
        logger.info("Бот запускается...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
