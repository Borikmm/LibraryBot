from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .config import MORNING_TIME, AFTERNOON_TIME, EVENING_TIME, GROUP_CHAT_ID
import logging
import asyncio

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, bot_app, quote_service):
        self.bot_app = bot_app
        self.quote_service = quote_service
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self):
        times = [MORNING_TIME, AFTERNOON_TIME, EVENING_TIME]
        for t in times:
            hour, minute = map(int, t.split(':'))
            self.scheduler.add_job(
                self._send_quote,
                CronTrigger(hour=hour, minute=minute, timezone="UTC"),
                args=[t],
                id=f"quote_{t}"
            )
        self.scheduler.start()
        logger.info("Планировщик запущен в UTC.")

    def stop(self):
        self.scheduler.shutdown()

    async def _send_quote(self, time_str: str):
        if not GROUP_CHAT_ID:
            logger.error("GROUP_CHAT_ID не задан!")
            return
        quote = self.quote_service.get_random()
        text = f"🕒 {time_str}\n\n«{quote}»"
        try:
            sent = await self.bot_app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
            #asyncio.create_task(self._delete_after_delay(GROUP_CHAT_ID, sent.message_id, delay=120))
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

    async def _delete_after_delay(self, chat_id: int, message_id: int, delay: int = 120):
        await asyncio.sleep(delay)
        try:
            await self.bot_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Не удалось удалить цитату {message_id}: {e}")