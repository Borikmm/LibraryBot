"""Reproducible visual QA gallery; contains generated examples, never user profiles."""

import argparse
import html
import json
from pathlib import Path

from bot.bonsai import generate_tree, render_tree


def write_gallery(directory):
    directory.mkdir(parents=True, exist_ok=True)
    samples = [(f"Seed {seed} · 100/100", generate_tree(100, seed), 100) for seed in range(20)]
    growth = generate_tree(100, "growth-example")
    stages = [(f"Один бонсай · {k}/100", growth, k) for k in (1, 10, 25, 50, 75, 100)]
    main = generate_tree(365, "main-example")
    stages += [(f"Главное дерево · {k}/365", main, k) for k in (10, 20, 50, 100, 200, 364)]
    cards = []
    for title, tree, k in samples + stages:
        cards.append(
            f"<article><h2>{title}</h2><small>{tree.style}</small>"
            f"<pre>{html.escape(render_tree(tree, k))}</pre></article>"
        )
    document = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LibraryBot — бонсаи</title><style>
body{background:#0b1717;color:#edf4eb;font:16px system-ui;margin:24px}
main{display:flex;gap:16px;flex-wrap:wrap}article{background:#18302b;padding:16px;border-radius:12px}
h1{font-size:24px}h2{font-size:16px;margin:0 0 8px}small{color:#b4cfbf}
pre{font:14px/1.12 'Segoe UI Emoji',monospace;white-space:pre;margin:16px 0 0}
</style><h1>Бонсаи: 20 силуэтов и последовательный рост</h1>
<p>Текстовая сетка для проверки в браузере. Вид эмодзи в Telegram зависит от клиента.</p><main>"""
    (directory / "gallery.html").write_text(
        document + "".join(cards) + "</main></html>", encoding="utf-8"
    )
    (directory / "samples.json").write_text(
        json.dumps([t.to_dict() for _, t, _ in samples], ensure_ascii=False), encoding="utf-8"
    )
    # Vector contact sheets show exact occupied coordinates with colored cells.
    for name, entries, columns, card_w, card_h, pixel in (
        ("silhouettes", samples, 4, 260, 284, 12),
        ("growth", stages, 3, 340, 430, 10),
    ):
        height = ((len(entries) + columns - 1) // columns) * card_h
        shapes = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{columns * card_w}" height="{height}"><rect width="100%" height="100%" fill="#0b1717"/>'
        ]
        for index, (title, tree, k) in enumerate(entries):
            ox, oy = (index % columns) * card_w, (index // columns) * card_h
            shapes.append(
                f'<text x="{ox + 16}" y="{oy + 25}" fill="#edf4eb" font-size="14" font-family="sans-serif">{html.escape(title)}</text>'
            )
            shapes.append(
                f'<text x="{ox + 16}" y="{oy + 44}" fill="#a4c4b5" font-size="12" font-family="sans-serif">{tree.style}</text>'
            )
            for part in tree.parts[:k]:
                color = "#48a54e" if part.type == "leaf" else "#946334"
                if part.type == "magic":
                    color = {
                        "✨": "#ffd85c",
                        "🌸": "#ff9cc5",
                        "🌿": "#95d782",
                        "🍃": "#bcf295",
                        "🔮": "#b38dec",
                    }[part.emoji]
                x, y = ox + 16 + part.x * pixel, oy + 56 + part.y * pixel
                shapes.append(
                    f'<rect x="{x}" y="{y}" width="{pixel - 1}" height="{pixel - 1}" rx="1" fill="{color}"/>'
                )
                if part.type == "magic":
                    shapes.append(
                        f'<circle cx="{x + pixel / 2 - 0.5}" cy="{y + pixel / 2 - 0.5}" r="2" fill="#ffffff"/>'
                    )
        (directory / f"{name}.svg").write_text("".join(shapes) + "</svg>", encoding="utf-8")
    print(f"Generated QA gallery: {directory.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".local/bonsai-preview"))
    write_gallery(parser.parse_args().output)
