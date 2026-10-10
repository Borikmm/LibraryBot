from datetime import timedelta
from types import SimpleNamespace

import pytest
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot import domain as d, views as v
from bot.config import Settings
from bot.navigation import Controller
from bot.service import Service
from telegram_api import TelegramAPI
from test_domain import START


@pytest.fixture
async def ui(store):
    api = TelegramAPI()
    c = Controller(
        store,
        Service(store),
        Settings("123456:fake-token", "unused", "UTC"),
        SimpleNamespace(get_random=lambda: "Читай каждый день"),
    )
    c.now = lambda: START
    app = Application.builder().token("123456:fake-token").request(api).build()
    app.add_handler(CommandHandler("start", c.start))
    app.add_handler(CommandHandler("export", c.export_command))
    app.add_handler(CallbackQueryHandler(c.callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, c.text))
    await app.initialize()
    yield app, api, c
    await app.shutdown()


async def text(ui, uid, value, gid=None):
    app, api, _ = ui
    gid = gid or uid
    update = {
        "update_id": len(api.calls) + 100,
        "message": {
            "message_id": 5000 + len(api.calls),
            "date": 1,
            "from": {"id": uid, "first_name": "Reader", "is_bot": False},
            "chat": {
                "id": gid,
                "type": "private" if gid > 0 else "supergroup",
                "title": "Test group",
            },
            "text": value,
        },
    }
    if value.startswith("/"):
        update["message"]["entities"] = [
            {"type": "bot_command", "offset": 0, "length": len(value.split()[0])}
        ]
    await app.process_update(Update.de_json(update, app.bot))


def last_message(ui, gid):
    return [m for (chat, _), m in ui[1].messages.items() if chat == gid][-1]


async def click(ui, uid, label=None, route=None, message=None, gid=None):
    app, api, _ = ui
    gid = gid or uid
    message = message or last_message(ui, gid)
    if route is None:
        route = next(
            b["callback_data"]
            for row in message["reply_markup"]["inline_keyboard"]
            for b in row
            if label in b["text"]
        )
    query = {
        "id": str(len(api.calls) + 1),
        "from": {"id": uid, "first_name": "Reader", "is_bot": False},
        "chat_instance": "instance",
        "message": message,
        "data": route,
    }
    await app.process_update(
        Update.de_json({"update_id": 10000 + len(api.calls), "callback_query": query}, app.bot)
    )


async def test_first_run_form_mark_and_repeat(ui, store):
    await text(ui, 1, "/start")
    await click(ui, 1, "Дальше")
    await click(ui, 1, "Дальше")
    await click(ui, 1, "Продолжить")
    await click(ui, 1, "пустым")
    for value in ("Колобок", "Народ", "100", "25"):
        await text(ui, 1, value)
    assert store.get(1)["books"][0]["title"] == "Колобок"
    await text(ui, 1, "✅")
    await text(ui, 1, "✅")
    assert store.get(1)["books"][0]["page"] == 25
    assert "уже зачтена" in last_message(ui, 1)["text"]
    ui[2].now = lambda: START + timedelta(days=1)
    await text(ui, 1, "✅")
    assert store.get(1)["books"][0]["page"] == 50


async def test_private_navigation_and_stable_forest(ui, store):
    store.ensure(1, "Reader", "UTC", START)
    store.mutate(1, lambda p: d.add_book(p, "<Книга>", "A&B", 100, 25, START))
    await text(ui, 1, "/start")
    await click(ui, 1, "Посмотреть на дерево")
    assert "&lt;Книга&gt;" in last_message(ui, 1)["text"]
    await click(ui, 1, "Мой лес")
    forest = last_message(ui, 1)["text"]
    await click(ui, 1, "Главное дерево")
    await click(ui, 1, "Мой лес")
    assert last_message(ui, 1)["text"] == forest
    await click(ui, 1, "Общая статистика")
    assert "Текущая книга: 1" in last_message(ui, 1)["text"]


async def test_quote_form_duplicates_and_toggle(ui, store):
    store.ensure(1, "Reader", "UTC", START)
    store.mutate(1, lambda p: p.update(onboarded=True))
    await text(ui, 1, "/start")
    await click(ui, 1, "Мотивация")
    await click(ui, 1, "Добавить")
    await text(ui, 1, "6:00")
    assert "ЧЧ:ММ" in last_message(ui, 1)["text"]
    await text(ui, 1, "06:00")
    assert store.get(1)["quote_times"].count("06:00") == 1
    await click(ui, 1, "Выключить")
    assert not store.get(1)["quotes_enabled"]
    assert store.get(1)["quote_times"] == ["06:00", "13:00", "21:00"]


