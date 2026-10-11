"""Versioned, connected emoji bonsai; rendering only reveals an immutable prefix."""

from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
from dataclasses import dataclass, replace

ALGORITHM_VERSION = "magic-bonsai-v1"
MAX_PARTS = 600
EMPTY = "\u3000"
MAGIC = ("✨", "🌸", "🌿", "🍃", "🔮")
STYLES = ("windswept", "classic_bonsai", "rounded")
TEXT_BUDGET = 2700  # UTF-16 units, leaving room for the Telegram card's heading and fields.


class TreeGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class Part:
    order: int
    x: int
    y: int
    type: str
    emoji: str


@dataclass(frozen=True)
class Tree:
    algorithm_version: str
    seed: int | str
    max_parts: int
    width: int
    height: int
    root: tuple[int, int]
    style: str
    parts: tuple[Part, ...]

    def to_dict(self):
        return {
            "algorithm_version": self.algorithm_version,
            "seed": self.seed,
            "max_parts": self.max_parts,
            "width": self.width,
            "height": self.height,
            "root": {"x": self.root[0], "y": self.root[1]},
            "style": self.style,
            "parts": [vars(part).copy() for part in self.parts],
        }

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {
            "algorithm_version",
            "seed",
            "max_parts",
            "width",
            "height",
            "root",
            "style",
            "parts",
        }:
            raise ValueError("Неполные данные дерева.")
        if not isinstance(value["parts"], list) or len(value["parts"]) > MAX_PARTS:
            raise ValueError("Недопустимое число частей дерева.")
        if not isinstance(value["root"], dict) or set(value["root"]) != {"x", "y"}:
            raise ValueError("Недопустимое основание дерева.")
        parts = []
        for part in value["parts"]:
            if not isinstance(part, dict) or set(part) != {"order", "x", "y", "type", "emoji"}:
                raise ValueError("Недопустимая часть дерева.")
            parts.append(Part(**part))
        tree = cls(
            value["algorithm_version"],
            value["seed"],
            value["max_parts"],
            value["width"],
            value["height"],
            (value["root"]["x"], value["root"]["y"]),
            value["style"],
            tuple(parts),
        )
        validate_tree(tree)
        return tree


def neighbors(x, y):
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate_tree(tree: Tree) -> bool:
    if tree.algorithm_version != ALGORITHM_VERSION or tree.style not in STYLES:
        raise ValueError("Неизвестная версия или форма дерева.")
    if type(tree.seed) not in (int, str) or (isinstance(tree.seed, str) and len(tree.seed) > 200):
        raise ValueError("Недопустимый seed дерева.")
    if not _integer(tree.max_parts, 1, MAX_PARTS):
        raise ValueError("Недопустимое число частей дерева.")
    if not _integer(tree.width, 3, 28) or not _integer(tree.height, 3, 64):
        raise ValueError("Дерево слишком велико для текстового сообщения Telegram.")
    if len(tree.parts) != tree.max_parts or len(tree.root) != 2:
        raise ValueError("Число частей не соответствует дереву.")
    if not all(
        _integer(v, 0, n - 1) for v, n in zip(tree.root, (tree.width, tree.height), strict=True)
    ):
        raise ValueError("Основание вне сетки.")
    occupied, magic = set(), []
    for order, part in enumerate(tree.parts, 1):
        if type(part.type) is not str or type(part.emoji) is not str:
            raise ValueError("Недопустимый тип или символ части.")
        if type(part.order) is not int or part.order != order:
            raise ValueError("Нарушен порядок роста.")
        if not _integer(part.x, 0, tree.width - 1) or not _integer(part.y, 0, tree.height - 1):
            raise ValueError("Часть дерева вне сетки.")
        pos = (part.x, part.y)
        if pos in occupied:
            raise ValueError("Повторная клетка дерева.")
        if order == 1:
            if pos != tree.root or part.type != "trunk":
                raise ValueError("Первая часть должна быть основанием.")
        elif not occupied.intersection(neighbors(*pos)):
            raise ValueError("Часть не соединена с выросшим деревом.")
        if part.type in {"trunk", "branch"}:
            valid = part.emoji == "🟫"
        elif part.type == "leaf":
            valid = part.emoji == "🟩"
        elif part.type == "magic":
            valid = part.emoji in MAGIC and order > math.floor(tree.max_parts * 0.6)
            if any(max(abs(part.x - x), abs(part.y - y)) <= 2 for x, y in magic):
                raise ValueError("Магические акценты слишком близко.")
            magic.append(pos)
        else:
            valid = False
        if not valid:
            raise ValueError("Недопустимый тип или символ части.")
        occupied.add(pos)
    if len(magic) > math.floor(tree.max_parts * 0.06) or (tree.max_parts < 30 and magic):
        raise ValueError("Слишком много магии.")
    if len(render_tree(tree, tree.max_parts).encode("utf-16-le")) // 2 > TEXT_BUDGET:
        raise ValueError("Дерево не помещается в текстовое сообщение Telegram.")
    return True


