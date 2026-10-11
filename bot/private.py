"""Private onboarding, book forms and settings."""

import io
import json

from . import domain as d, views as v
from .backup import MAX_BACKUP_BYTES, parse_backup


class PrivateHandlers:
    async def private_start(self, update, context):
        uid = update.effective_user.id
        p = await self.db(
            self.store.ensure,
            uid,
            update.effective_user.full_name,
            self.settings.timezone,
            self.now(),
        )
        context.user_data.pop("flow", None)
        await self.db(self.store.settle, uid, self.now())
        if context.args and context.args[0].startswith("g_"):
            try:
                gid = -int(context.args[0][2:])
            except ValueError as exc:
                raise d.RuleError("Ссылка подключения некорректна.") from exc
            await self.invite(update, context, gid)
            return
        if not p["onboarded"]:
            await self.display(update, v.View(v.ONBOARDING[0], [[("Дальше →", "intro:1")]]))
        else:
            await self.show_home(update)

    async def private_action(self, update, context, action, args, token):
        uid, now = update.effective_user.id, self.now()
        p = await self.db(self.store.get, uid)
        view = None
        if action == "home":
            context.user_data.pop("flow", None)
            view = v.home(p, now)
        elif action == "intro":
            page = int(args[0])
            if not 0 <= page < len(v.ONBOARDING):
                raise d.RuleError("Страница недоступна.")
            rows = (
                [[("Дальше →", f"intro:{page + 1}")]] if page < 2 else [[("Продолжить", "restore")]]
            )
            view = v.View(v.ONBOARDING[page], rows)
        elif action == "restore":
            view = v.View(
                "<b>Сохранённый профиль</b>\nЕсть ли у тебя экспорт прежних данных?",
                [
                    [("Импортировать данные", "import")],
                    [("Начать с пустым профилем", "add")],
                    [("Выбрать книгу позже", "later")],
                ],
            )
        elif action == "later":
            await self.db(self.store.mutate, uid, lambda p: p.update(onboarded=True))
            view = v.home(await self.db(self.store.get, uid), now)
        elif action == "settings":
            title = await self.db(self.store.group_title, p["group_id"]) if p["group_id"] else None
            view = v.settings(p, title)
        elif action == "books":
            view = v.books(p, int(args[0]) if args else 0)
        elif action == "add":
            context.user_data["flow"] = {"kind": "add", "step": "title", "values": {}}
            view = v.View(
                "<b>Новая книга</b>\nВведи название (до 200 символов).",
                [v.back("books"), [("Выбрать позже", "later")]],
            )
        elif action == "pause":
            await self.db(self.store.mutate, uid, d.pause_book)
            view = v.books(await self.db(self.store.get, uid))
        elif action == "resume":
            await self.db(self.store.mutate, uid, lambda p: d.resume_book(p, args[0]))
            view = v.home(await self.db(self.store.get, uid), now)
        elif action == "editmenu":
            b = d.book_by_id(p, args[0])
            fields = [
                ("Название", "title"),
                ("Автор", "author"),
                ("Всего страниц", "total"),
                ("Дневная норма", "norm"),
                ("Дата начала", "start"),
                ("Текущая страница", "page"),
            ]
            view = v.View(
                f"<b>Изменить · {v.e(b['title'])}</b>\nПравка страницы не даёт новый день или награду.",
                [[(title, f"edit:{b['id']}:{field}")] for title, field in fields]
                + [v.back(f"book:{uid}:{b['id']}")],
            )
        elif action == "edit":
            d.book_by_id(p, args[0])
            prompts = {
                "title": "Введи название.",
                "author": "Введи автора.",
                "total": "Введи общее число страниц.",
                "norm": "Введи дневную норму.",
                "page": "Введи текущую прочитанную страницу.",
                "start": "Введи дату начала в формате ГГГГ-ММ-ДД.",
            }
            if args[1] not in prompts:
                raise d.RuleError("Неизвестный параметр.")
            context.user_data["flow"] = {"kind": "edit", "book_id": args[0], "field": args[1]}
            view = v.View(prompts[args[1]], [v.back(f"editmenu:{args[0]}")])
        elif action == "delete":
            b = d.book_by_id(p, args[0])
            a = await self.db(self.store.action, uid, "delete", {"book_id": b["id"]}, now)
            view = v.View(
                f"Удалить <b>{v.e(b['title'])}</b>?\nИсчезнут книга и её история чтения; "
                "страницы будут исключены из общих итогов. Монеты и главное дерево сохранятся.",
                self.confirm("deleteyes:" + a, a),
            )
        elif action == "deleteyes":
            await self.db(self.service.delete, uid, args[0], now)
            view = v.forest(await self.db(self.store.get, uid))
        elif action == "timezone":
            zones = [
                ("Чита", "Asia/Chita"),
                ("Москва", "Europe/Moscow"),
                ("Екатеринбург", "Asia/Yekaterinburg"),
                ("Новосибирск", "Asia/Novosibirsk"),
                ("Владивосток", "Asia/Vladivostok"),
                ("UTC", "UTC"),
            ]
            view = v.View(
                f"<b>Часовой пояс</b>\nСейчас: {v.e(p['timezone'])}\n"
                "Определяет сутки и время уведомлений.",
                [[(label, "tz:" + zone)] for label, zone in zones]
                + [[("Ввести другой пояс", "tzinput")], v.back("settings")],
            )
        elif action == "tz":
            await self.db(self.store.mutate, uid, lambda p: d.change_timezone(p, args[0], now))
            title = await self.db(self.store.group_title, p["group_id"]) if p["group_id"] else None
            view = v.settings(await self.db(self.store.get, uid), title)
        elif action == "tzinput":
            context.user_data["flow"] = {"kind": "timezone"}
            view = v.View(
                "Введи часовой пояс IANA, например Europe/Berlin или Asia/Chita.",
                [v.back("timezone")],
            )
        elif action == "privacy":
            view = v.View(
                "<b>Приватность</b>\nЛес включает карту и карточки книг. "
                "Общая статистика открывается отдельно. Данные видны участникам подключённой группы.",
                [
                    [("Лес: " + ("открыт" if p["show_forest"] else "скрыт"), "toggle:show_forest")],
                    [
                        (
                            "Статистика: " + ("открыта" if p["show_stats"] else "скрыта"),
                            "toggle:show_stats",
                        )
                    ],
                    v.back("settings"),
                ],
            )
        elif action == "toggle":
            field = args[0]
            if field not in {"show_forest", "show_stats", "reminders", "quotes_enabled"}:
                raise d.RuleError("Неизвестная настройка.")
            await self.db(self.store.mutate, uid, lambda p: p.update({field: not p[field]}))
            destination = (
                "motivation"
                if field == "quotes_enabled"
                else "privacy"
                if field.startswith("show")
                else "settings"
            )
            await self.private_action(update, context, destination, [], token)
            return
        elif action == "motivation":
            view = v.motivation(p)
        elif action == "quoteadd":
            context.user_data["flow"] = {"kind": "quote_time"}
            view = v.View(
                "Введи время в формате ЧЧ:ММ, например 06:00. Максимум — 24 времени.",
                [v.back("motivation")],
            )
        elif action == "quotedel":
            view = v.View(
                "<b>Удалить время</b>\nВыбери время." if p["quote_times"] else "Расписание пусто.",
                [[(t, "quoteremove:" + t.replace(":", "-"))] for t in p["quote_times"]]
                + [v.back("motivation")],
            )
        elif action == "quoteremove":
            t = args[0].replace("-", ":")
            await self.db(
                self.store.mutate,
                uid,
                lambda p: p.update(quote_times=[x for x in p["quote_times"] if x != t]),
            )
            view = v.motivation(await self.db(self.store.get, uid))
        elif action == "quote":
            view = v.View(
                "<b>Мотивация</b>\n\n«" + v.e(self.quotes.get_random()) + "»",
                [v.back("motivation")],
            )
        elif action == "rules":
            page = int(args[0])
            if not 0 <= page < len(v.RULES):
                raise d.RuleError("Страница недоступна.")
            nav = []
            if page:
                nav += [("←", f"rules:{page - 1}")]
            if page < 2:
                nav += [("→", f"rules:{page + 1}")]
            view = v.View(v.RULES[page], [nav, v.back("settings")])
        elif action == "data":
            view = v.View(
                "<b>Мои данные</b>\nЭкспорт — личный JSON-файл для восстановления. "
                "Импорт заменяет профиль после проверки и подтверждения; группу нужно подключить заново.",
                [[("Экспортировать", "export"), ("Импортировать", "import")], v.back("settings")],
            )
        elif action == "export":
            await self.export_command(update, context)
            return
        elif action == "import":
            context.user_data["flow"] = {"kind": "import"}
            view = v.View(
                "Пришли JSON-файл экспорта LibraryBot (до 5 МБ). "
                "Сначала я проверю его и покажу результат. Текущий профиль пока сохраняется.",
                [v.back("data")],
            )
        elif action == "importyes":
            await self.db(self.service.import_profile, uid, args[0], now)
            context.user_data.pop("flow", None)
            view = v.home(await self.db(self.store.get, uid), now)
        elif action == "group":
            if p["group_id"]:
                title = await self.db(self.store.group_title, p["group_id"])
                view = v.View(
                    f"<b>Группа</b>\n{v.e(title)}\nОтключение сохранит книги и личный прогресс.",
                    [[("Отключиться", "disconnect")], v.back("settings")],
                )
            else:
                view = v.View(
                    "Группа не подключена. Добавь бота в группу, дай права администратора "
                    "и отправь там /start. Подключись через приглашение в ЛС.",
                    [v.back("settings")],
                )
        elif action == "disconnect":
            a = await self.db(self.store.action, uid, "disconnect", {}, now)
            view = v.View(
                "Отключиться от группы? Доступ к твоему профилю через группу прекратится.",
                self.confirm("disconnectyes:" + a, a),
            )
        elif action == "disconnectyes":
            await self.db(self.service.disconnect, uid, args[0], now)
            view = v.settings(await self.db(self.store.get, uid))
        elif action == "connect":
            payload = await self.db(self.store.peek_action, args[0], uid, "connect")
            await self.require_member(context.bot, payload["group_id"], uid)
            await self.db(self.service.connect, uid, args[0], now)
            view = v.View(
                "Группа подключена. Лес и статистика сохраняют свои настройки приватности.",
                [[("Продолжить знакомство", "intro:0")]]
                if not p["onboarded"]
                else [v.back("home")],
            )
        if view is None:
            raise d.RuleError("Действие недоступно. Открой /start.")
        # Any navigation closes a form, except the newly opened form itself.
        if action not in {"add", "edit", "tzinput", "quoteadd", "import"}:
            context.user_data.pop("flow", None)
        await self.display(update, view, token)

    async def text(self, update, context):
        if update.effective_chat.type != "private":
            if update.message.text.strip() in {"✅", "✔", "✔️", "✓"}:
                await update.message.reply_text(
                    "Отметки принимаются только в ЛС с ботом.",
                    reply_markup=self.private_link(context.bot.username),
                )
            return
        try:
            uid, now, text = update.effective_user.id, self.now(), update.message.text.strip()
            if text in {"✅", "✔", "✔️", "✓"}:
                await self.read_command(update, context)
                return
            flow = context.user_data.get("flow")
            if not flow:
                await self.show_home(update)
                return
            kind = flow["kind"]
            if kind == "add":
                step = flow["step"]
                value = text
                if step in {"title", "author"} and not 1 <= len(value) <= 200:
                    raise d.RuleError("Нужно от 1 до 200 символов.")
                if step in {"total", "norm"}:
                    value = d.integer(text, 1)
                flow["values"][step] = value
                steps = {
                    "title": ("author", "Введи автора."),
                    "author": ("total", "Сколько страниц в книге?"),
                    "total": ("norm", "Сколько страниц в день ты будешь читать?"),
                }
                if step in steps:
                    flow["step"], prompt = steps[step]
                    await self.display(update, v.View(prompt, [v.back("books")]))
                    return
                values = flow["values"]
                await self.db(self.store.mutate, uid, lambda p: d.add_book(p, now=now, **values))
            elif kind == "edit":
                await self.db(
                    self.store.mutate,
                    uid,
                    lambda p: d.edit_book(p, flow["book_id"], flow["field"], text, now),
                )
            elif kind == "timezone":
                await self.db(self.store.settle, uid, now)
                await self.db(self.store.mutate, uid, lambda p: d.change_timezone(p, text, now))
            elif kind == "quote_time":
                value = d.validate_time(text)

                def add_time(p):
                    if value not in p["quote_times"]:
                        if len(p["quote_times"]) >= 24:
                            raise d.RuleError("Уже настроено 24 времени. Сначала удали одно.")
                        p["quote_times"] = sorted(p["quote_times"] + [value])

                await self.db(self.store.mutate, uid, add_time)
            elif kind == "import":
                raise d.RuleError("Пришли JSON как файл, а не текстом. /cancel отменит импорт.")
            context.user_data.pop("flow", None)
            if kind == "edit":
                await self.display(
                    update, v.book(await self.db(self.store.get, uid), flow["book_id"])
                )
            elif kind == "quote_time":
                await self.display(update, v.motivation(await self.db(self.store.get, uid)))
            else:
                await self.show_home(update)
        except d.RuleError as exc:
            await update.message.reply_text(str(exc))

    async def read_command(self, update, context):
        if update.effective_chat.type != "private":
            await update.effective_message.reply_text("Отправь ✅ в ЛС с ботом.")
            return
        try:
            preview = await self.db(self.preview.advance, update.effective_user.id, self.now())
            if preview is not None:
                context.user_data.pop("flow", None)
                await self.display(update, preview.view())
                return
            result = await self.db(self.service.mark, update.effective_user.id, self.now())
            b = result["book"]
            text = (
                f"✅ Отметка зачтена! +{result['pages']} страниц\n"
                f"{v.e(b['title'])}: {b['page']} из {b['total']} — {d.percentage(b)}%"
            )
            if result["completed"]:
                text += "\n🌲 Книга завершена! Дерево сохранено в лесу. На следующий день действует бесплатная защита."
            if result["rewarded"]:
                text += "\n🪙 Новый десяток серии — получена одна монета!"
            if result["golden"]:
                text += "\n🏆 Главное дерево золотое! Посмотри награду."
            p = await self.db(self.store.get, update.effective_user.id)
            view = v.home(p, self.now())
            view.text = text + "\n\n" + view.text
            await self.display(update, view)
            if result["golden_new"]:
                await self.display(update, v.main_tree(p))
        except d.RuleError as exc:
            await update.effective_message.reply_text(str(exc))

    async def preview_action(self, update, context, args, token):
        uid, now = update.effective_user.id, self.now()
        if len(args) != 1 or args[0] not in {"1", "10", "365", "exit"}:
            raise d.RuleError("Неизвестное действие просмотра.")
        if args[0] == "exit":
            if not await self.db(self.preview.disable, uid, now):
                raise d.RuleError("Время просмотра истекло. Открой /start.")
            view = v.View(
                "Просмотр завершён. Снова действует одна отметка чтения в день.",
                [v.back("home")],
            )
        else:
            preview = await self.db(self.preview.advance, uid, now, int(args[0]))
            if preview is None:
                raise d.RuleError("Время просмотра истекло. Открой /start.")
            view = preview.view()
        context.user_data.pop("flow", None)
        await self.display(update, view, token)

    async def export_command(self, update, context):
        if update.effective_chat.type != "private":
            await update.effective_message.reply_text("Экспорт доступен только владельцу в ЛС.")
            return
        data = await self.db(self.service.export, update.effective_user.id, self.now())
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        await update.effective_message.reply_document(
            io.BytesIO(raw),
            filename=f"LibraryBot-{self.now():%Y-%m-%d}.json",
            caption="Личный профиль для восстановления. Храни файл у себя.",
        )

    async def document(self, update, context):
        if update.effective_chat.type != "private":
            return
        if context.user_data.get("flow", {}).get("kind") != "import":
            await update.message.reply_text("Открой Настройки → Данные → Импортировать.")
            return
        try:
            doc = update.message.document
            if doc.file_size is None or doc.file_size > MAX_BACKUP_BYTES:
                raise d.RuleError("Размер файла неизвестен или превышает 5 МБ.")
            file = await doc.get_file()
            raw = await file.download_as_bytearray()
            uid, now = update.effective_user.id, self.now()
            payload = parse_backup(bytes(raw), uid, now)
            p = payload["profile"]
            a = await self.db(self.store.action, uid, "import", payload, now)
            text = (
                f"<b>Файл проверен</b>\nКниг: {len(p['books'])}\nДней чтения: {len(p['marks'])}\n"
                f"Главное дерево: {len(p['tree'])}/365\nМонеты: {p['coins']}\n"
                "Заменить текущий профиль? Подключение к группе потребуется заново."
            )
            await self.display(update, v.View(text, self.confirm("importyes:" + a, a)))
        except d.RuleError as exc:
            await update.message.reply_text(
                str(exc) + "\nМожно загрузить другой файл или отправить /cancel."
            )

    async def cancel(self, update, context):
        if update.effective_chat.type == "private":
            context.user_data.pop("flow", None)
            await self.show_home(update)
