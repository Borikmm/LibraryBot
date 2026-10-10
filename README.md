# LibraryBot

Telegram-бот для ежедневного чтения и личного леса книг. Python 3.12, python-telegram-bot 21 и PostgreSQL. Версия 1 реализует структуру из `LibraryBot_Structure_v1.docx` от 10 октября 2026 года.

У каждого читателя свои книги, отметки, серии, монеты и главное дерево. Для работы достаточно личного диалога; группу друзей можно подключить позднее с явным согласием. Лес и статистика изначально скрыты.

## Что умеет бот

- Знакомство, первая книга и восстановление профиля из JSON.
- Одна отметка ✅ за местный календарный день; страницы ограничены остатком книги.
- Одна активная книга, пауза и продолжение, изменение всех параметров и удаление с подтверждением.
- Сохраняемые деревья книг, карта леса с участками, карточки и история чтения.
- Главное дерево из 365 видимых символов и постоянная золотая награда.
- Монета за каждый десяток серии, бесплатная защита только на следующий день после завершения книги, автоматическая защита монетой.
- Помощь своему дереву и открытым деревьям друзей с подтверждением и защитой от повторного расхода.
- Одна группа на профиль, согласие на подключение, актуальная проверка членства и независимое меню каждого участника.
- Личные цитаты по расписанию и напоминания до отметки; уведомлений в группы нет.
- Экспорт, проверка импорта и подтверждение замены профиля.

Команды: `/start`, `/menu`, `/read`, `/export`, `/cancel`. Основная отметка — сообщение ✅ в ЛС. `/start` в группе открывает публичное меню отправителя, а не приватный разговор.

## Локально на Windows

Нужны Python 3.12 и PostgreSQL 18. Скрипт создаёт отдельный кластер на `127.0.0.1:55432` внутри игнорируемой `.local`; установленная служба PostgreSQL и её базы не изменяются.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -Action Setup
```

Создайте `.env` в корне проекта с `BOT_TOKEN=...`. Токен не отправляется в GitHub. Для встроенной локальной базы достаточно токена; параметры базы скрипт сохраняет в `.local/db.env`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -Action Run
Invoke-RestMethod http://127.0.0.1:10000/health
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -Action Test
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -Action Stop
```

Логи: `.local/bot.stdout.log` и `.local/bot.stderr.log`. `Run` запускает процесс в фоне. `Stop` останавливает этот процесс и выделенный локальный PostgreSQL. При повторном запуске профили сохраняются.

Для собственной базы задайте `DATABASE_URL` и запустите напрямую:

```powershell
.venv/Scripts/python.exe main.py
```

## Быстрый запуск на сервере

Нужны Linux VPS, Docker Engine и Compose. Полная инструкция, перенос локальной базы и восстановление описаны в [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

```sh
git clone https://github.com/Borikmm/LibraryBot.git
cd LibraryBot
git switch codex/librarybot-deployment
cp .env.example .env
# Заполните BOT_TOKEN и POSTGRES_PASSWORD. Пароль — случайные латинские буквы и цифры.
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:10000/health
```

Перед запуском сервера остановите локальный экземпляр с тем же Telegram-токеном. Нужен ровно один процесс polling. Миграции применяются автоматически при старте. База сохраняется в именованном томе; её порт не опубликован наружу. Health-порт доступен только на localhost сервера.

```sh
sh scripts/backup.sh
sh scripts/restore.sh backups/librarybot-YYYYMMDDTHHMMSSZ.dump
```

`restore.sh` сначала делает резервную копию текущей базы, затем останавливает бота и восстанавливает выбранный снимок в одной транзакции. Секреты, пользовательские выгрузки и дампы не входят в Git.

## Проверки и устройство

```sh
pip install -r requirements.lock -r requirements-dev.txt
export TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/TEST_DATABASE
ruff check bot tests main.py app.py
python -m pytest -q
```

PostgreSQL-тесты используют временную схему с уникальным именем в указанной базе. Без `TEST_DATABASE_URL` или локальной `.local/db.env` они пропускаются. CI всегда поднимает PostgreSQL 18 и запускает все тесты, затем собирает Docker-образ.

- `bot/domain.py`: правила чтения, деревьев, серий и защиты, независимо от Telegram.
- `bot/storage.py`, `bot/service.py`: транзакции, блокировки профилей и уникальные дни/подтверждения.
- `bot/private.py`, `bot/groups.py`, `bot/navigation.py`, `bot/views.py`: ЛС, согласия, групповой доступ и меню.
- `bot/scheduler.py`: местная полночь, личные расписания и журнал доставок.
- `bot/backup.py`: проверка личного экспорта до изменения базы.
- `migrations/`: версия схемы; `assets/`: изображения леса и золотой награды.

Подробности хранения и границы гарантий: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Соответствие сценариям документа и результаты проверки: [docs/VERIFICATION.md](docs/VERIFICATION.md).
