"""Transactional use cases. Profile locks protect dependent updates."""

from . import domain as d


class Service:
    def __init__(self, store):
        self.store = store

    def mark(self, uid, now):
        self.store.settle(uid, now)
        with self.store.locked(uid) as (conn, profiles):
            p = profiles[uid]
            day = d.today(p, now)
            if conn.execute(
                "SELECT 1 FROM reading_days WHERE user_id=%s AND local_day=%s", (uid, day)
            ).fetchone():
                raise d.RuleError("Сегодняшняя отметка уже зачтена.")
            result = d.mark_reading(p, now)
            conn.execute(
                "INSERT INTO reading_days(user_id,local_day,read_at) VALUES (%s,%s,%s)",
                (uid, day, now),
            )
            return result

    def can_view(self, viewer, target, kind, group_id):
        if group_id is None:
            return viewer == target
        a, b = self.store.get(viewer), self.store.get(target)
        return a["group_id"] == group_id == b["group_id"] and b["show_" + kind]

    def fertilize(self, uid, token, now):
        payload = self.store.peek_action(token, uid, "fertilize")
        target = payload["target"]
        with self.store.locked(uid, target) as (conn, ps):
            self.store.consume(conn, token, uid, "fertilize", now)
            a, b = ps[uid], ps[target]
            if uid != target and (
                a["group_id"] is None or a["group_id"] != b["group_id"] or not b["show_forest"]
            ):
                raise d.RuleError("Лес участника больше недоступен.")
            if b["golden"] or len(b["tree"]) >= d.MAX_GROWTH:
                raise d.RuleError("Дерево уже золотое. Монета не потрачена.")
            d.coin_event(a, "fertilize:" + token, -1, "fertilize", now)
            d.grow(b)
            if target != uid:
                self.store.enqueue(
                    conn,
                    target,
                    "gift:" + token,
                    {"kind": "gift", "name": a["name"], "golden": b["golden"]},
                )
            return target, b["golden"]

    def delete(self, uid, token, now):
        with self.store.locked(uid) as (conn, ps):
            payload = self.store.consume(conn, token, uid, "delete", now)
            d.delete_book(ps[uid], payload["book_id"])

    def connect(self, uid, token, now):
        with self.store.locked(uid) as (conn, ps):
            payload = self.store.consume(conn, token, uid, "connect", now)
            if ps[uid]["group_id"] is not None:
                raise d.RuleError("Сначала отключись от текущей группы в настройках.")
            self.store.group_title(payload["group_id"])
            ps[uid]["group_id"] = payload["group_id"]

    def disconnect(self, uid, token, now):
        with self.store.locked(uid) as (conn, ps):
            self.store.consume(conn, token, uid, "disconnect", now)
            ps[uid]["group_id"] = None

    def export(self, uid, now):
        p = self.store.get(uid)
        p.pop("group_id", None)
        return {
            "format": "LibraryBot",
            "version": 1,
            "exported_at": d.iso(now),
            "owner_id": uid,
            "profile": p,
        }

    def import_profile(self, uid, token, now):
        from .backup import validate_backup

        with self.store.locked(uid) as (conn, ps):
            payload = self.store.consume(conn, token, uid, "import", now)
            imported = validate_backup(payload, uid, now)
            current = ps[uid]
            imported_events = {e["id"]: e for e in imported["coin_events"]}
            for event in current["coin_events"]:
                if imported_events.get(event["id"]) != event:
                    raise d.RuleError("Файл старее текущих операций монет. Сделай свежий экспорт.")
            rows = conn.execute(
                "SELECT local_day FROM reading_days WHERE user_id=%s", (uid,)
            ).fetchall()
            days = {m["day"] for m in imported["marks"]}
            if any(r["local_day"].isoformat() not in days for r in rows):
                raise d.RuleError(
                    "В файле отсутствуют уже зачтённые дни. Используй свежий экспорт."
                )
            imported["group_id"] = None
            imported["revision"] = current["revision"]
            imported["onboarded"] = True
            ps[uid] = imported
            for mark in imported["marks"]:
                conn.execute(
                    "INSERT INTO reading_days(user_id,local_day,read_at) VALUES (%s,%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (uid, mark["day"], mark["at"]),
                )
            conn.execute(
                "UPDATE deliveries SET status='cancelled' WHERE user_id=%s AND status='pending'",
                (uid,),
            )
            conn.execute("UPDATE actions SET consumed=true WHERE owner_id=%s", (uid,))
