"""Consent-based groups, current membership checks and public navigation."""

import asyncio
import logging

from telegram.error import TelegramError

from . import domain as d, views as v

logger = logging.getLogger(__name__)


def is_member(member):
    return member.status in {"member", "administrator", "creator"} or (
        member.status == "restricted" and member.is_member
    )


class GroupHandlers:
    async def require_admin(self, bot, gid):
        try:
            me = await bot.get_chat_member(gid, bot.id)
        except TelegramError as exc:
            raise d.RuleError(
                "Не удалось проверить группу. Добавь бота и дай права администратора."
            ) from exc
        if me.status not in {"administrator", "creator"}:
            raise d.RuleError("Для проверки участников боту нужны права администратора группы.")

    async def require_member(self, bot, gid, uid):
        await self.require_admin(bot, gid)
        try:
            member = await bot.get_chat_member(gid, uid)
        except TelegramError as exc:
            raise d.RuleError(
                "Сейчас не удалось проверить участие в группе. Попробуй позже."
            ) from exc
        if not is_member(member):
            try:
                p = await self.db(self.store.get, uid)
                if p["group_id"] == gid:
                    await self.db(self.store.mutate, uid, lambda p: p.update(group_id=None))
            except d.RuleError:
                pass
            raise d.RuleError("Ты больше не участник этой группы. Доступ прекращён.")

    async def group_start(self, update, context):
        gid = update.effective_chat.id
        await self.require_member(context.bot, gid, update.effective_user.id)
        first = await self.db(self.store.group, gid, update.effective_chat.title or "Группа")
        if first:
            context.application.create_task(self.scan_invitations(context, gid), update=update)
        await self.group_home(update, context)

    async def scan_invitations(self, context, gid):
        users = await self.db(self.store.users)
        for uid in users:
            try:
                p = await self.db(self.store.get, uid)
                if p["group_id"] is None:
                    member = await context.bot.get_chat_member(gid, uid)
                    if is_member(member):
                        await self.send_invitation(context.bot, gid, uid)
            except TelegramError:
                logger.info("An invitation could not be delivered")
            await asyncio.sleep(0.06)
        with self.store.pool.connection() as conn:
            conn.execute("UPDATE groups SET invite_scanned=true WHERE chat_id=%s", (gid,))

    async def send_invitation(self, bot, gid, uid, update=None):
        title = await self.db(self.store.group_title, gid)
        a = await self.db(self.store.action, uid, "connect", {"group_id": gid}, self.now())
        view = v.View(
            f"<b>Подключение к группе</b>\n{v.e(title)}\n"
            "Подключиться? Лес и статистика останутся закрытыми, пока ты сам не откроешь их в настройках.",
            [[("Подключиться", "connect:" + a), ("Отказаться", "cancelact:" + a)]],
        )
        if update:
            await self.display(update, view)
        else:
            await self.send_to(bot, uid, uid, view)

    async def invite(self, update, context, gid):
        await self.require_member(context.bot, gid, update.effective_user.id)
        await self.send_invitation(context.bot, gid, update.effective_user.id, update)

    async def members(self, context, gid):
        result = []
        for uid in await self.db(self.store.users, gid):
            try:
                await self.require_member(context.bot, gid, uid)
                await self.db(self.store.settle, uid, self.now())
                result.append(await self.db(self.store.get, uid))
            except d.RuleError:
                pass
        return result

    async def group_home(self, update, context, token=None, page=0):
        gid = update.effective_chat.id
        members = await self.members(context, gid)
        text = v.GROUP_INTRO + "\n\n<b>Наши Лесники счастья</b>\n"
        for p in members[page * 3 : (page + 1) * 3]:
            text += v.e(p["name"][:50]) + ": "
            if p["show_stats"]:
                text += f"завершено {sum(b['status'] == 'completed' for b in p['books'])}; "
            else:
                text += "статистика скрыта; "
            if p["show_forest"]:
                b = d.active_book(p)
                tree = "золотое" if p["golden"] else f"{len(p['tree'])}/365"
                text += f"главное дерево {tree}; книга: {d.stage(b)[1] if b else 'не выбрана'}\n"
            else:
                text += "лес скрыт\n"
        if not members:
            text += "Пока нет подключённых профилей. Подключись через ЛС."
        rows = [[("Пользователи", "users:0")]]
        nav = []
        if page:
            nav += [("←", f"ghome:{page - 1}")]
        if len(members) > (page + 1) * 3:
            nav += [("→", f"ghome:{page + 1}")]
        if nav:
            rows.append(nav)
        rows += [
            [("Подключиться в ЛС", f"url:https://t.me/{context.bot.username}?start=g_{abs(gid)}")]
        ]
        await self.display(update, v.View(text, rows, route=f"ghome:{page}"), token)

    async def group_action(self, update, context, action, args, token):
        gid, viewer = update.effective_chat.id, update.effective_user.id
        await self.require_member(context.bot, gid, viewer)
        if action == "ghome":
            await self.group_home(update, context, token, int(args[0]) if args else 0)
            return
        if action == "users":
            page = int(args[0]) if args else 0
            members = await self.members(context, gid)
            rows = [
                [(p["name"][:60], f"person:{p['owner_id']}")]
                for p in members[page * 8 : (page + 1) * 8]
            ]
            nav = []
            if page:
                nav += [("←", f"users:{page - 1}")]
            if len(members) > (page + 1) * 8:
                nav += [("→", f"users:{page + 1}")]
            await self.display(
                update,
                v.View(
                    "<b>Пользователи</b>\nВыбери участника.",
                    rows + ([nav] if nav else []) + [v.back("ghome:0")],
                    route=f"users:{page}",
                ),
                token,
            )
            return
        if action == "person":
            target = int(args[0])
            await self.require_member(context.bot, gid, target)
            p = await self.db(self.store.get, target)
            if p["group_id"] != gid:
                raise d.RuleError("Профиль больше не подключён к этой группе.")
            rows = []
            if p["show_forest"]:
                rows += [
                    [("Посмотреть лес", f"forest:{target}:0:0")],
                    [("Помочь главному дереву", f"fert:{target}")],
                ]
            if p["show_stats"]:
                rows += [[("Посмотреть статистику", f"stats:{target}")]]
            text = (
                f"<b>{v.e(p['name'])}</b>\nЛес: {'открыт' if p['show_forest'] else 'скрыт'}\n"
                f"Статистика: {'открыта' if p['show_stats'] else 'скрыта'}"
            )
            await self.display(
                update, v.View(text, rows + [v.back("users:0")], route=f"person:{target}"), token
            )
            return
        if action in {"tree", "forest", "book", "history", "stats", "fert", "fertyes", "cancelact"}:
            await self.shared_action(update, context, action, args, token)
            return
        raise d.RuleError("Это личная настройка. Открой её в ЛС с ботом.")

    async def member_changed(self, update, context):
        event = update.chat_member or update.my_chat_member
        if not event or is_member(event.new_chat_member):
            return
        gid, uid = event.chat.id, event.new_chat_member.user.id
        users = await self.db(self.store.users, gid) if uid == context.bot.id else [uid]
        for uid in users:
            try:
                p = await self.db(self.store.get, uid)
                if p["group_id"] == gid:
                    await self.db(self.store.mutate, uid, lambda p: p.update(group_id=None))
            except d.RuleError:
                pass
