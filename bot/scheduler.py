"""Personal schedules, midnight recovery and an at-most-once delivery outbox."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from . import domain as d

logger = logging.getLogger(__name__)
REMINDER_TIMES = {"18:00", "20:00", "21:00", "22:00"}


def marked_today(p, now):
    return p["last_mark_date"] == d.today(p, now).isoformat() or (
        p["next_mark_at"] is not None and now < datetime.fromisoformat(p["next_mark_at"])
    )


class Scheduler:
    def __init__(self, store, quotes):
        self.store, self.quotes = store, quotes
        self.last_tick = None

    def prepare(self, uid, now):
        with self.store.locked(uid) as (conn, ps):
            p = ps[uid]
            for event in d.settle_days(p, now):
                self.store.enqueue(
                    conn,
                    uid,
                    "boundary:" + event["day"],
                    {**event, "kind": "boundary", "result": event["kind"]},
                )
            local = now.astimezone(ZoneInfo(p["timezone"]))
            day, slot = local.date().isoformat(), local.strftime("%H:%M")
            if p["quotes_enabled"] and slot in p["quote_times"]:
                self.store.enqueue(
                    conn, uid, f"quote:{day}:{slot}", {"kind": "quote", "day": day, "slot": slot}
                )
            if p["reminders"] and not marked_today(p, now):
                book = d.active_book(p)
                if (book and slot in REMINDER_TIMES) or (not book and slot == "18:00"):
                    self.store.enqueue(
                        conn,
                        uid,
                        f"reminder:{day}:{slot}",
                        {"kind": "reminder" if book else "choose", "day": day, "slot": slot},
                    )

    def claim(self):
        with self.store.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "SELECT * FROM deliveries WHERE status='pending' "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE deliveries SET status='sending',attempts=attempts+1 WHERE id=%s",
                    (row["id"],),
                )
        return row

    def finish(self, row_id, status):
        with self.store.pool.connection() as conn:
            conn.execute(
                "UPDATE deliveries SET status=%s,sent_at=CASE WHEN %s='sent' THEN now() "
                "ELSE sent_at END WHERE id=%s",
                (status, status, row_id),
            )

    def message(self, uid, event, now):
        p = self.store.get(uid)
        kind = event["kind"]
        if kind in {"quote", "reminder", "choose"}:
            local = now.astimezone(ZoneInfo(p["timezone"]))
            if local.date().isoformat() != event["day"]:
                return None
            scheduled = datetime.fromisoformat(event["day"] + "T" + event["slot"]).replace(
                tzinfo=local.tzinfo
            )
            if not timedelta(0) <= local - scheduled <= timedelta(minutes=5):
                return None
            if kind == "quote":
                if not p["quotes_enabled"] or event["slot"] not in p["quote_times"]:
                    return None
                return "🕒 " + event["slot"] + "\n\n«" + self.quotes.get_random() + "»"
            if not p["reminders"] or marked_today(p, now):
                return None
            book = d.active_book(p)
            if not book:
                return (
                    "Выбери следующую книгу, чтобы продолжить выращивать своё главное дерево."
                    if event["slot"] == "18:00"
                    else None
                )
            return "Сегодня ещё нет отметки. Прочитай свою норму и отправь мне ✅."
        if kind == "boundary":
            result = {
                "free": "Применена бесплатная защита после завершения книги. Серия и дерево сохранены без роста.",
                "coin": "За пропуск потрачена одна монета. Серия и дерево сохранены без роста.",
                "lost": "Защиты не было: текущая серия обнулилась. Обычное главное дерево начнётся заново. Книги, рекорд и золотая награда сохраняются.",
            }[event["result"]]
            return f"День {event['day']}\n{result}\nМонеты после обработки: {event['coins']}"
        if kind == "gift":
            return f"{event['name']} помог твоему главному дереву: +1 символ." + (
                "\n🏆 Теперь оно золотое!" if event["golden"] else ""
            )
        return None

    async def tick(self, context):
        now = datetime.now(UTC)
        try:
            for uid in await asyncio.to_thread(self.store.users):
                await asyncio.to_thread(self.prepare, uid, now)
            self.last_tick = now
            await self.dispatch(context.bot, now)
        except Exception as exc:
            logger.error("Scheduler failed: %s", type(exc).__name__)

    async def dispatch(self, bot, now):
        for _ in range(100):
            row = await asyncio.to_thread(self.claim)
            if row is None:
                break
            text = await asyncio.to_thread(self.message, row["user_id"], row["payload"], now)
            if not text:
                await asyncio.to_thread(self.finish, row["id"], "cancelled")
                continue
            try:
                if row["payload"]["kind"] == "gift" and row["payload"]["golden"]:
                    with (
                        Path(__file__).resolve().parent.parent / "assets" / "golden-tree.png"
                    ).open("rb") as photo:
                        await bot.send_photo(row["user_id"], photo, caption=text)
                else:
                    await bot.send_message(row["user_id"], text)
                await asyncio.to_thread(self.finish, row["id"], "sent")
            except RetryAfter as exc:
                # Telegram explicitly rejected this request; a retry cannot duplicate it.
                await asyncio.to_thread(self.finish, row["id"], "pending")
                delay = (
                    exc.retry_after.total_seconds()
                    if isinstance(exc.retry_after, timedelta)
                    else exc.retry_after
                )
                await asyncio.sleep(min(float(delay), 30))
                break
            except (Forbidden, BadRequest):
                await asyncio.to_thread(self.finish, row["id"], "failed")
            except NetworkError:
                # Bot API has no idempotency key. A timeout may mean the message arrived.
                await asyncio.to_thread(self.finish, row["id"], "uncertain")
            except TelegramError:
                await asyncio.to_thread(self.finish, row["id"], "failed")
            await asyncio.sleep(0.04)
