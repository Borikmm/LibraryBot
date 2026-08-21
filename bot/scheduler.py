from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date

from . import config
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot_app, quote_service, user_service, book_service):
        self.bot_app = bot_app
        self.quote_service = quote_service
        self.user_service = user_service
        self.book_service = book_service
        self.scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    def start(self):
        scheduled_times = [
            ("morning", config.MORNING_TIME, self._send_quote),
            ("afternoon", config.AFTERNOON_TIME, self._send_quote),
            ("evening", config.EVENING_TIME, self._send_quote),
            ("reminder", config.REMINDER_TIME, self._send_reading_reminders),
        ]

        for job_name, time_str, callback in scheduled_times:
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                callback,
                trigger=CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=config.TIMEZONE,
                ),
                args=[time_str] if callback == self._send_quote else [],
                id=f"{job_name}_{time_str.replace(':', '_')}",
                replace_existing=True,
                misfire_grace_time=900,
            )

        self.scheduler.start()

        logger.info(
            "Планировщик запущен. Часовой пояс: %s. "
            "Цитаты: %s, %s, %s. Напоминания: %s",
            config.TIMEZONE,
            config.MORNING_TIME,
            config.AFTERNOON_TIME,
            config.EVENING_TIME,
            config.REMINDER_TIME,
        )

        for job in self.scheduler.get_jobs():
            logger.info("Задача %s, следующий запуск: %s", job.id, job.next_run_time)

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _send_quote(self, time_str: str):
        chat_id = config.GROUP_CHAT_ID
        if not chat_id:
            logger.error(
                "GROUP_CHAT_ID не задан. Укажите ID группы в переменной окружения "
                "GROUP_CHAT_ID на Render или вызовите /start в группе после запуска."
            )
            return

        try:
            quote = self.quote_service.get_random()
            if not quote:
                logger.error("Не удалось получить случайную цитату.")
                return

            sent = await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text=f"🕒 {time_str}\n\n«{quote}»",
            )
            logger.info(
                "Цитата отправлена в chat_id=%s, message_id=%s",
                chat_id,
                sent.message_id,
            )
        except Exception:
            logger.exception("Ошибка при отправке цитаты в chat_id=%s", chat_id)

    async def _send_reading_reminders(self):
        chat_id = config.GROUP_CHAT_ID
        if not chat_id:
            logger.error("GROUP_CHAT_ID не задан — вечернее напоминание не отправлено.")
            return

        if not self.book_service.get_current():
            logger.info("Текущей книги нет — вечерние напоминания не отправляются.")
            return

        today = date.today().isoformat()
        overdue = []
        for uid, data in self.user_service.get_all_users().items():
            if data.get("last_mark_date") != today:
                username = data.get("username") or uid
                overdue.append(str(username))

        if not overdue:
            logger.info("Все пользователи отметились за сегодня.")
            return

        try:
            for name in overdue:
                sent = await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ {name}, вы не прочитали книгу сегодня. "
                        "Пожалуйста, прочитайте её и отметьтесь!"
                    ),
                )
                logger.info(
                    "Напоминание отправлено пользователю %s, message_id=%s",
                    name,
                    sent.message_id,
                )
        except Exception:
            logger.exception("Ошибка при отправке вечерних напоминаний в chat_id=%s", chat_id)
