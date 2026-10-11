"""Russian Telegram screens. User strings are always HTML escaped."""

from dataclasses import dataclass, field
from html import escape

from . import bonsai, domain as d

e = escape
QUOTE = "Книги — это семена, брошенные в землю человеческого разума; они прорастают и приносят плоды в виде новых идей и поступков"
GROUP_INTRO = (
    "В этой группе мы становимся лучше с каждым днем при помощи книг, а также выращиваем "
    "при этом свой собственный лес знаний, в центре которого неизбежно растет огромное "
    "дерево счастья! Просто попробуй, закрепись, начни взращивать, и вот увидишь, вся твоя "
    "жизнь кардинально изменится в лучшую сторону! И не забывай, твоя судьба в твоих руках "
    "также, как и жизнь твоего дерева!"
)
RULES = [
    "<b>Чтение и личный лес</b>\n\nКаждая книга — своё дерево. Отправляй ✅ в ЛС один раз за местный день. "
    "Книга получает дневную норму страниц, но не больше остатка. Главное дерево получает ровно один "
    "символ. Повторная галочка ничего не добавляет. Отметки за прошлые дни недоступны.\n\n"
    "Книгу можно отложить и продолжить. Её страницы и дерево сохраняются; при продолжении серия "
    "книги начинается с нуля. Смена книги сама по себе не прерывает общую серию.",
    "<b>Серии, монеты и защита</b>\n\nЗа каждые 10 дней общей серии — одна монета. "
    "После завершения книги защищён только следующий календарный день. Затем каждый пропуск "
    "автоматически расходует одну монету. Защита сохраняет серию, но не увеличивает её и дерево.\n\n"
    "Если защиты нет, текущая серия обнуляется и обычное главное дерево погибает. Книги, их деревья "
    "и рекорд сохраняются. Следующая отметка создаёт первый символ новой формы.",
    "<b>Золотая цель и друзья</b>\n\nНа 365 символах главное дерево становится золотым изображением "
    "навсегда. Серия продолжает приносить монеты. Одну монету можно потратить на один символ своего "
    "дерева или открытого дерева участника своей группы. Полное дерево монету не расходует.\n\n"
    "Лес и статистика изначально закрыты. Подключение к группе требует согласия и не открывает "
    "данные. Часовой пояс определяет сутки и расписания; его изменение не повторяет награды.",
]
ONBOARDING = [
    "<b>Добро пожаловать в LibraryBot 🌱</b>\n\nУ тебя будет собственный лес: каждое дерево — книга, "
    "которую ты читаешь или уже прочитал. Читай и каждый день отправляй мне ✅. "
    "Дерево книги растёт по страницам, а главное дерево — на один символ за день чтения.",
    "<b>Монеты и защита</b>\n\nЗа каждые 10 дней серии ты получаешь монету удачи. Она может "
    "добавить символ дереву или автоматически защитить один пропуск. После завершения книги "
    "бесплатно защищён только следующий день. Без защиты обычное главное дерево и текущая серия "
    "начнутся заново. Деревья книг и рекорды сохранятся.",
    "<b>Твоя цель — 365 символов</b>\n\nНа вершине этой цели тебя ждёт постоянная золотая награда. "
    "Можно читать наедине с ботом, а позже подключить группу друзей. "
    "Лес и статистика будут видны только с твоего разрешения.",
]


@dataclass
class View:
    text: str
    rows: list = field(default_factory=list)
    photo: str | None = None
    route: str | None = None


def back(action="home"):
    return [("← Назад", action)]


def home(p, now):
    b = d.active_book(p)
    text = f"<i>«{QUOTE}»</i>\n\n"
    if b:
        emoji, stage = d.stage(b)
        pc = d.percentage(b)
        from .scheduler import marked_today

        marked = marked_today(p, now)
        text += (
            f"<b>Сейчас ты читаешь:</b> {e(b['title'])} — {e(b['author'])}\n"
            f"Твоё дерево: {emoji} {stage}\nРост дерева: {pc:.0f}%\n"
            f"Количество жизни в дереве: {b['streak']} дней\n"
            f"Сколько страниц в книге: {b['total']}\n"
            f"Сколько ты уже прочитал: {b['page']} страниц — {pc:.0f}%\n"
            f"Сколько ты читаешь в день: {b['norm']} страниц\n"
            f"Статус прочтения на сегодня: {'✅' if marked else '❌'}\n"
        )
    else:
        text += "<b>Сейчас ты не читаешь.</b>\nВыбери следующую книгу в настройках.\n"
    text += f"Твой рекорд общего беспрерывного чтения: {p['best']} дней\n\nОтметка чтения: отправь ✅ в ЛС."
    tree_action = f"book:{p['owner_id']}:{b['id']}" if b else f"tree:{p['owner_id']}"
    return View(
        text,
        [
            [("Настройки", "settings"), ("Посмотреть на дерево", tree_action)],
            [("Мотивация", "motivation")],
        ],
    )


