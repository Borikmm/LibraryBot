from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Настройка вывода в консоль
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class Scheduler:
    def __init__(self, bot_app, quote_service):
        self.bot_app = bot_app
        self.quote_service = quote_service

        self.scheduler = AsyncIOScheduler(
            timezone=config.TIMEZONE
        )

    def start(self):
        times = [
            config.MORNING_TIME,
            config.AFTERNOON_TIME,
            config.EVENING_TIME,
        ]

        for time_str in times:
            hour, minute = map(int, time_str.split(":"))

            self.scheduler.add_job(
                self._send_quote,
                trigger=CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=config.TIMEZONE,
                ),
                args=[time_str],
                id=f"quote_{time_str.replace(':', '_')}",
                replace_existing=True,
            )

        self.scheduler.start()

        logger.info(
            "Планировщик запущен. Часовой пояс: %s. "
            "Время цитат: %s",
            config.TIMEZONE,
            ", ".join(times),
        )

        for job in self.scheduler.get_jobs():
            logger.info(
                "Запланирована задача %s, следующий запуск: %s",
                job.id,
                job.next_run_time,
            )

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _send_quote(self, time_str: str):
        # Берём актуальный GROUP_CHAT_ID из config,
        # а не устаревшую копию, импортированную при запуске.
        chat_id = config.GROUP_CHAT_ID

        if not chat_id:
            logger.error(
                "GROUP_CHAT_ID не задан. "
                "Сначала бот должен получить /start в группе."
            )
            print("aaaaa------")
            return

        try:
            quote = self.quote_service.get_random()

            if not quote:
                logger.error("Не удалось получить случайную цитату.")
                print("aaaaa------2")
                return

            text = f"🕒 {time_str}\n\n«{quote}»"

            sent = await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text=text,
            )

            logger.info(
                "Цитата отправлена в chat_id=%s, message_id=%s",
                chat_id,
                sent.message_id,
            )

        except Exception:
            logger.exception(
                "Ошибка при отправке цитаты в chat_id=%s",
                chat_id,
            )
            print("aaaaa------3")
