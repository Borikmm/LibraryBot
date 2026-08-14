from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from .user_service import UserService
from .book_service import BookService
from .stats_service import StatsService
from .config import GROUP_CHAT_ID
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Состояния для смены книги
TITLE, AUTHOR, TOTAL_PAGES, NORM = range(4)

class Handlers:
    def __init__(self, user_svc: UserService, book_svc: BookService, stats_svc: StatsService):
        self.user_svc = user_svc
        self.book_svc = book_svc
        self.stats_svc = stats_svc

    # ----- Вспомогательный метод удаления сообщений бота через 2 минуты -----
    async def _delete_bot_msg(self, context, chat_id, msg_id, delay=5):
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение бота: {e}")

    # ----- Клавиатура -----
    def _get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        ]
        if self.user_svc.is_admin(user_id):
            buttons.append([InlineKeyboardButton("📚 Поменять книгу", callback_data="change_book")])
        return InlineKeyboardMarkup(buttons)

    # ----- Получение статуса всех пользователей -----
    def _get_users_status(self) -> str:
        """Возвращает список пользователей с их статусом прочтения на сегодня"""
        today = datetime.now().date().isoformat()
        users = self.user_svc.get_all_users()
        book = self.book_svc.get_current()
        
        if not users:
            return "👥 Нет зарегистрированных пользователей."
        
        lines = ["👥 Статус прочтения на сегодня:"]
        for uid, data in users.items():
            username = data.get("username", uid)
            last_mark = data.get("last_mark_date")
            # Проверяем, читает ли пользователь эту книгу (если есть текущая книга)
            if book and book.get("last_update") == today:
                # Если пользователь отмечал сегодня
                if last_mark == today:
                    status = "✅"
                else:
                    status = "☑️"
            else:
                # Если книга не выбрана или сегодня ещё никто не отмечал
                status = "❓"
            lines.append(f"{username} - {status}.")
        
        return "\n".join(lines)

    # ----- Команда /start -----
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        username = user.username or user.first_name
        self.user_svc.add_user(user.id, username=username, role="reader")

        if update.effective_chat.type in ["group", "supergroup"]:
            global GROUP_CHAT_ID
            GROUP_CHAT_ID = update.effective_chat.id

        book = self.book_svc.get_current()
        
        # Получаем статусы пользователей
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

    # ----- Обработчик кнопок -----
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if query.data == "stats":
            stats_text = self.stats_svc.get_stats_text()
            await query.edit_message_text(stats_text, reply_markup=None)
            sent = await query.message.reply_text("Вернуться к главному меню: /start")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id, 120))

        elif query.data == "mark_read":
            book = self.book_svc.get_current()
            if not book:
                await query.edit_message_text("Книга не выбрана. Обратитесь к администратору.")
                return

            today = datetime.now().date().isoformat()
            if book.get("last_update") != today:
                # Только первый читатель за день двигает общую книгу
                updated = self.book_svc.update_progress(user_id)
            
                if not updated:
                    text = "⏳ Не удалось обновить прогресс книги."
                else:
                    # И первый пользователь тоже получает свою личную отметку
                    self.user_svc.mark_read(user_id)
                    progress = self.book_svc.get_progress_percent()
                    text = f"✅ Отметка принята! Текущий прогресс: {progress}%"
            else:
                # Книга уже продвинута сегодня.
                # Но конкретного пользователя всё равно отмечаем.
                self.user_svc.mark_read(user_id)
                progress = self.book_svc.get_progress_percent()
                text = (
                    f"✅ Вы отметили прочтение за сегодня!\n"
                    f"Прогресс книги не изменился и составляет {progress}%."
                )

            await query.edit_message_text(text, reply_markup=None)
            sent = await query.message.reply_text("Вернуться к главному меню: /start")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id, 5))

        elif query.data == "change_book":
            if not self.user_svc.is_admin(user_id):
                await query.edit_message_text("У вас нет прав для смены книги.")
                return
            
            # Запускаем диалог смены книги через команду
            await query.edit_message_text("Введите название книги:")
            # Устанавливаем состояние для ConversationHandler
            context.user_data['in_change_book'] = True
            # Сохраняем chat_id и message_id для ответа
            context.user_data['change_book_chat_id'] = query.message.chat_id
            context.user_data['change_book_message_id'] = query.message.message_id
            return ConversationHandler.END

    # ----- Обработка текстовых сообщений (отметка) -----
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
            if book.get("last_update") == today:
                reply = await update.message.reply_text("⏳ Вы уже отмечали сегодня! Прогресс не изменился.")
                asyncio.create_task(self._delete_bot_msg(context, reply.chat_id, reply.message_id, 5))
                return

            updated = self.book_svc.update_progress(user_id)
            if updated:
                self.user_svc.mark_read(user_id)
                progress = self.book_svc.get_progress_percent()
                text_msg = f"✅ Отметка принята! Текущий прогресс: {progress}%"
            else:
                text_msg = "⏳ Не удалось отметить. Попробуйте позже."

            reply = await update.message.reply_text(text_msg)
            asyncio.create_task(self._delete_bot_msg(context, reply.chat_id, reply.message_id, 10))
            await self.start_command(update, context)

    # ----- Диалог смены книги (ConversationHandler) -----
    async def change_book_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.user_svc.is_admin(user_id):
            await update.message.reply_text("У вас нет прав для смены книги.")
            return ConversationHandler.END

        # Если диалог начат с кнопки, используем сохранённые данные
        if context.user_data.get('in_change_book'):
            # Удаляем сообщение с кнопкой (оно уже отредактировано)
            context.user_data['in_change_book'] = False
            # Продолжаем диалог
            await update.message.reply_text("Введите название книги:")
            return TITLE
        
        await update.message.reply_text("Введите название книги:")
        return TITLE

    async def change_book_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['title'] = update.message.text
        await update.message.reply_text("Введите автора книги:")
        return AUTHOR

    async def change_book_author(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['author'] = update.message.text
        await update.message.reply_text("Введите общее количество страниц (число):")
        return TOTAL_PAGES

    async def change_book_total(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            total = int(update.message.text)
            context.user_data['total'] = total
            await update.message.reply_text("Введите норму страниц в день (число):")
            return NORM
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите число.")
            return TOTAL_PAGES

    async def change_book_norm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            norm = int(update.message.text)
            title = context.user_data['title']
            author = context.user_data['author']
            total = context.user_data['total']
            self.book_svc.set_book(title, author, total, norm)
            sent = await update.message.reply_text(f"Книга '{title}' успешно установлена!")
            asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id))
            
            # Очищаем данные диалога
            context.user_data.pop('title', None)
            context.user_data.pop('author', None)
            context.user_data.pop('total', None)
            
            await self.start_command(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите число.")
            return NORM

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sent = await update.message.reply_text("Операция отменена.")
        asyncio.create_task(self._delete_bot_msg(context, sent.chat_id, sent.message_id))
        context.user_data.pop('in_change_book', None)
        context.user_data.pop('title', None)
        context.user_data.pop('author', None)
        context.user_data.pop('total', None)
        return ConversationHandler.END