def render_tree(tree: Tree, current_parts: int) -> str:
    if not _integer(current_parts, 0, tree.max_parts):
        raise ValueError("current_parts вне диапазона дерева.")
    grid = [[EMPTY] * tree.width for _ in range(tree.height)]
    for part in tree.parts[:current_parts]:
        grid[part.y][part.x] = part.emoji
    return "\n".join("".join(row) for row in grid)


def _rng(seed, attempt):
    raw = json.dumps([ALGORITHM_VERSION, seed, attempt], ensure_ascii=False).encode()
    return random.Random(int.from_bytes(hashlib.sha256(raw).digest(), "big"))


def _small_tree(n, seed, rng):
    width, height = max(5, math.ceil(1.6 * math.sqrt(n))), max(5, math.ceil(1.4 * math.sqrt(n)))
    root = (width // 2, height - 2)
    coords, used = [], set()
    trunk_height = min(n, max(1, height // 3))
    for step in range(trunk_height):
        pos = (root[0], root[1] - step)
        coords.append(Part(len(coords) + 1, *pos, "trunk", "🟫"))
        used.add(pos)
    center = (root[0] + rng.choice((-0.5, 0.5)), root[1] - trunk_height)
    while len(coords) < n:
        frontier = sorted({pos for cell in used for pos in neighbors(*cell)} - used)
        frontier = [(x, y) for x, y in frontier if 1 <= x < width - 1 and 1 <= y <= root[1] - 1]
        if not frontier:
            return None
        scores = [math.exp(-((x - center[0]) ** 2 + (y - center[1]) ** 2) / 4) for x, y in frontier]
        pos = rng.choices(frontier, weights=scores)[0]
        used.add(pos)
        coords.append(Part(len(coords) + 1, *pos, "leaf", "🟩"))
    return Tree(ALGORITHM_VERSION, seed, n, width, height, root, "rounded", tuple(coords))


def _build(n, seed, rng):
    width = min(28, max(10, math.ceil(1.8 * math.sqrt(n))))
    height = max(9, math.ceil(1.8 * math.sqrt(n)), math.ceil(n / ((width - 2) * 0.58)) + 2)
    root = (width // 2 + rng.choice((-1, 0, 1)), height - 2)
    style, direction = rng.choice(STYLES), rng.choice((-1, 1))
    top = max(3, round(height * rng.uniform(0.36, 0.44)))
    bend = rng.randint(1, max(2, width // 6))
    parts, occupied, trunk = [], set(), {}

    def add(x, y, kind):
        if not (1 <= x < width - 1 and 1 <= y < height - 1):
            return False
        if (x, y) not in occupied:
            occupied.add((x, y))
            parts.append(Part(len(parts) + 1, x, y, kind, "🟫"))
        return True

    x = root[0]
    for y in range(root[1], top - 1, -1):
        add(x, y, "trunk")
        fraction = (root[1] - y) / max(1, root[1] - top)
        target = root[0] + direction * round(bend * (fraction**1.5))
        while x != target:
            x += 1 if target > x else -1
            add(x, y, "trunk")
        trunk[y] = x
    # A little thickness at the base; keep all growth orthogonally attached.
    if n >= 70:
        for y in range(root[1], max(top + 1, root[1] - height // 3), -1):
            add(trunk[y] - direction, y, "trunk")
    count = 2 if n < 70 else rng.choice((3, 4))
    levels = [top + round(i * (root[1] - top - 3) / max(1, count - 1)) for i in range(count)]
    tips = [(x, top)]
    for i, level in enumerate(levels):
        side = direction if i % 2 == 0 else -direction
        length = rng.randint(max(2, width // 6), max(3, width // 3))
        if style == "windswept" and side == direction:
            length += 1
        bx, by = trunk[level], level
        for step in range(length):
            nx = bx + side
            if not add(nx, by, "branch"):
                break
            bx = nx
            if step > 0 and step % 3 == 0 and by > 2:
                by -= 1
                add(bx, by, "branch")
        tips.append((bx, by))
    if len(parts) >= n:
        return None
    leaf_count = n - len(parts)
    clouds = []
    leaf_floor = root[1] - max(2, height // 5)
    radius = math.sqrt(leaf_count / (len(tips) * math.pi))
    for tx, ty in tips:
        rx = radius * rng.uniform(1.6, 1.95)
        ry = radius * rng.uniform(0.8, 1.05)
        if style == "rounded":
            ry *= 1.12
        mx = min(width - 2 - rx, max(1 + rx, tx + rng.uniform(-0.5, 0.5)))
        my = min(leaf_floor - ry, max(1 + ry, ty - ry * 0.45))
        clouds.append((mx, my, rx, ry))
    # Leave small windows by branch junctions, instead of filling a solid green block.
    windows = set()
    for i in range(len(levels) - 1):
        wy = (levels[i] + levels[i + 1]) // 2
        wx = trunk[wy] + (direction if i % 2 == 0 else -direction)
        windows.update((wx + dx, wy + dy) for dx in (0, 1) for dy in (0, 1))
    preferences = {}
    for cy in range(1, leaf_floor + 1):
        for cx in range(1, width - 1):
            if (cx, cy) in windows:
                continue
            values = [
                1 - ((cx - mx) / rx) ** 2 - ((cy - my) / ry) ** 2 for mx, my, rx, ry in clouds
            ]
            index = max(range(len(values)), key=values.__getitem__)
            preferences[cx, cy] = (values[index] + rng.uniform(-0.06, 0.06), index)
    filled = [0] * len(clouds)
    while len(parts) < n:
        frontier = sorted({pos for cell in occupied for pos in neighbors(*cell)} - occupied)
        candidates, weights = [], []
        for pos in frontier:
            if pos not in preferences:
                continue
            affinity, index = preferences[pos]
            adjacent = len(occupied.intersection(neighbors(*pos)))
            compact = 1 + 0.4 * (adjacent - 1)
            balance = 1 / (1 + filled[index] / max(1, leaf_count / len(clouds)))
            candidates.append(pos)
            weights.append(math.exp(max(-20, min(12, affinity * 8))) * compact * balance)
        if not candidates:
            return None
        pos = rng.choices(candidates, weights=weights)[0]
        occupied.add(pos)
        filled[preferences[pos][1]] += 1
        parts.append(Part(len(parts) + 1, *pos, "leaf", "🟩"))
    # Reject a saturated rectangular crown or a form that leaves only one useful cloud.
    leaves = [part for part in parts if part.type == "leaf"]
    area = (max(p.x for p in leaves) - min(p.x for p in leaves) + 1) * (
        max(p.y for p in leaves) - min(p.y for p in leaves) + 1
    )
    spurs = sum(len(occupied.intersection(neighbors(p.x, p.y))) == 1 for p in leaves)
    if len(leaves) / area > 0.88 or sum(f >= 3 for f in filled) < 2 or spurs > len(leaves) * 0.15:
        return None
    rng.shuffle(leaves)
    accents = []
    target = min(math.floor(n * 0.06), round(n * rng.uniform(0.02, 0.04)))
    for part in leaves:
        if (
            part.order <= math.floor(n * 0.6)
            or len(occupied.intersection(neighbors(part.x, part.y))) < 2
        ):
            continue
        if any(max(abs(part.x - p.x), abs(part.y - p.y)) <= 2 for p in accents):
            continue
        accents.append(part)
        # Rare purple magic; the common palette consists of four simple glyphs.
        emoji = rng.choice(MAGIC if rng.random() < 0.08 else MAGIC[:-1])
        parts[part.order - 1] = replace(part, type="magic", emoji=emoji)
        if len(accents) >= target:
            break
    return Tree(ALGORITHM_VERSION, seed, n, width, height, root, style, tuple(parts))


def generate_tree(max_parts: int, seed: int | str | None = None) -> Tree:
    if type(max_parts) is not int or max_parts <= 0:
        raise ValueError("max_parts должен быть положительным целым числом.")
    if max_parts > MAX_PARTS:
        raise TreeGenerationError(f"Текстовое дерево поддерживает не более {MAX_PARTS} частей.")
    if seed is None:
        seed = secrets.token_hex(16)
    if type(seed) not in (int, str) or (isinstance(seed, str) and len(seed) > 200):
        raise ValueError("seed должен быть целым числом или строкой до 200 символов.")
    for attempt in range(16):
        rng = _rng(seed, attempt)
        tree = _small_tree(max_parts, seed, rng) if max_parts < 30 else _build(max_parts, seed, rng)
        if tree is not None:
            validate_tree(tree)
            return tree
    raise TreeGenerationError("Не удалось создать связный бонсай заданного размера.")
