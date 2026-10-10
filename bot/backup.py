"""Strict versioned backup validation, performed before any replacement."""

import copy
import json
import re
from datetime import UTC, date, datetime, timedelta

from . import domain as d

MAX_BACKUP_BYTES = 5 * 1024 * 1024


def backup_integer(value, minimum=0, maximum=1_000_000):
    if type(value) is not int:
        raise d.RuleError("Числовые поля экспорта должны быть целыми числами JSON.")
    return d.integer(value, minimum, maximum)


def parse_backup(raw: bytes, uid: int, now: datetime) -> dict:
    if len(raw) > MAX_BACKUP_BYTES:
        raise d.RuleError("Файл слишком большой. Максимум — 5 МБ.")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise d.RuleError("Нужен корректный JSON-файл экспорта LibraryBot.") from exc
    validate_backup(payload, uid, now)
    return payload


def validate_backup(payload: dict, uid: int, now: datetime) -> dict:
    try:
        return _validate(payload, uid, now)
    except d.RuleError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise d.RuleError("Файл содержит неполные или недопустимые данные профиля.") from exc


def _validate(payload, uid, now):
    if (
        payload["format"] != "LibraryBot"
        or type(payload["version"]) is not int
        or payload["version"] != 1
    ):
        raise d.RuleError("Версия или формат экспорта не поддерживается.")
    if (
        type(payload["owner_id"]) is not int
        or type(payload["profile"]["owner_id"]) is not int
        or payload["owner_id"] != uid
        or payload["profile"]["owner_id"] != uid
    ):
        raise d.RuleError("Этот экспорт принадлежит другому пользователю Telegram.")
    p = copy.deepcopy(payload["profile"])
    expected = set(d.new_profile(uid, "", "UTC", now))
    if set(p) != expected:
        raise d.RuleError("Набор полей профиля не соответствует версии 1.")
    d.validate_timezone(p["timezone"])
    if not isinstance(p["name"], str) or not 1 <= len(p["name"]) <= 100:
        raise ValueError("name")
    for key in ("onboarded", "show_forest", "show_stats", "reminders", "quotes_enabled", "golden"):
        if not isinstance(p[key], bool):
            raise ValueError(key)
    for key in ("streak", "best", "coins", "revision"):
        backup_integer(p[key])
    if p["streak"] > p["best"] or not re.fullmatch(r"[0-9a-f]{32}", p["series_id"]):
        raise ValueError("series")
    if len(p["quote_times"]) > 24 or len(set(p["quote_times"])) != len(p["quote_times"]):
        raise ValueError("times")
    for value in p["quote_times"]:
        d.validate_time(value)

    def timestamp(value):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed > now + timedelta(days=2):
            raise ValueError("timestamp")
        return parsed.astimezone(UTC)

    if timestamp(p["registered_at"]) > now:
        raise ValueError("registration")
    timestamp(payload["exported_at"])
    if p["next_mark_at"]:
        timestamp(p["next_mark_at"])
    current = d.today(p, now)
    for key in ("closed_through", "last_mark_date", "free_day"):
        if p[key] and date.fromisoformat(p[key]) > current + timedelta(days=1):
            raise ValueError(key)
    books, positions = {}, set()
    if not isinstance(p["books"], list) or len(p["books"]) > 10000:
        raise ValueError("books")
    for b in p["books"]:
        if set(b) != {
            "id",
            "title",
            "author",
            "total",
            "norm",
            "page",
            "status",
            "start",
            "end",
            "streak",
            "best",
            "plot",
            "x",
            "y",
            "seed",
        }:
            raise ValueError("book fields")
        if not re.fullmatch(r"[0-9a-f]{12}", b["id"]) or b["id"] in books:
            raise ValueError("book id")
        books[b["id"]] = b
        for key in ("title", "author"):
            if not isinstance(b[key], str) or not 1 <= len(b[key]) <= 200:
                raise ValueError(key)
        for key in ("total", "norm"):
            backup_integer(b[key], 1)
        backup_integer(b["page"], 0, b["total"])
        for key in ("streak", "best", "plot"):
            backup_integer(b[key])
        backup_integer(b["seed"], 0, 2**31 - 1)
        backup_integer(b["x"], 0, 8)
        backup_integer(b["y"], 0, 6)
        pos = (b["plot"], b["x"], b["y"])
        if pos in positions or pos[1:] == (4, 3):
            raise ValueError("position")
        positions.add(pos)
        if b["status"] not in {"active", "paused", "completed"} or b["streak"] > b["best"]:
            raise ValueError("book status")
        if date.fromisoformat(b["start"]) > current:
            raise ValueError("start")
        if (
            b["end"]
            and not date.fromisoformat(b["start"]) <= date.fromisoformat(b["end"]) <= current
        ):
            raise ValueError("end")
        if (b["status"] == "completed") != (b["page"] == b["total"]):
            raise ValueError("completion")
        if (b["status"] == "completed") != bool(b["end"]):
            raise ValueError("end status")
    if sum(b["status"] == "active" for b in p["books"]) > 1:
        raise ValueError("active")
    days = set()
    for mark in p["marks"]:
        if set(mark) != {"day", "book_id", "pages", "at"}:
            raise ValueError("mark fields")
        day = date.fromisoformat(mark["day"])
        if day > current or mark["day"] in days:
            raise ValueError("mark day")
        days.add(mark["day"])
        timestamp(mark["at"])
        backup_integer(mark["pages"])
        if mark["book_id"] is not None and mark["book_id"] not in books:
            raise ValueError("mark book")
        if mark["book_id"] is None and mark["pages"] != 0:
            raise ValueError("tombstone")
    if p["last_mark_date"] != (max(days) if days else None):
        raise ValueError("last mark")
    if p["best"] > len(days):
        raise ValueError("best")
    cells = set()
    allowed = set(d.TREE_CELLS)
    if not isinstance(p["tree"], list) or len(p["tree"]) > d.MAX_GROWTH:
        raise ValueError("tree")
    for cell in p["tree"]:
        if len(cell) != 3 or type(cell[0]) is not int or type(cell[1]) is not int:
            raise ValueError("cell types")
        if len(cell) != 3 or tuple(cell) not in allowed or tuple(cell[:2]) in cells:
            raise ValueError("cell")
        cells.add(tuple(cell[:2]))
    if p["golden"] != (len(p["tree"]) == d.MAX_GROWTH):
        raise ValueError("gold")
    event_ids, balance = set(), 0
    reward_marks = set()
    for event in p["coin_events"]:
        if set(event) != {"id", "delta", "kind", "at"} or event["id"] in event_ids:
            raise ValueError("coin event")
        if not isinstance(event["id"], str) or len(event["id"]) > 100:
            raise ValueError("coin id")
        event_ids.add(event["id"])
        timestamp(event["at"])
        if event["kind"] not in {"reward", "fertilize", "protection"}:
            raise ValueError("coin kind")
        if event["kind"] == "reward":
            reward = re.fullmatch(r"reward:[0-9a-f]{32}:([0-9]+)", event["id"])
            if not reward or int(reward[1]) < 10 or int(reward[1]) % 10:
                raise ValueError("reward id")
            if event["at"] not in {m["at"] for m in p["marks"]} or event["at"] in reward_marks:
                raise ValueError("reward mark")
            reward_marks.add(event["at"])
        if event["kind"] == "fertilize" and not re.fullmatch(
            r"fertilize:(?:[0-9a-f]{12}|[0-9a-f]{16})", event["id"]
        ):
            raise ValueError("fertilizer id")
        if event["kind"] == "protection":
            if not event["id"].startswith("protect:"):
                raise ValueError("protection id")
            date.fromisoformat(event["id"][8:])
        if type(event["delta"]) is not int or event["delta"] != (
            1 if event["kind"] == "reward" else -1
        ):
            raise ValueError("coin delta")
        balance += event["delta"]
        if balance < 0:
            raise ValueError("coin balance")
    if balance != p["coins"]:
        raise ValueError("coins")
    if len(reward_marks) > len(p["marks"]) // 10:
        raise ValueError("reward count")
    protection_days = set()
    for event in p["protections"]:
        if set(event) != {"day", "kind", "coins"} or event["day"] in protection_days:
            raise ValueError("protection fields")
        protection_days.add(event["day"])
        if date.fromisoformat(event["day"]) > current or event["day"] in days:
            raise ValueError("protection day")
        if event["kind"] not in {"free", "coin", "lost"}:
            raise ValueError("protection kind")
        backup_integer(event["coins"])
    return p