async def test_group_menu_owner_no_reading_and_stale_privacy(ui, store):
    for uid in (1, 2):
        store.ensure(uid, "Reader", "UTC", START)
        store.mutate(uid, lambda p: d.add_book(p, "Секретная книга", "Автор", 100, 25, START))
    store.group(-100, "Test group")
    for uid in (1, 2):
        store.mutate(uid, lambda p: p.update(group_id=-100, show_forest=True, show_stats=True))
    await text(ui, 1, "/start", -100)
    menu = last_message(ui, -100)
    before = len([c for c in ui[1].calls if c[0] == "editMessageMedia"])
    await click(ui, 2, "Пользователи", message=menu, gid=-100)
    assert len([c for c in ui[1].calls if c[0] == "editMessageMedia"]) == before
    assert any(
        "другого" in data.get("text", "")
        for endpoint, data in ui[1].calls
        if endpoint == "answerCallbackQuery"
    )
    await click(ui, 1, "Пользователи", gid=-100)
    await click(
        ui,
        1,
        route=menu["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split("|")[0]
        + "|person:2",
        gid=-100,
    )
    person = last_message(ui, -100)
    await click(ui, 1, "Посмотреть лес", gid=-100)
    assert "участок" in last_message(ui, -100)["caption"]
    store.mutate(2, lambda p: p.update(show_forest=False))
    await click(ui, 1, "Посмотреть лес", message=person, gid=-100)
    assert any(
        "закрыты" in data.get("text", "")
        for endpoint, data in ui[1].calls
        if endpoint == "answerCallbackQuery"
    )
    await text(ui, 1, "✅", -100)
    assert not store.get(1)["marks"]


async def test_group_leave_revokes_old_buttons(ui, store):
    store.ensure(1, "Reader", "UTC", START)
    store.group(-100, "Test group")
    store.mutate(1, lambda p: p.update(group_id=-100, show_forest=True))
    await text(ui, 1, "/start", -100)
    ui[1].memberships[(-100, 1)] = "left"
    await click(ui, 1, "Пользователи", gid=-100)
    assert store.get(1)["group_id"] is None


def test_long_cards_fit_captions_and_callback_data():
    p = d.new_profile(1234567890123456, "Имя" * 33, "UTC", START)
    p["name"] = p["name"][:100]
    b = d.add_book(p, "Название" * 25, "Автор" * 40, 100, 25, START)
    p["tree"] = [list(c) for c in d.TREE_CELLS[:-1]]
    for view in [
        v.book(p, b["id"], private=False),
        v.main_tree(p, private=False),
        v.forest(p, private=False),
        v.stats(p, START, private=False),
    ]:
        from html import unescape
        import re

        rendered = unescape(re.sub(r"<[^>]+>", "", view.text))
        assert len(rendered.encode("utf-16-le")) // 2 <= 1024
        Controller.keyboard("12345678", view.rows)


async def test_group_long_names_and_single_message_navigation(ui, store):
    store.group(-100, "Group")
    for uid in range(1, 5):
        store.ensure(uid, "Я" * 100, "UTC", START)
        store.mutate(uid, lambda p: d.add_book(p, "Длинная книга", "Автор", 100, 25, START))
        store.mutate(uid, lambda p: p.update(group_id=-100, show_forest=True, show_stats=True))
    await text(ui, 1, "/start", -100)
    menu = last_message(ui, -100)
    await click(ui, 1, "Пользователи", gid=-100)
    assert last_message(ui, -100)["message_id"] == menu["message_id"]
    assert len([m for (chat, _), m in ui[1].messages.items() if chat == -100]) == 1


async def test_golden_reward_is_sent_as_image(ui, store):
    store.ensure(1, "Reader", "UTC", START)
    store.mutate(1, lambda p: d.add_book(p, "Книга", "Автор", 100, 25, START))
    store.mutate(1, lambda p: p.update(tree=[list(c) for c in d.TREE_CELLS[:-1]]))
    await text(ui, 1, "✅")
    assert store.get(1)["golden"]
    assert "photo" in last_message(ui, 1)
    assert "Золотое дерево" in last_message(ui, 1)["caption"]


async def test_group_consent_required_and_private_default(ui, store):
    store.ensure(1, "Reader", "UTC", START)
    store.group(-100, "Group")
    await text(ui, 1, "/start g_100")
    assert store.get(1)["group_id"] is None
    await click(ui, 1, "Подключиться")
    p = store.get(1)
    assert p["group_id"] == -100 and not p["show_forest"] and not p["show_stats"]
