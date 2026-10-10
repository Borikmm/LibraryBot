import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import Settings
from .health import HealthServer
from .logging_config import configure_logging
from .navigation import Controller
from .quote_service import QuoteService
from .scheduler import Scheduler
from .service import Service
from .storage import Store


class LibraryBot:
    def __init__(self, settings=None):
        configure_logging()
        self.settings = settings or Settings.load()
        self.store = Store(self.settings.database_url)
        self.store.migrate()
        self.leader = psycopg.connect(self.settings.database_url, autocommit=True)
        if not self.leader.execute("SELECT pg_try_advisory_lock(76365002)").fetchone()[0]:
            self.leader.close()
            self.store.close()
            raise RuntimeError("Для этой базы уже запущен экземпляр LibraryBot.")
        self.service = Service(self.store)
        self.quotes = QuoteService()
        self.controller = Controller(self.store, self.service, self.settings, self.quotes)
        self.scheduler = Scheduler(self.store, self.quotes)
        self.app = (
            Application.builder()
            .token(self.settings.token)
            .concurrent_updates(False)
            .post_init(self.post_init)
            .post_shutdown(self.post_shutdown)
            .build()
        )
        c = self.controller
        for name, handler in (
            ("start", c.start),
            ("menu", c.start),
            ("read", c.read_command),
            ("export", c.export_command),
            ("cancel", c.cancel),
        ):
            self.app.add_handler(CommandHandler(name, handler))
        self.app.add_handler(CallbackQueryHandler(c.callback))
        self.app.add_handler(MessageHandler(filters.Document.ALL, c.document))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, c.text))
        self.app.add_handler(ChatMemberHandler(c.member_changed, ChatMemberHandler.ANY_CHAT_MEMBER))
        self.app.add_error_handler(c.error)
        self.health = HealthServer(self.settings.health_host, self.settings.port, self.ready)

    def ready(self):
        with self.store.pool.connection() as conn:
            conn.execute("SELECT 1")
        return bool(
            self.app.running
            and self.app.updater.running
            and self.scheduler.last_tick
            and datetime.now(UTC) - self.scheduler.last_tick < timedelta(minutes=2)
        )

    async def post_init(self, app):
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Главное меню"),
                BotCommand("read", "Отметить чтение в ЛС"),
                BotCommand("export", "Экспорт личного профиля"),
                BotCommand("cancel", "Отменить ввод"),
            ]
        )
        await asyncio.to_thread(self.recover_deliveries)
        app.job_queue.run_repeating(
            self.scheduler.tick,
            interval=30,
            first=1,
            name="personal-schedules",
            job_kwargs={"max_instances": 1},
        )

    def recover_deliveries(self):
        with self.store.pool.connection() as conn:
            conn.execute("UPDATE deliveries SET status='uncertain' WHERE status='sending'")

    async def post_shutdown(self, app):
        await asyncio.to_thread(self.health.close)
        self.leader.close()
        self.store.close()

    def run(self):
        self.health.start()
        try:
            self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
        finally:
            if not self.leader.closed:
                self.leader.close()
                self.store.close()