def settings(p, group_title=None):
    def flags(value):
        return "включены" if value else "выключены"

    text = (
        f"<b>Настройки</b>\nЧасовой пояс: {e(p['timezone'])}\n"
        f"Напоминания: {flags(p['reminders'])}\n"
        f"Лес: {'открыт' if p['show_forest'] else 'скрыт'}\n"
        f"Статистика: {'открыта' if p['show_stats'] else 'скрыта'}\n"
        f"Группа: {e(group_title) if group_title else 'не подключена'}"
    )
    return View(
        text,
        [
            [("Книга", "books"), ("Часовой пояс", "timezone")],
            [("Приватность", "privacy"), ("Группа", "group")],
            [("Напоминания: " + flags(p["reminders"]), "toggle:reminders")],
            [("Мотивация", "motivation"), ("Данные", "data")],
            [("Правила", "rules:0")],
            back(),
        ],
    )


def books(p, page=0):
    rows = [[("Добавить новую книгу", "add")]]
    b = d.active_book(p)
    if b:
        rows += [
            [("Изменить текущую книгу", "editmenu:" + b["id"])],
            [("Отложить текущую книгу", "pause")],
        ]
    paused = [b for b in p["books"] if b["status"] == "paused"]
    for b in paused[page * 8 : (page + 1) * 8]:
        rows.append([("Продолжить: " + b["title"][:45], "resume:" + b["id"])])
    nav = []
    if page:
        nav.append(("←", f"books:{page - 1}"))
    if len(paused) > (page + 1) * 8:
        nav.append(("→", f"books:{page + 1}"))
    if nav:
        rows.append(nav)
    rows += [back("settings")]
    return View(
        "<b>Мои книги</b>\nВыбери новую или продолжи отложенную. Общая серия сохраняется.", rows
    )


