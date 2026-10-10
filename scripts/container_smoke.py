"""Run inside the built image against a disposable PostgreSQL database."""

import os
import sys
from datetime import UTC, datetime, timedelta

from bot import domain as d
from bot.bot import LibraryBot
from bot.config import Settings

now = datetime(2026, 1, 29, 12, tzinfo=UTC)
bot = LibraryBot(Settings("123456:fake-token", os.environ["TEST_DATABASE_URL"], "UTC", port=10010))
try:
    if len(sys.argv) > 1:
        if sys.argv[1] == "mutate":
            p = bot.store.get(1)
            bot.store.mutate(
                1,
                lambda p: d.edit_book(
                    p, p["books"][0]["id"], "norm", "99", now + timedelta(days=3)
                ),
            )
            assert bot.store.get(1)["books"][0]["norm"] == 99
            print("Disposable database changed before restore")
        elif sys.argv[1] == "verify":
            p = bot.store.get(1)
            assert p["books"][0]["page"] == 100 and p["books"][0]["norm"] == 25
            assert len(p["marks"]) == 4 and len(p["tree"]) == 4
            print("Backup restore verified: 100 pages, norm 25, four marks and four symbols")
        else:
            raise ValueError("Unknown smoke mode")
        sys.exit(0)
    bot.store.ensure(1, "Smoke reader", "UTC", now)
    bot.store.mutate(1, lambda p: d.add_book(p, "Kolobok", "Author", 100, 25, now))
    for i in range(4):
        result = bot.service.mark(1, now + timedelta(days=i))
        assert result["book"]["page"] == (i + 1) * 25
    try:
        bot.service.mark(1, now + timedelta(days=3))
    except d.RuleError:
        pass
    else:
        raise AssertionError("Duplicate mark accepted")
    p = bot.store.get(1)
    assert p["books"][0]["status"] == "completed" and len(p["tree"]) == 4
    print("Container startup, migrations and 25/50/75/100 reading smoke test passed")
finally:
    bot.health.server.server_close()
    bot.leader.close()
    bot.store.close()
