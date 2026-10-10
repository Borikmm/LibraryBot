from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import domain as d
from bot.scheduler import Scheduler
from bot.service import Service
from test_domain import START


def setup(store, book=True):
    store.ensure(1, "Reader", "UTC", START)
    if book:
        store.mutate(1, lambda p: d.add_book(p, "Книга", "Автор", 1000, 25, START))
    return Scheduler(store, SimpleNamespace(get_random=lambda: "Читай"))


@pytest.mark.parametrize("hour", [18, 20, 21, 22])
async def test_reminders_stop_after_mark(store, hour):
    scheduler = setup(store)
    now = START.replace(hour=hour)
    scheduler.prepare(1, now)
    scheduler.prepare(1, now)
    Service(store).mark(1, now)
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler.dispatch(bot, now)
    texts = [call.args[1] for call in bot.send_message.call_args_list]
    assert not any("отметки" in t for t in texts)
    assert len(texts) == (1 if hour == 21 else 0)


async def test_no_book_one_reminder_and_disabled_quotes(store):
    scheduler = setup(store, book=False)
    store.mutate(1, lambda p: p.update(quotes_enabled=False))
    bot = SimpleNamespace(send_message=AsyncMock())
    for hour in (18, 20, 21, 22):
        now = START.replace(hour=hour)
        scheduler.prepare(1, now)
        scheduler.prepare(1, now)
        await scheduler.dispatch(bot, now)
    assert bot.send_message.call_count == 1
    assert "Выбери" in bot.send_message.call_args.args[1]


async def test_timezone_and_delivery_idempotency(store):
    scheduler = setup(store)
    store.mutate(1, lambda p: p.update(timezone="Asia/Chita"))
    now = START.replace(hour=21)  # 06:00 next day in Chita
    scheduler.prepare(1, now)
    scheduler.prepare(1, now)
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler.dispatch(bot, now)
    await scheduler.dispatch(bot, now)
    assert bot.send_message.call_count == 1
    assert "06:00" in bot.send_message.call_args.args[1]


async def test_midnight_notification_once_after_restart(store):
    scheduler = setup(store)
    Service(store).mark(1, START)
    now = START + timedelta(days=3)
    scheduler.prepare(1, now)
    scheduler.prepare(1, now)
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler.dispatch(bot, now)
    await Scheduler(store, scheduler.quotes).dispatch(bot, now)
    assert bot.send_message.call_count == 1
    assert "обнулилась" in bot.send_message.call_args.args[1]


async def test_ambiguous_send_not_replayed(store):
    from telegram.error import NetworkError

    scheduler = setup(store)
    now = START.replace(hour=18)
    scheduler.prepare(1, now)
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=NetworkError("timeout")))
    await scheduler.dispatch(bot, now)
    await scheduler.dispatch(bot, now)
    assert bot.send_message.call_count == 1
    with store.pool.connection() as conn:
        assert conn.execute("SELECT status FROM deliveries").fetchone()["status"] == "uncertain"
