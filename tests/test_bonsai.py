import copy
import json
import random
from datetime import timedelta

import pytest

from bot import bonsai, domain as d, views
from bot.backup import validate_backup
from bot.service import Service
from test_domain import START, profile


@pytest.mark.parametrize("size", [1, 5, 20, 30, 50, 100, 200, 365, 600])
@pytest.mark.parametrize("seed", [0, "librarybot", "0"])
def test_every_growth_step_is_one_connected_fixed_cell(size, seed):
    tree = bonsai.generate_tree(size, seed)
    assert bonsai.validate_tree(tree)
    assert len(tree.parts) == len({(part.x, part.y) for part in tree.parts}) == size
    assert tree == bonsai.generate_tree(size, seed)
    assert tree == bonsai.Tree.from_dict(json.loads(json.dumps(tree.to_dict())))
    previous = bonsai.render_tree(tree, 0)
    assert set(previous) <= {bonsai.EMPTY, "\n"}
    glyphs = {"🟩", "🟫", *bonsai.MAGIC}
    for count in range(1, size + 1):
        current = bonsai.render_tree(tree, count)
        rows = current.splitlines()
        assert len(rows) == tree.height and all(len(row) == tree.width for row in rows)
        assert sum(c in glyphs for c in current) == count
        changed = [(a, b) for a, b in zip(previous, current, strict=True) if a != b]
        assert len(changed) == 1 and changed[0][0] == bonsai.EMPTY
        assert current == bonsai.render_tree(tree, count)
        previous = current
    assert len(previous.encode("utf-16-le")) // 2 <= bonsai.TEXT_BUDGET


def test_twenty_seeds_have_different_geometry_and_sparse_late_magic():
    outlines = set()
    for seed in range(20):
        tree = bonsai.generate_tree(100, seed)
        outlines.add(tuple((p.x, p.y, p.type in {"trunk", "branch"}) for p in tree.parts))
        magic = [p for p in tree.parts if p.type == "magic"]
        assert 2 <= len(magic) <= 6
        assert all(p.order > 60 for p in magic)
        assert all(0 < p.x < tree.width - 1 and 0 < p.y < tree.height - 1 for p in tree.parts)
    assert len(outlines) == 20


@pytest.mark.parametrize("size", [0, -1, True, 1.5, "100", 601])
def test_invalid_sizes_are_explicit_errors(size):
    with pytest.raises(ValueError):
        bonsai.generate_tree(size)


def test_render_and_seed_do_not_use_global_random():
    state = random.getstate()
    tree = bonsai.generate_tree(100, "fixed")
    bonsai.render_tree(tree, 50)
    assert state == random.getstate()
    assert bonsai.generate_tree(100).seed != bonsai.generate_tree(100).seed
    for count in (-1, 101, True, 1.5):
        with pytest.raises(ValueError):
            bonsai.render_tree(tree, count)


@pytest.mark.parametrize(
    "corruption", ["duplicate", "disconnected", "order", "emoji", "version", "string"]
)
def test_tree_json_validation_rejects_corruption(corruption):
    raw = bonsai.generate_tree(100, 1).to_dict()
    if corruption == "duplicate":
        raw["parts"][1].update(x=raw["parts"][0]["x"], y=raw["parts"][0]["y"])
    elif corruption == "disconnected":
        raw["parts"][1].update(x=0, y=0)
    elif corruption == "order":
        raw["parts"][1]["order"] = 99
    elif corruption == "emoji":
        raw["parts"][1]["emoji"] = "🌸🌸"
    elif corruption == "version":
        raw["algorithm_version"] = "unknown"
    else:
        raw["parts"][1]["x"] = "1"
    with pytest.raises(ValueError):
        bonsai.Tree.from_dict(raw)


def test_main_growth_and_book_render_never_regenerate(monkeypatch):
    p = profile()
    saved = copy.deepcopy(p["tree_plan"])
    book = p["books"][0]

    def forbidden(*args, **kwargs):
        raise AssertionError("A saved tree must not be generated again")

    monkeypatch.setattr(bonsai, "generate_tree", forbidden)
    for step in range(10):
        before = copy.deepcopy(p["tree"])
        d.grow(p)
        assert p["tree"][:-1] == before
        assert p["tree_plan"] == saved
        d.render_tree(p)
        book["page"] = step * 10
        views.compact_tree(book)
    assert book["tree_plan"]["max_parts"] == 100


def test_loss_creates_new_plan_but_books_and_golden_plan_survive():
    p = profile(10000, 1)
    main, book = copy.deepcopy(p["tree_plan"]), copy.deepcopy(p["books"][0]["tree_plan"])
    d.mark_reading(p, START)
    d.settle_days(p, START + timedelta(days=2))
    assert not p["tree"] and p["tree_plan"] != main
    assert p["books"][0]["tree_plan"] == book
    for _ in range(365):
        d.grow(p)
    golden = copy.deepcopy(p["tree_plan"])
    d.mark_reading(p, START + timedelta(days=2))
    d.settle_days(p, START + timedelta(days=4))
    assert p["golden"] and p["tree_plan"] == golden


def test_persisted_plan_survives_restart_export_and_import(store):
    store.ensure(1, "Reader", "UTC", START)
    store.mutate(1, lambda p: d.add_book(p, "Book", "Author", 100, 25, START))
    svc = Service(store)
    svc.mark(1, START)
    before = store.get(1)
    backup = Service(store).export(1, START)
    assert backup["version"] == 2
    action = store.action(1, "import", json.loads(json.dumps(backup)), START)
    Service(store).import_profile(1, action, START)
    after = store.get(1)
    for field in ("tree_plan", "tree", "books"):
        assert after[field] == before[field]
    assert d.render_tree(after) == d.render_tree(before)
    corrupted = copy.deepcopy(backup)
    corrupted["profile"]["tree"][0][2] = "🌸"
    with pytest.raises(d.RuleError):
        validate_backup(corrupted, 1, START)


def test_version_one_backup_and_database_upgrade_preserve_ascii(store):
    p = profile()
    d.mark_reading(p, START)
    p.pop("tree_plan")
    p["tree"] = [list(d.TREE_CELLS[0])]
    for book in p["books"]:
        book.pop("tree_plan")
    backup = {
        "format": "LibraryBot",
        "version": 1,
        "owner_id": 1,
        "exported_at": d.iso(START),
        "profile": p,
    }
    restored = validate_backup(backup, 1, START)
    assert restored["tree_plan"] is None and restored["books"][0]["tree_plan"] is None
    store.ensure(1, "Reader", "UTC", START)
    from psycopg.types.json import Jsonb

    with store.pool.connection() as conn:
        conn.execute("UPDATE profiles SET data=%s WHERE user_id=1", (Jsonb(p),))
    store.migrate()
    upgraded = store.get(1)
    assert upgraded["tree"] == p["tree"]
    assert upgraded["tree_plan"] is None
    assert views.compact_tree(upgraded["books"][0]) == views.compact_tree(p["books"][0])
    store.migrate()
    assert store.get(1) == upgraded
    d.grow(upgraded)
    assert upgraded["tree"][0] == p["tree"][0] and upgraded["tree_plan"] is None
