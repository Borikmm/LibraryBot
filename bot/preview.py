"""Opt-in, expiring local owner preview, separate from reading records."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from .bonsai import Tree, generate_tree, render_tree
from .config import BASE_DIR
from .views import View

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Preview:
    tree: Tree
    parts: int
    expires_at: str

    def view(self):
        return View(
            f"<b>🧪 Просмотр роста · {self.parts}/365</b>\n"
            "Каждая ✅ добавляет одну часть. Это тестовое дерево; "
            "страницы, серия и монеты сохраняются.\n"
            f"До {self.expires_at} (UTC).\n<pre>{render_tree(self.tree, self.parts)}</pre>",
            [
                [("✅ +1", "demo:1"), ("+10", "demo:10"), ("До конца", "demo:365")],
                [("Завершить просмотр", "demo:exit")],
            ],
        )


class PreviewStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else BASE_DIR / ".local" / "tree_preview.json"
        self.lock = Lock()

    def _write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def enable(self, owner_id, now):
        """Called locally by the operator; Telegram cannot enable or extend the session."""
        with self.lock:
            self._write(
                {
                    "owner_id": owner_id,
                    "expires_at": (now + timedelta(hours=1)).astimezone(UTC).isoformat(),
                    "parts": 0,
                    "tree": generate_tree(365).to_dict(),
                }
            )

    def _active(self, owner_id, now):
        if not self.path.is_file():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            expires = datetime.fromisoformat(value["expires_at"])
            if value["owner_id"] != owner_id or expires.tzinfo is None or now >= expires:
                return None
            tree = Tree.from_dict(value["tree"])
            parts = value["parts"]
            if tree.max_parts != 365 or type(parts) is not int or not 0 <= parts <= 365:
                raise ValueError("Invalid preview progress")
            return value, tree
        except (ValueError, TypeError, KeyError):
            logger.warning("Invalid local preview session; preview disabled")
            return None

    def advance(self, owner_id, now, amount=1):
        if type(amount) is not int or amount not in {0, 1, 10, 365}:
            raise ValueError("Invalid preview step")
        with self.lock:
            active = self._active(owner_id, now)
            if active is None:
                return None
            value, tree = active
            value["parts"] = min(365, value["parts"] + amount)
            self._write(value)
            return Preview(tree, value["parts"], value["expires_at"])

    def disable(self, owner_id, now):
        with self.lock:
            if self._active(owner_id, now) is None:
                return False
            self.path.unlink()
            return True
