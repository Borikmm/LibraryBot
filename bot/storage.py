"""PostgreSQL repository with row locks and durable idempotency records."""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .domain import RuleError, new_profile, settle_days


class Store:
    def __init__(self, dsn: str):
        self.pool = ConnectionPool(
            dsn, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True
        )
        self.pool.wait(timeout=15)

    def migrate(self):
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(76365001)")
            for path in sorted(
                (Path(__file__).resolve().parent.parent / "migrations").glob("*.sql")
            ):
                conn.execute(path.read_text(encoding="utf-8"))

    def close(self):
        self.pool.close()

    def ensure(self, uid: int, name: str, timezone: str, now: datetime) -> dict:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO profiles(user_id,data) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (uid, Jsonb(new_profile(uid, name, timezone, now))),
            )
        return self.get(uid)

    def get(self, uid: int) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE user_id=%s", (uid,)).fetchone()
        if not row:
            raise RuleError("Сначала запусти бота в личных сообщениях командой /start.")
        return {**row["data"], "group_id": row["group_id"]}

    def users(self, group_id=None) -> list[int]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT user_id FROM profiles"
                if group_id is None
                else "SELECT user_id FROM profiles WHERE group_id=%s ORDER BY user_id",
                () if group_id is None else (group_id,),
            ).fetchall()
        return [r["user_id"] for r in rows]

    @contextmanager
    def locked(self, *uids: int):
        with self.pool.connection() as conn, conn.transaction():
            profiles = {}
            for uid in sorted(set(uids)):
                row = conn.execute(
                    "SELECT * FROM profiles WHERE user_id=%s FOR UPDATE", (uid,)
                ).fetchone()
                if not row:
                    raise RuleError("Профиль недоступен. Открой /start в ЛС.")
                profiles[uid] = {**row["data"], "group_id": row["group_id"]}
            yield conn, profiles
            for uid, data in profiles.items():
                group_id = data.pop("group_id", None)
                data["revision"] += 1
                conn.execute(
                    "UPDATE profiles SET data=%s,group_id=%s,updated_at=now() WHERE user_id=%s",
                    (Jsonb(data), group_id, uid),
                )

    def mutate(self, uid, function):
        with self.locked(uid) as (_, profiles):
            return function(profiles[uid])

    @staticmethod
    def enqueue(conn, uid, key, payload):
        conn.execute(
            "INSERT INTO deliveries(user_id,event_key,payload) VALUES (%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (uid, key, Jsonb(payload)),
        )

    def settle(self, uid, now):
        with self.locked(uid) as (conn, profiles):
            events = settle_days(profiles[uid], now)
            for event in events:
                self.enqueue(conn, uid, "boundary:" + event["day"], {"kind": "boundary", **event})
            return events

    def action(self, uid, kind, payload, now=None) -> str:
        token = secrets.token_hex(6)
        now = now or datetime.now(UTC)
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO actions(token,owner_id,kind,payload,expires_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (token, uid, kind, Jsonb(payload), now + timedelta(minutes=30)),
            )
        return token

    @staticmethod
    def consume(conn, token, uid, kind, now):
        row = conn.execute("SELECT * FROM actions WHERE token=%s FOR UPDATE", (token,)).fetchone()
        if not row or row["owner_id"] != uid or row["kind"] != kind:
            raise RuleError("Недоступное подтверждение.")
        if row["consumed"]:
            raise RuleError("Это действие уже выполнено или отменено.")
        if row["expires_at"] < now:
            raise RuleError("Подтверждение устарело. Открой действие ещё раз.")
        conn.execute("UPDATE actions SET consumed=true WHERE token=%s", (token,))
        return row["payload"]

    def peek_action(self, token, uid, kind):
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM actions WHERE token=%s AND owner_id=%s "
                "AND kind=%s AND NOT consumed",
                (token, uid, kind),
            ).fetchone()
        if not row:
            raise RuleError("Подтверждение недоступно или уже выполнено.")
        return row["payload"]

    def cancel_action(self, token, uid):
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE actions SET consumed=true WHERE token=%s AND owner_id=%s", (token, uid)
            )

    def create_menu(self, uid, chat_id) -> str:
        token = secrets.token_hex(4)
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO menus(token,owner_id,chat_id) VALUES (%s,%s,%s)", (token, uid, chat_id)
            )
        return token

    def bind_menu(self, token, message_id):
        with self.pool.connection() as conn:
            conn.execute("UPDATE menus SET message_id=%s WHERE token=%s", (message_id, token))

    def menu(self, token, uid, chat_id, message_id):
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM menus WHERE token=%s", (token,)).fetchone()
        if (
            not row
            or row["owner_id"] != uid
            or row["chat_id"] != chat_id
            or row["message_id"] != message_id
        ):
            raise RuleError("Это меню другого участника. Создай своё командой /start.")
        return row

    def group(self, chat_id, title):
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "INSERT INTO groups(chat_id,title) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING chat_id",
                (chat_id, title),
            ).fetchone()
            conn.execute("UPDATE groups SET title=%s WHERE chat_id=%s", (title, chat_id))
            return bool(row)

    def group_title(self, chat_id):
        with self.pool.connection() as conn:
            row = conn.execute("SELECT title FROM groups WHERE chat_id=%s", (chat_id,)).fetchone()
        if not row:
            raise RuleError("Группа ещё не активирована командой /start.")
        return row["title"]
