from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from .user_service import UserService
from .book_service import BookService
from .stats_service import StatsService
from .config import GROUP_CHAT_ID
import logging
import asyncio
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Состояния для смены/редактирования книги
TITLE, AUTHOR, TOTAL_PAGES, NORM = range(4)
EDIT_TITLE, EDIT_AUTHOR, EDIT_TOTAL_PAGES, EDIT_NORM, EDIT_START_DATE, EDIT_CURRENT_PAGE = range(4, 10)

class Handlers:
    def __init__(self, user_svc: UserService, book_svc: BookService, stats_svc: StatsService):
        self.user_svc = user_svc
        self.book_svc = book_svc
        self.stats_svc = stats_svc

    async def _delete_bot_msg(self, context, chat_id, msg_id, delay=5):
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение бота: {e}")

    def _get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        buttons = [[InlineKeyboardButton("📊 Статистика", callback_data="stats")]]
        if self.user_svc.is_admin(user_id):
            if self.book_svc.get_current():
                buttons.append([InlineKeyboardButton("📚 Поменять книгу", callback_data="change_book")])
                buttons.append([InlineKeyboardButton("✏️ Отредактировать текущую книгу", callback_data="edit_book")])
            else:
                buttons.append([InlineKeyboardButton("📚 Установить книгу", callback_data="change_book")])
        return InlineKeyboardMarkup(buttons)

    def _get_users_status(self) -> str:
        today = datetime.now().date().isoformat()
        users = self.user_svc.get_all_users()
        book = self.book_svc.get_current()
        if not users:
            return "👥 Нет зарегистрированных пользователей."
        lines = ["👥 Статус прочтения на сегодня:"]
        for uid, data in users.items():
            username = data.get("username", uid)
            last_mark = data.get("last_mark_date")
            if book and book.get("last_update") == today:
                status = "✅" if last_mark == today else "☑️"
            else:
                status = "❓"
            lines.append(f"{username} - {status}.")
        return "\n".join(lines)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        username = user.username or user.first_name
        self.user_svc.add_user(user.id, username=username, role="reader")
        if update.effective_chat.type in ["group", "supergroup"]:
            global GROUP_CHAT_ID
            GROUP_CHAT_ID = update.effective_chat.id

        book = self.book_svc.get_current()
        users_status = self._get_users_status()
        if not book:
            text = f"📕 Книга ещё не выбрана. Администратор должен установить книгу командой /change_book.\n\n{users_status}"
        else:
            progress = self.book_svc.get_progress_percent()
            text = (
                f"В этой группе мы читаем текущую книгу и отмечаем, прочитали ли сегодня норму\n\n"
                f"Текущая книга 📕: \n {book.get('title')} - {book.get('author')}.\n"
                f"Чтобы отметить, что прочитали книгу - ✅ (просто отправьте этот символ в чат)\n"
                f"Норма - ({book.get('norm_pages')} страниц в день)\n"
                f"Текущий глобальный прогресс прочтения книги - {progress}%\n\n"
                f"{users_status}\n\n"
                f"Желаю успеха! И помни - настоящий мужчина, это тот, кто держит свое слово 💪👊😎"
            )
        keyboard = self._get_main_keyboard(user.id)
        sent = await update.message.reply_text(text, reply_markup=keyboard)
        asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id, 120))

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if query.data == "stats":
            stats_text = self.stats_svc.get_stats_text()
            await query.edit_message_text(stats_text, reply_markup=None)
            sent = await query.message.reply_text("Вернуться к главному меню: /start")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id, 120))
            return

        if query.data in ("change_book", "edit_book"):
            if not self.user_svc.is_admin(user_id):
                await query.edit_message_text("У вас нет прав для изменения книги.")
                return ConversationHandler.END

            book = self.book_svc.get_current()
            if query.data == "change_book":
                await query.edit_message_text("Введите название книги:")
                context.user_data.pop('edit_book', None)
                return TITLE

            if not book:
                await query.edit_message_text("Текущая книга не выбрана. Используйте «Поменять книгу».")
                return ConversationHandler.END

            context.user_data['edit_book'] = True
            context.user_data['edit_book_data'] = dict(book)
            await query.edit_message_text(
                f"Редактирование текущей книги.\n\nНазвание сейчас: {book.get('title')}\n"
                "Введите новое название книги:"
            )
            return EDIT_TITLE

        return ConversationHandler.END

    async def change_book_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатия на кнопку 'Поменять книгу' (запускает диалог)"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if not self.user_svc.is_admin(user_id):
            await query.edit_message_text("У вас нет прав для смены книги.")
            return ConversationHandler.END

        # Редактируем текущее сообщение с кнопкой, заменяя его на приглашение ввести название
        await query.edit_message_text("Введите название книги:")
        return TITLE

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == context.bot.id:
            return
        text = update.message.text
        if text and (text.strip() == "✅" or text.strip() == "✔" or text.strip() == "+"):
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            self.user_svc.add_user(user_id, username=username)
            book = self.book_svc.get_current()
            if not book:
                reply = await update.message.reply_text("Книга не выбрана. Обратитесь к администратору.")
                asyncio.create_task(self._delete_bot_msg(context, reply.chat_id, reply.message_id, 5))
                return
            today = datetime.now().date().isoformat()
            if book.get("last_update") != today:
                updated = self.book_svc.update_progress(user_id)
                if not updated:
                    text_msg = "⏳ Не удалось обновить прогресс книги."
                else:
                    self.user_svc.mark_read(user_id)
                    progress = self.book_svc.get_progress_percent()
                    text_msg = f"✅ Отметка принята! Текущий прогресс: {progress}%"
            else:
                self.user_svc.mark_read(user_id)
                progress = self.book_svc.get_progress_percent()
                text_msg = f"✅ Вы отметили прочтение за сегодня!\nПрогресс книги не изменился и составляет {progress}%."
            reply = await update.message.reply_text(text_msg)
            asyncio.create_task(self._delete_bot_msg(context, reply.chat_id, reply.message_id, 10))
            await self.start_command(update, context)

    # ----- Создание новой книги -----
    async def change_book_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.user_svc.is_admin(user_id):
            await update.message.reply_text("У вас нет прав для смены книги.")
            return ConversationHandler.END
        await update.message.reply_text("Введите название книги:")
        context.user_data.pop('edit_book', None)
        return TITLE

    async def change_book_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['title'] = update.message.text.strip()
        await update.message.reply_text("Введите автора книги:")
        return AUTHOR

    async def change_book_author(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['author'] = update.message.text.strip()
        await update.message.reply_text("Введите общее количество страниц (число):")
        return TOTAL_PAGES

    async def change_book_total(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            total = int(update.message.text)
            if total <= 0:
                raise ValueError
            context.user_data['total'] = total
            await update.message.reply_text("Введите норму страниц в день (число):")
            return NORM
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите положительное число.")
            return TOTAL_PAGES

    async def change_book_norm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            norm = int(update.message.text)
            total = context.user_data['total']
            if norm <= 0 or norm > total:
                raise ValueError
            title = context.user_data['title']
            author = context.user_data['author']
            self.book_svc.set_book(title, author, total, norm)
            sent = await update.message.reply_text(f"Книга '{title}' успешно установлена!")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id))
            for key in ('title', 'author', 'total', 'edit_book', 'edit_book_data'):
                context.user_data.pop(key, None)
            await self.start_command(update, context)
            return ConversationHandler.END
        except (ValueError, KeyError):
            await update.message.reply_text("Пожалуйста, введите положительное число, не превышающее общее количество страниц.")
            return NORM

    # ----- Редактирование текущей книги -----
    async def edit_book_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("efefefefef")
        context.user_data['edit_book_data']['title'] = update.message.text.strip()
        await update.message.reply_text("Введите нового автора книги:")
        return EDIT_AUTHOR

    async def edit_book_author(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['edit_book_data']['author'] = update.message.text.strip()
        await update.message.reply_text(
            f"Введите новое общее количество страниц (сейчас {context.user_data['edit_book_data'].get('total_pages')}):"
        )
        return EDIT_TOTAL_PAGES

    async def edit_book_total(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            total = int(update.message.text)
            if total <= 0:
                raise ValueError
            data = context.user_data['edit_book_data']
            if data.get('current_page', 0) > total:
                await update.message.reply_text("Новое количество страниц не может быть меньше текущей страницы. Введите другое число:")
                return EDIT_TOTAL_PAGES
            data['total_pages'] = total
            await update.message.reply_text(f"Введите новую норму страниц в день (сейчас {data.get('norm_pages')}):")
            return EDIT_NORM
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите положительное число.")
            return EDIT_TOTAL_PAGES

    async def edit_book_norm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            norm = int(update.message.text)
            data = context.user_data['edit_book_data']
            if norm <= 0 or norm > data['total_pages']:
                raise ValueError
            data['norm_pages'] = norm
            await update.message.reply_text(
                f"Введите дату начала чтения в формате ГГГГ-ММ-ДД (сейчас {data.get('start_date')}):"
            )
            return EDIT_START_DATE
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите положительное число, не превышающее общее количество страниц.")
            return EDIT_NORM

    async def edit_book_start_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            start_date = date.fromisoformat(update.message.text.strip())
            data = context.user_data['edit_book_data']
            data['start_date'] = start_date.isoformat()
            await update.message.reply_text(
                f"Введите текущую прочитанную страницу (сейчас {data.get('current_page', 0)}):"
            )
            return EDIT_CURRENT_PAGE
        except ValueError:
            await update.message.reply_text("Неверная дата. Используйте формат ГГГГ-ММ-ДД, например 2026-08-16.")
            return EDIT_START_DATE

    async def edit_book_current_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            current_page = int(update.message.text)
            data = context.user_data['edit_book_data']
            if current_page < 0 or current_page > data['total_pages']:
                raise ValueError
            data['current_page'] = current_page
            self.book_svc.update_book(
                data['title'], data['author'], data['total_pages'], data['norm_pages'],
                data['start_date'], data['current_page'], data.get('last_update')
            )
            title = data['title']
            sent = await update.message.reply_text(f"Книга '{title}' успешно отредактирована!")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id))
            context.user_data.pop('edit_book', None)
            context.user_data.pop('edit_book_data', None)
            await self.start_command(update, context)
            return ConversationHandler.END
        except (ValueError, KeyError):
            await update.message.reply_text("Пожалуйста, введите число от 0 до общего количества страниц.")
            return EDIT_CURRENT_PAGE

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sent = await update.message.reply_text("Операция отменена.")
        asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id))
        for key in ('title', 'author', 'total', 'edit_book', 'edit_book_data'):
            context.user_data.pop(key, None)
        return ConversationHandler.END
