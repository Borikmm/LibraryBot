import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes

from . import config
from .quote_service import QuoteService

logger = logging.getLogger(__name__)


class ManualQuoteHandler:
    def __init__(self, quote_service: QuoteService):
        self.quote_service = quote_service

    def add_button(self, keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
        """Add the public manual-quote button without changing admin-only buttons."""
        rows = [list(row) for row in keyboard.inline_keyboard]
        rows.insert(1, [InlineKeyboardButton("💬 Отправить цитату", callback_data="send_quote")])
        return InlineKeyboardMarkup(rows)

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        chat_id = config.GROUP_CHAT_ID
        if not chat_id:
            await query.answer("ID группы не задан. Выполните /start в группе.", show_alert=True)
            return

        try:
            quote = self.quote_service.get_random()
            if not quote:
                raise RuntimeError("Список цитат пуст")

            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=f"«{quote}»",
            )
            logger.info(
                "Цитата отправлена вручную: requested_by=%s, chat_id=%s, message_id=%s",
                query.from_user.id,
                chat_id,
                sent.message_id,
            )
            await query.answer("Цитата отправлена")
        except Exception:
            logger.exception("Ошибка при ручной отправке цитаты в chat_id=%s", chat_id)
            await query.answer("Не удалось отправить цитату", show_alert=True)
