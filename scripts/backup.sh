#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/.."
mkdir -p backups
target="backups/librarybot-$(date -u +%Y%m%dT%H%M%SZ).dump"
if [ -e "$target" ]; then
  echo "A backup with this timestamp already exists." >&2
  exit 1
fi
trap 'rm -f "$target"' HUP INT TERM
if docker compose exec -T db pg_dump -U librarybot -d librarybot -Fc > "$target"; then
  echo "Backup saved: $target"
else
  rm -f "$target"
  exit 1
fi
