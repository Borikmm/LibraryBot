from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from bot import domain as d
from bot.service import Service
from test_domain import START


def setup(store, uid=1):
    store.ensure(uid, "Reader", "UTC", START)
    store.mutate(uid, lambda p: d.add_book(p, "Колобок", "Автор", 10000, 25, START))
    return Service(store)


def test_concurrent_marks_atomic(store):
    svc = setup(store)

    def attempt(_):
        try:
            svc.mark(1, START)
            return True
        except d.RuleError:
            return False

    with ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(attempt, range(10))) == 1
    p = store.get(1)
    assert p["books"][0]["page"] == 25 and p["streak"] == 1 and len(p["tree"]) == 1


def test_profiles_isolated_and_restart(store):
    svc = setup(store)
    setup(store, 2)
    svc.mark(1, START)
    assert store.get(2)["streak"] == 0
    fresh = Service(store)
    store.settle(1, START + timedelta(days=3))
    fresh.mark(1, START + timedelta(days=3))
    assert store.get(1)["best"] == 1 and store.get(1)["streak"] == 1
    with store.pool.connection() as conn:
        assert conn.execute("SELECT count(*) n FROM deliveries").fetchone()["n"] == 1


def test_fertilizer_transaction_repeat_cancel_full_tree(store):
    svc = setup(store)
    setup(store, 2)
    for i in range(10):
        svc.mark(1, START + timedelta(days=i))
    now = START + timedelta(days=9)
    store.group(-100, "Group")
    for uid in (1, 2):
        store.mutate(uid, lambda p: p.update(group_id=-100, show_forest=True))
    token = store.action(1, "fertilize", {"target": 2}, now)
    svc.fertilize(1, token, now)
    assert store.get(1)["coins"] == 0 and len(store.get(2)["tree"]) == 1
    with pytest.raises(d.RuleError):
        svc.fertilize(1, token, now)
    token = store.action(1, "fertilize", {"target": 2}, now)
    store.cancel_action(token, 1)
    with pytest.raises(d.RuleError):
        svc.fertilize(1, token, now)
    store.mutate(2, lambda p: p.update(tree=[list(c) for c in d.TREE_CELLS], golden=True))
    token = store.action(1, "fertilize", {"target": 2}, now)
    with pytest.raises(d.RuleError, match="золотое"):
        svc.fertilize(1, token, now)
    assert store.get(1)["coins"] == 0


def test_privacy_rechecked_and_single_group(store):
    svc = setup(store)
    setup(store, 2)
    store.group(-100, "One")
    store.group(-200, "Two")
    for uid in (1, 2):
        token = store.action(uid, "connect", {"group_id": -100}, START)
        svc.connect(uid, token, START)
    assert not svc.can_view(1, 2, "forest", -100)
    store.mutate(2, lambda p: p.update(show_forest=True))
    assert svc.can_view(1, 2, "forest", -100)
    token = store.action(2, "connect", {"group_id": -200}, START)
    with pytest.raises(d.RuleError):
        svc.connect(2, token, START)
    store.mutate(2, lambda p: p.update(group_id=None))
    assert not svc.can_view(1, 2, "forest", -100)


def test_import_atomic_and_stale_coins_rejected(store):
    svc = setup(store)
    for i in range(10):
        svc.mark(1, START + timedelta(days=i))
    now = START + timedelta(days=9)
    backup = svc.export(1, now)
    token = store.action(1, "import", backup, now)
    svc.import_profile(1, token, now)
    assert store.get(1)["coins"] == 1
    with pytest.raises(d.RuleError):
        svc.mark(1, now)
    token = store.action(1, "fertilize", {"target": 1}, now)
    svc.fertilize(1, token, now)
    token = store.action(1, "import", backup, now)
    before = store.get(1)
    with pytest.raises(d.RuleError, match="старее"):
        svc.import_profile(1, token, now)
    assert store.get(1) == before


def test_menu_owner_bound_to_message(store):
    setup(store)
    token = store.create_menu(1, -100)
    store.bind_menu(token, 10)
    assert store.menu(token, 1, -100, 10)
    with pytest.raises(d.RuleError):
        store.menu(token, 2, -100, 10)
