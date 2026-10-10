"""Pure reading rules. UTC timestamps; local calendar days."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_GROWTH = 365
STAGES = [
    (20, "🌱", "Росток"),
    (40, "🌿", "Молодой побег"),
    (60, "🪴", "Подросшее растение"),
    (100, "🌳", "Взрослеющее дерево"),
    (101, "🌲", "Завершённое дерево"),
]


class RuleError(ValueError):
    """A user-readable rule failure."""


def iso(now: datetime) -> str:
    return now.astimezone(UTC).isoformat()


def today(p: dict, now: datetime) -> date:
    return now.astimezone(ZoneInfo(p["timezone"])).date()


def new_profile(uid: int, name: str, timezone: str, now: datetime) -> dict:
    validate_timezone(timezone)
    return {
        "owner_id": uid,
        "name": name[:100],
        "registered_at": iso(now),
        "timezone": timezone,
        "onboarded": False,
        "show_forest": False,
        "show_stats": False,
        "reminders": True,
        "quotes_enabled": True,
        "quote_times": ["06:00", "13:00", "21:00"],
        "books": [],
        "marks": [],
        "protections": [],
        "coin_events": [],
        "streak": 0,
        "best": 0,
        "coins": 0,
        "series_id": uuid.uuid4().hex,
        "tree": [],
        "golden": False,
        "last_mark_date": None,
        "next_mark_at": None,
        "closed_through": (today({"timezone": timezone}, now) - timedelta(days=1)).isoformat(),
        "free_day": None,
        "revision": 0,
    }


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise RuleError("Неизвестный часовой пояс. Пример: Asia/Chita или Europe/Moscow.") from exc
    return value


def validate_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (ValueError, TypeError) as exc:
        raise RuleError("Введи время в формате ЧЧ:ММ, например 06:00.") from exc
    if parsed.strftime("%H:%M") != value:
        raise RuleError("Нужен формат ЧЧ:ММ, например 06:00.")
    return value


def integer(value, minimum=0, maximum=1_000_000) -> int:
    if isinstance(value, bool):
        raise RuleError("Нужно целое число.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RuleError("Нужно целое число.") from exc
    if str(result) != str(value) or not minimum <= result <= maximum:
        raise RuleError(f"Введи целое число от {minimum} до {maximum}.")
    return result


def active_book(p: dict) -> dict | None:
    return next((b for b in p["books"] if b["status"] == "active"), None)


def book_by_id(p: dict, book_id: str) -> dict:
    book = next((b for b in p["books"] if b["id"] == book_id), None)
    if book is None:
        raise RuleError("Эта книга уже удалена или недоступна.")
    return book


def stage(b: dict) -> tuple[str, str]:
    percent = b["page"] / b["total"] * 100
    return next((emoji, title) for bound, emoji, title in STAGES if percent < bound)


def add_book(p: dict, title: str, author: str, total, norm, now: datetime) -> dict:
    if not title.strip() or not author.strip() or len(title) > 200 or len(author) > 200:
        raise RuleError("Название и автор должны содержать от 1 до 200 символов.")
    total, norm = integer(total, 1), integer(norm, 1)
    pause_book(p)
    used = {(b["plot"], b["x"], b["y"]) for b in p["books"]}
    plot = 0
    while True:
        slots = [
            (plot, x, y)
            for y in range(7)
            for x in range(9)
            if (x, y) != (4, 3) and (plot, x, y) not in used
        ]
        if slots:
            plot, x, y = random.choice(slots)
            break
        plot += 1
    book = {
        "id": uuid.uuid4().hex[:12],
        "title": title.strip(),
        "author": author.strip(),
        "total": total,
        "norm": norm,
        "page": 0,
        "status": "active",
        "start": today(p, now).isoformat(),
        "end": None,
        "streak": 0,
        "best": 0,
        "plot": plot,
        "x": x,
        "y": y,
        "seed": random.randrange(2**31),
    }
    p["books"].append(book)
    p["onboarded"] = True
    return book


def pause_book(p: dict) -> None:
    b = active_book(p)
    if b:
        b["status"] = "paused"
        b["streak"] = 0


def resume_book(p: dict, book_id: str) -> None:
    b = book_by_id(p, book_id)
    if b["status"] == "completed":
        raise RuleError("Книга уже завершена. Добавь следующую книгу.")
    if b["status"] == "active":
        return
    pause_book(p)
    b["status"], b["streak"] = "active", 0


def edit_book(p: dict, book_id: str, field: str, value, now: datetime) -> None:
    b = book_by_id(p, book_id)
    if field in {"title", "author"}:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
            raise RuleError("Нужно от 1 до 200 символов.")
        b[field] = value.strip()
    elif field in {"total", "norm", "page"}:
        n = integer(value, 0 if field == "page" else 1)
        if field == "page" and n > b["total"]:
            raise RuleError("Текущая страница не может быть больше объёма книги.")
        if field == "total" and n < b["page"]:
            raise RuleError("Объём не может быть меньше уже прочитанной страницы.")
        b[field] = n
        if b["page"] == b["total"]:
            b["status"], b["end"] = "completed", today(p, now).isoformat()
        elif b["status"] == "completed":
            b["status"], b["end"], b["streak"] = "paused", None, 0
    elif field == "start":
        try:
            dt = date.fromisoformat(value)
        except (ValueError, TypeError) as exc:
            raise RuleError("Введи дату в формате ГГГГ-ММ-ДД.") from exc
        if dt > today(p, now) or (b["end"] and dt > date.fromisoformat(b["end"])):
            raise RuleError("Дата начала не может быть в будущем или после завершения.")
        b["start"] = dt.isoformat()
    else:
        raise RuleError("Неизвестный параметр книги.")


def tree_positions() -> list[tuple[int, int, str]]:
    trunk = [(15, y, "|") for y in range(22, 5, -1)]
    branches = [(15 - i, 15 - i // 2, "/") for i in range(1, 12)]
    branches += [(15 + i, 13 - i // 2, "\\") for i in range(1, 12)]
    canopy = [
        (x, y, "*")
        for y in range(0, 16)
        for x in range(1, 30)
        if ((x - 15) / 15) ** 2 + ((y - 7) / 9) ** 2 <= 1
    ]
    rng = random.Random(365)
    rng.shuffle(canopy)
    result, seen = [], set()
    for cell in trunk + branches + canopy:
        if cell[:2] not in seen:
            seen.add(cell[:2])
            result.append(cell)
    return result[:MAX_GROWTH]


TREE_CELLS = tree_positions()


def grow(p: dict) -> bool:
    if p["golden"] or len(p["tree"]) >= MAX_GROWTH:
        return False
    used = {(c[0], c[1]) for c in p["tree"]}
    candidates = [c for c in TREE_CELLS if c[:2] not in used]
    near = [c for c in candidates if any(abs(c[0] - x) + abs(c[1] - y) <= 2 for x, y in used)]
    cell = random.choice(near) if near else candidates[0]
    p["tree"].append(list(cell))
    p["golden"] = len(p["tree"]) == MAX_GROWTH
    return True


def render_tree(p: dict) -> str:
    if not p["tree"]:
        return "·"
    canvas = [[" " for _ in range(31)] for _ in range(23)]
    for x, y, char in p["tree"]:
        canvas[y][x] = char
    lines = ["".join(row).rstrip() for row in canvas]
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines)


def coin_event(p: dict, key: str, delta: int, kind: str, now: datetime) -> None:
    if any(e["id"] == key for e in p["coin_events"]):
        raise RuleError("Эта операция уже выполнена.")
    if p["coins"] + delta < 0:
        raise RuleError("Недостаточно монет.")
    p["coins"] += delta
    p["coin_events"].append({"id": key, "delta": delta, "kind": kind, "at": iso(now)})


def settle_days(p: dict, now: datetime) -> list[dict]:
    last_closed = today(p, now) - timedelta(days=1)
    cursor = date.fromisoformat(p["closed_through"]) + timedelta(days=1)
    marks = {m["day"] for m in p["marks"]}
    events = []
    while cursor <= last_closed:
        day = cursor.isoformat()
        if day not in marks and p["streak"] > 0:
            if p["free_day"] == day:
                kind = "free"
            elif p["coins"] > 0:
                kind = "coin"
                coin_event(p, "protect:" + day, -1, "protection", now)
            else:
                kind = "lost"
                p["streak"] = 0
                p["series_id"] = uuid.uuid4().hex
                if not p["golden"]:
                    p["tree"] = []
                b = active_book(p)
                if b:
                    b["streak"] = 0
            event = {"day": day, "kind": kind, "coins": p["coins"]}
            p["protections"].append(event)
            events.append(event)
        p["closed_through"] = day
        cursor += timedelta(days=1)
    return events


def mark_reading(p: dict, now: datetime) -> dict:
    settle_days(p, now)
    day = today(p, now).isoformat()
    if (
        any(m["day"] == day for m in p["marks"])
        or (p["last_mark_date"] and day <= p["last_mark_date"])
        or (p["next_mark_at"] and now < datetime.fromisoformat(p["next_mark_at"]))
    ):
        raise RuleError("Сегодняшняя отметка уже зачтена. Следующая — в новый читательский день.")
    b = active_book(p)
    if not b:
        raise RuleError("Сейчас ты не читаешь. Выбери книгу в настройках.")
    pages = min(b["norm"], b["total"] - b["page"])
    b["page"] += pages
    b["streak"] += 1
    b["best"] = max(b["best"], b["streak"])
    p["streak"] += 1
    p["best"] = max(p["best"], p["streak"])
    was_golden = p["golden"]
    grow(p)
    mark = {"day": day, "book_id": b["id"], "pages": pages, "at": iso(now)}
    p["marks"].append(mark)
    p["last_mark_date"] = day
    boundary = datetime.combine(today(p, now) + timedelta(days=1), time(), ZoneInfo(p["timezone"]))
    p["next_mark_at"] = iso(boundary)
    rewarded = p["streak"] % 10 == 0
    if rewarded:
        coin_event(p, f"reward:{p['series_id']}:{p['streak']}", 1, "reward", now)
    completed = b["page"] == b["total"]
    if completed:
        b["status"], b["end"] = "completed", day
        p["free_day"] = (today(p, now) + timedelta(days=1)).isoformat()
    return {
        "pages": pages,
        "book": b.copy(),
        "completed": completed,
        "rewarded": rewarded,
        "golden": p["golden"],
        "golden_new": p["golden"] and not was_golden,
    }


def change_timezone(p: dict, timezone: str, now: datetime) -> None:
    validate_timezone(timezone)
    settle_days(p, now)
    p["timezone"] = timezone
    new_closed = (today(p, now) - timedelta(days=1)).isoformat()
    p["closed_through"] = max(p["closed_through"], new_closed)


def delete_book(p: dict, book_id: str) -> None:
    b = book_by_id(p, book_id)
    p["books"].remove(b)
    for m in p["marks"]:
        if m["book_id"] == book_id:
            m["book_id"], m["pages"] = None, 0


def statistics(p: dict, now: datetime) -> dict:
    return {
        "completed": sum(b["status"] == "completed" for b in p["books"]),
        "paused": sum(b["status"] == "paused" for b in p["books"]),
        "active": sum(b["status"] == "active" for b in p["books"]),
        "pages": sum(m["pages"] for m in p["marks"] if m["book_id"]),
        "stages": {title: sum(stage(b)[1] == title for b in p["books"]) for _, _, title in STAGES},
        "days": max(0, (now - datetime.fromisoformat(p["registered_at"])).days),
    }
