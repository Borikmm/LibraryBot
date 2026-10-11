"""Menu ownership, shared forest screens and Telegram rendering."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest

from . import domain as d, views as v
from .groups import GroupHandlers
from .private import PrivateHandlers
from .preview import PreviewStore

logger = logging.getLogger(__name__)
ASSETS = Path(__file__).resolve().parent.parent / "assets"


class Controller(PrivateHandlers, GroupHandlers):
    def __init__(self, store, service, settings, quotes):
        self.store, self.service, self.settings, self.quotes = store, service, settings, quotes
        self.preview = PreviewStore()

    @staticmethod
    def now():
        return datetime.now(UTC)

    @staticmethod
    async def db(function, *args):
        return await asyncio.to_thread(function, *args)

    @staticmethod
    def confirm(yes, token):
        return [[("Да", yes), ("Отмена", "cancelact:" + token)]]

    @staticmethod
    def keyboard(token, rows):
        result = []
        for row in rows:
            buttons = []
            for label, action in row:
                if action.startswith("url:"):
                    buttons.append(InlineKeyboardButton(label, url=action[4:]))
                else:
                    data = token + "|" + action
                    if len(data.encode("utf-8")) > 64:
                        raise ValueError("Callback exceeds Telegram's 64-byte limit")
                    buttons.append(InlineKeyboardButton(label, callback_data=data))
            if buttons:
                result.append(buttons)
        return InlineKeyboardMarkup(result)

    @staticmethod
    def private_link(username):
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("Открыть ЛС", url=f"https://t.me/{username}")]]
        )

    async def menu_keyboard(self, token, chat_id, view):
        rows = view.rows
        if chat_id < 0 and view.route:
            depth = await self.db(self.store.remember_route, token, view.route)
            if depth > 1:
                rows = [
                    [(label, "back" if label == "← Назад" else action) for label, action in row]
                    for row in rows
                ]
        return self.keyboard(token, rows)

    async def send_to(self, bot, uid, chat_id, view, token=None):
        token = token or await self.db(self.store.create_menu, uid, chat_id)
        markup = await self.menu_keyboard(token, chat_id, view)
        photo = view.photo
        if photo:
            with (ASSETS / photo).open("rb") as file:
                message = await bot.send_photo(
                    chat_id, file, caption=view.text, parse_mode="HTML", reply_markup=markup
                )
        else:
            message = await bot.send_message(
                chat_id, view.text, parse_mode="HTML", reply_markup=markup
            )
        await self.db(self.store.bind_menu, token, message.message_id)
        return message

    async def display(self, update, view, token=None):
        message, uid = update.effective_message, update.effective_user.id
        if not token or not update.callback_query:
            return await self.send_to(update.get_bot(), uid, update.effective_chat.id, view)
        markup = await self.menu_keyboard(token, update.effective_chat.id, view)
        photo = view.photo
        try:
            if photo and message.photo:
                with (ASSETS / photo).open("rb") as file:
                    await message.edit_media(
                        InputMediaPhoto(file, caption=view.text, parse_mode="HTML"),
                        reply_markup=markup,
                    )
            elif not photo and not message.photo:
                await message.edit_text(view.text, parse_mode="HTML", reply_markup=markup)
            else:
                # Telegram cannot convert text/photo; the permanent golden reward is an image.
                await message.delete()
                return await self.send_to(
                    update.get_bot(), uid, update.effective_chat.id, view, token
                )
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise

    async def show_home(self, update):
        uid = update.effective_user.id
        await self.db(self.store.settle, uid, self.now())
        await self.display(update, v.home(await self.db(self.store.get, uid), self.now()))

    async def start(self, update, context):
        try:
            if update.effective_chat.type == "private":
                await self.private_start(update, context)
            elif update.effective_chat.type in {"group", "supergroup"}:
                await self.group_start(update, context)
        except d.RuleError as exc:
            await update.effective_message.reply_text(str(exc))

    async def callback(self, update, context):
        query = update.callback_query
        try:
            if not query.message or not query.data or "|" not in query.data:
                raise d.RuleError("Меню устарело. Открой /start.")
            token, route = query.data.split("|", 1)
            await self.db(
                self.store.menu,
                token,
                query.from_user.id,
                query.message.chat_id,
                query.message.message_id,
            )
            if route == "back" and update.effective_chat.type != "private":
                route = await self.db(self.store.back_route, token)
            action, *args = route.split(":")
            if action == "demo":
                if update.effective_chat.type != "private":
                    raise d.RuleError("Просмотр доступен только владельцу в ЛС.")
                await self.preview_action(update, context, args, token)
                await query.answer()
                return
            await query.answer()
            if update.effective_chat.type == "private":
                await self.db(self.store.settle, query.from_user.id, self.now())
                if action in {
                    "tree",
                    "forest",
                    "book",
                    "history",
                    "stats",
                    "fert",
                    "fertyes",
                    "cancelact",
                }:
                    context.user_data.pop("flow", None)
                    await self.shared_action(update, context, action, args, token)
                else:
                    await self.private_action(update, context, action, args, token)
            else:
                await self.group_action(update, context, action, args, token)
        except (d.RuleError, ValueError, IndexError) as exc:
            text = (
                str(exc) if isinstance(exc, d.RuleError) else "Некорректная кнопка. Открой /start."
            )
            try:
                await query.answer(text, show_alert=True)
            except BadRequest:
                pass

    async def check_view(self, update, context, target, kind):
        uid = update.effective_user.id
        private = update.effective_chat.type == "private"
        group = None if private else update.effective_chat.id
        if not private:
            await self.require_member(context.bot, group, uid)
            await self.require_member(context.bot, group, target)
        allowed = await self.db(self.service.can_view, uid, target, kind, group)
        if not allowed:
            raise d.RuleError("Эти данные закрыты или профиль больше не подключён к группе.")
        await self.db(self.store.settle, target, self.now())
        return await self.db(self.store.get, target)

    async def shared_action(self, update, context, action, args, token):
        uid, now = update.effective_user.id, self.now()
        private = update.effective_chat.type == "private"
        if action == "cancelact":
            await self.db(self.store.cancel_action, args[0], uid)
            view = v.View("Действие отменено.", [v.back("home" if private else "ghome:0")])
        elif action == "fertyes":
            payload = await self.db(self.store.peek_action, args[0], uid, "fertilize")
            target = payload["target"]
            await self.check_view(update, context, target, "forest")
            await self.db(self.store.settle, uid, now)
            await self.db(self.service.fertilize, uid, args[0], now)
            p = await self.db(self.store.get, target)
            view = v.main_tree(p, private=private)
        else:
            target = int(args[0])
            p = await self.check_view(
                update, context, target, "stats" if action == "stats" else "forest"
            )
            if action == "tree":
                view = v.main_tree(p, private=private)
            elif action == "forest":
                view = v.forest(p, int(args[1]), int(args[2]), private=private)
            elif action == "book":
                view = v.book(p, args[1], private=private)
            elif action == "history":
                view = v.history(p, args[1], int(args[2]))
            elif action == "stats":
                view = v.stats(p, now, private=private)
            elif action == "fert":
                sender = await self.db(self.store.get, uid)
                if not sender["coins"]:
                    raise d.RuleError("Нет монет. Получай одну за каждые 10 дней серии.")
                if p["golden"]:
                    raise d.RuleError("Дерево уже золотое. Монета не потрачена.")
                a = await self.db(self.store.action, uid, "fertilize", {"target": target}, now)
                view = v.View(
                    f"Добавить один символ дереву <b>{v.e(p['name'])}</b> за одну твою монету?\n"
                    f"Баланс: {sender['coins']}. Монеты также защищают серию от пропусков.",
                    self.confirm("fertyes:" + a, a),
                )
            else:
                raise d.RuleError("Действие недоступно.")
        await self.display(update, view, token)

    async def error(self, update, context):
        # Avoid logging Update objects (private messages) and HTTP URLs (bot token).
        logger.error("Update failed: %s", type(context.error).__name__)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Сейчас не удалось выполнить действие. Попробуй ещё раз или открой /start."
                )
            except Exception:
                logger.error("Could not send the error message")
