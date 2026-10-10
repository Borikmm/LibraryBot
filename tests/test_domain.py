import copy
from datetime import UTC, datetime, timedelta

import pytest

from bot import domain as d
from bot.backup import validate_backup

START = datetime(2026, 1, 29, 12, tzinfo=UTC)


def profile(total=100, norm=25):
    p = d.new_profile(1, "Читатель", "UTC", START)
    d.add_book(p, "Колобок", "Народ", total, norm, START)
    return p


def test_four_marks_and_duplicate_after_completion():
    p = profile()
    for i in range(4):
        result = d.mark_reading(p, START + timedelta(days=i))
        assert result["book"]["page"] == 25 * (i + 1)
    before = copy.deepcopy(p)
    with pytest.raises(d.RuleError, match="уже зачтена"):
        d.mark_reading(p, START + timedelta(days=3, hours=1))
    assert p == before
    assert d.stage(p["books"][0]) == ("🌲", "Завершённое дерево")
    assert p["free_day"] == "2026-02-02"


def test_remainder_and_switch_preserve_general_streak():
    p = profile(60, 25)
    first = p["books"][0]
    d.mark_reading(p, START)
    second = d.add_book(p, "Новая", "Автор", 100, 20, START)
    assert first["status"] == "paused" and first["page"] == 25
    d.resume_book(p, first["id"])
    assert second["status"] == "paused" and first["streak"] == 0 and p["streak"] == 1
    d.mark_reading(p, START + timedelta(days=1))
    result = d.mark_reading(p, START + timedelta(days=2))
    assert result["pages"] == 10 and first["page"] == 60
    assert p["streak"] == 3 and first["streak"] == 2


def test_free_day_then_loss_no_book():
    p = profile(25, 25)
    d.mark_reading(p, START)
    events = d.settle_days(p, START + timedelta(days=2))
    assert [e["kind"] for e in events] == ["free"]
    assert p["streak"] == 1 and len(p["tree"]) == 1
    events = d.settle_days(p, START + timedelta(days=3))
    assert events[0]["kind"] == "lost"
    assert p["streak"] == 0 and not p["tree"] and p["best"] == 1
    assert p["books"][0]["status"] == "completed"
    assert not d.settle_days(p, START + timedelta(days=3))


def test_coin_protection_keeps_19_then_reward_at_20():
    p = profile(10000, 1)
    for i in range(19):
        d.mark_reading(p, START + timedelta(days=i))
    assert p["coins"] == 1
    d.settle_days(p, START + timedelta(days=20))
    assert p["streak"] == 19 and p["coins"] == 0 and len(p["tree"]) == 19
    d.mark_reading(p, START + timedelta(days=20))
    assert p["streak"] == 20 and p["coins"] == 1 and len(p["tree"]) == 20


def test_new_series_earns_again_and_tree_restarts():
    p = profile(10000, 1)
    for i in range(10):
        d.mark_reading(p, START + timedelta(days=i))
    d.settle_days(p, START + timedelta(days=13))
    assert p["streak"] == 0 and p["best"] == 10 and len(p["tree"]) == 0
    for i in range(13, 23):
        d.mark_reading(p, START + timedelta(days=i))
    assert p["streak"] == 10 and p["coins"] == 1
    assert len([e for e in p["coin_events"] if e["kind"] == "reward"]) == 2


def test_golden_permanent_exactly_365_visible_symbols():
    p = profile(10000, 1)
    assert len(d.TREE_CELLS) == 365
    for _ in range(365):
        before = copy.deepcopy(p["tree"])
        assert d.grow(p)
        assert p["tree"][:-1] == before
    drawing = d.render_tree(p)
    assert sum(not c.isspace() for c in drawing) == 365
    assert len(drawing.splitlines()) >= 15
    assert all(len(line) <= 31 for line in drawing.splitlines())
    assert p["golden"] and not d.grow(p)
    d.mark_reading(p, START)
    d.settle_days(p, START + timedelta(days=2))
    assert p["streak"] == 0 and p["golden"] and len(p["tree"]) == 365


def test_delete_removes_totals_keeps_daily_tombstone():
    p = profile()
    d.mark_reading(p, START)
    d.delete_book(p, p["books"][0]["id"])
    assert d.statistics(p, START)["pages"] == 0
    assert p["marks"][0]["book_id"] is None and len(p["tree"]) == 1
    d.add_book(p, "Новая", "Автор", 100, 10, START)
    with pytest.raises(d.RuleError):
        d.mark_reading(p, START)


def test_timezone_cannot_shorten_existing_day_or_replay_midnight():
    p = profile()
    d.mark_reading(p, START)
    d.change_timezone(p, "Pacific/Kiritimati", START + timedelta(hours=1))
    with pytest.raises(d.RuleError):
        d.mark_reading(p, START + timedelta(hours=1))
    d.change_timezone(p, "America/Los_Angeles", START + timedelta(hours=2))
    with pytest.raises(d.RuleError):
        d.mark_reading(p, START + timedelta(hours=2))
    assert len(p["tree"]) == 1


def test_year_boundary_and_restart_catchup():
    now = datetime(2026, 12, 31, 12, tzinfo=UTC)
    p = d.new_profile(1, "User", "UTC", now)
    d.add_book(p, "Книга", "Автор", 1000, 1, now)
    d.mark_reading(p, now)
    assert d.settle_days(p, now + timedelta(days=3))[0]["day"] == "2027-01-01"
    assert p["closed_through"] == "2027-01-02"
    assert not d.settle_days(p, now + timedelta(days=3))


def test_manual_correction_no_rewards_or_free_day():
    p = profile()
    d.edit_book(p, p["books"][0]["id"], "page", "100", START)
    assert not p["marks"] and not p["tree"] and p["free_day"] is None
    assert d.active_book(p) is None


@pytest.mark.parametrize(
    "field,value",
    [("total", "0"), ("norm", "-1"), ("page", "101"), ("start", "2099-01-01"), ("title", "")],
)
def test_invalid_book_edit(field, value):
    p = profile()
    with pytest.raises(d.RuleError):
        d.edit_book(p, p["books"][0]["id"], field, value, START)


def test_backup_roundtrip_and_corruption():
    p = profile()
    d.mark_reading(p, START)
    payload = {
        "format": "LibraryBot",
        "version": 1,
        "owner_id": 1,
        "exported_at": d.iso(START),
        "profile": p,
    }
    assert validate_backup(payload, 1, START) == p
    with pytest.raises(d.RuleError, match="другому"):
        validate_backup(payload, 2, START)
    broken = copy.deepcopy(payload)
    broken["profile"]["coins"] = 99
    with pytest.raises(d.RuleError):
        validate_backup(broken, 1, START)
    broken = copy.deepcopy(payload)
    broken["profile"]["marks"].append(broken["profile"]["marks"][0])
    with pytest.raises(d.RuleError):
        validate_backup(broken, 1, START)