def compact_tree(b):
    if b.get("tree_plan") is not None:
        tree = bonsai.Tree.from_dict(b["tree_plan"])
        return bonsai.render_tree(tree, b["page"] * tree.max_parts // b["total"])
    layouts = [
        "  .\n  |",
        "  *\n /|",
        " ***\n  |\n / ",
        " *****\n  ***\n   |\n  / ",
        " *******\n *****\n   |\n  / ",
    ]
    index = next(i for i, (_, emoji, _) in enumerate(d.STAGES) if emoji == d.stage(b)[0])
    drawing = layouts[index]
    return drawing if b["seed"] % 2 else "\n".join(line[::-1] for line in drawing.splitlines())


def book(p, book_id, private=True):
    b = d.book_by_id(p, book_id)
    uid = p["owner_id"]
    emoji, title = d.stage(b)
    status = {"active": "Читаю", "paused": "На паузе", "completed": "Завершена"}[b["status"]]
    text = (
        f"<b>{e(b['title'])} — {e(b['author'])}</b>\n<pre>{e(compact_tree(b))}</pre>\n"
        f"{emoji} {title}: {d.percentage(b)}%\n"
        f"Страницы: {b['page']} из {b['total']}\nДневная норма: {b['norm']} страниц\n"
        f"Серия книги: {b['streak']} дней · Рекорд: {b['best']} дней\n"
        f"Начало: {b['start']}\nЗавершение: {b['end'] or '—'}\nСтатус: {status}"
    )
    rows = [
        [("Чтение по дням", f"history:{uid}:{book_id}:0")],
        [("Главное дерево", f"tree:{uid}"), ("Мой лес" if private else "Лес", f"forest:{uid}:0:0")],
    ]
    if private:
        rows += [[("Изменить", "editmenu:" + book_id), ("Удалить дерево", "delete:" + book_id)]]
    rows += [back("home" if private else f"forest:{uid}:{b['plot']}:0")]
    return View(text, rows, route=f"book:{uid}:{book_id}")


def history(p, book_id, page):
    b = d.book_by_id(p, book_id)
    marks = [m for m in reversed(p["marks"]) if m["book_id"] == book_id]
    text = f"<b>Чтение по дням · {e(b['title'])}</b>\nСтраницы, зачтённые через дневную норму:\n\n"
    text += (
        "\n".join(f"{m['day']}: {m['pages']} страниц" for m in marks[page * 10 : (page + 1) * 10])
        or "Пока нет отметок."
    )
    uid = p["owner_id"]
    nav = []
    if page:
        nav += [("←", f"history:{uid}:{book_id}:{page - 1}")]
    if len(marks) > (page + 1) * 10:
        nav += [("→", f"history:{uid}:{book_id}:{page + 1}")]
    return View(
        text,
        ([nav] if nav else []) + [back(f"book:{uid}:{book_id}")],
        route=f"history:{uid}:{book_id}:{page}",
    )


def main_tree(p, private=True, return_action=None):
    uid, size = p["owner_id"], len(p["tree"])
    text = (
        f"<b>Главное дерево · {e(p['name'])}</b>\nРост: {size} из 365 — {size / 365 * 100:.1f}%\n"
    )
    if private:
        text += f"Серия: {p['streak']} дней · Рекорд: {p['best']} дней\nМонеты: {p['coins']}\n"
    if p["golden"]:
        text += "\n🏆 Золотое дерево — твоя постоянная награда!"
    elif p["tree"] or p.get("tree_plan") is not None:
        text += "\n<pre>" + e(d.render_tree(p)) + "</pre>"
        if not p["tree"]:
            text += "\nПока нет частей. Отправь ✅ после чтения."
    else:
        text += "\nПока нет символов. Отправь ✅ после чтения."
    rows = []
    if not p["golden"]:
        rows += [[("Удобрить за 1 монету" if private else "Подкинуть монетку", f"fert:{uid}")]]
    rows += [
        [("Мой лес" if private else "Лес", f"forest:{uid}:0:0")],
        back(return_action or ("home" if private else f"person:{uid}")),
    ]
    return View(text, rows, "golden-tree.png" if p["golden"] else None, f"tree:{uid}")


def forest(p, plot=0, page=0, private=True):
    uid = p["owner_id"]
    bs = [b for b in p["books"] if b["plot"] == plot]
    grid = [["▫️" for _ in range(9)] for _ in range(7)]
    grid[3][4] = "🏆" if p["golden"] else "🌳"
    for b in bs:
        grid[b["y"]][b["x"]] = d.stage(b)[0]
    text = f"<b>Лес · {e(p['name'])} · участок {plot + 1}</b>\n\n"
    text += "\n".join(" ".join(row) for row in grid)
    text += "\n\nВ центре — главное дерево. Выбери дерево книги ниже."
    rows = [[(b["title"][:50], f"book:{uid}:{b['id']}")] for b in bs[page * 8 : (page + 1) * 8]]
    nav = []
    if page:
        nav.append(("Книги ←", f"forest:{uid}:{plot}:{page - 1}"))
    if len(bs) > (page + 1) * 8:
        nav.append(("Книги →", f"forest:{uid}:{plot}:{page + 1}"))
    if nav:
        rows.append(nav)
    plots = []
    if plot:
        plots.append(("Участок ←", f"forest:{uid}:{plot - 1}:0"))
    if any(b["plot"] > plot for b in p["books"]):
        plots.append(("Участок →", f"forest:{uid}:{plot + 1}:0"))
    if plots:
        rows.append(plots)
    rows += [[("Главное дерево", f"tree:{uid}")]]
    if private:
        rows += [[("Общая статистика", f"stats:{uid}")]]
    rows += [back("home" if private else f"person:{uid}")]
    return View(text, rows, route=f"forest:{uid}:{plot}:{page}")


def stats(p, now, private=True):
    s = d.statistics(p, now)
    text = (
        f"<b>Статистика · {e(p['name'])}</b>\nРегистрация: {p['registered_at'][:10]}\n"
        f"В боте: {s['days']} дней\nГлавное дерево: 1 · Рост: {len(p['tree'])}/365\n"
        f"Завершённые книги: {s['completed']}\nТекущая книга: {s['active']}\n"
        f"Книги на паузе: {s['paused']}\nЗачтённые страницы: {s['pages']}\n"
        f"Общая серия: {p['streak']} дней · Рекорд: {p['best']} дней\n\n"
    )
    text += "\n".join(f"{title}: {n}" for title, n in s["stages"].items())
    if private:
        text += f"\nМонеты: {p['coins']}"
    return View(
        text,
        [back(f"forest:{p['owner_id']}:0:0" if private else f"person:{p['owner_id']}")],
        route=f"stats:{p['owner_id']}",
    )


def motivation(p):
    text = (
        f"<b>Мотивация</b>\nЦитаты {'включены' if p['quotes_enabled'] else 'выключены'}\n"
        f"Часовой пояс: {e(p['timezone'])}\nРасписание: {', '.join(p['quote_times']) or 'пусто'}\n"
        "Цитаты приходят только в личные сообщения."
    )
    return View(
        text,
        [
            [("Добавить время", "quoteadd"), ("Удалить время", "quotedel")],
            [("Выключить" if p["quotes_enabled"] else "Включить", "toggle:quotes_enabled")],
            [("Цитата сейчас", "quote")],
            back(),
        ],
    )
