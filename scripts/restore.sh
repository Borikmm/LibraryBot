#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo 'Usage: sh scripts/restore.sh backups/file.dump' >&2
  exit 1
fi
backup="$1"
docker compose exec -T db pg_restore --list < "$backup" > /dev/null
sh scripts/backup.sh
docker compose stop bot
if docker compose exec -T db pg_restore -U librarybot -d librarybot --clean --if-exists --single-transaction < "$backup"; then
  if [ "${RESTORE_START_BOT:-1}" = "1" ]; then
    docker compose up -d bot
  fi
else
  echo 'Restore failed; bot remains stopped. Review the error before restarting.' >&2
  exit 1
fi
