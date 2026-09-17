#!/usr/bin/env bash
# Накатывает на уже поднятую БД миграции из db/init, которых в ней ещё нет.
#
# Зачем: файлы db/init выполняются сами только при первом старте контейнера
# (docker-entrypoint-initdb.d). Когда в репозитории появляется новый файл, на живой базе
# его надо накатить руками — этим и занимается скрипт.
#
# Что применялось, помнит таблица schema_migration в самой БД. Файлы 001–003 (схема, справочники,
# демоданные) — только для первого старта контейнера: скрипт их не выполняет, а при первом запуске
# отмечает применёнными. Миграции 004 и дальше написаны идемпотентно (IF NOT EXISTS,
# UPDATE ... WHERE ... IS NULL), поэтому повторный запуск скрипта безопасен.
#
#   db/apply_migrations.sh            накатить всё, чего нет в БД
#   db/apply_migrations.sh --status   показать, что накачено, а что ждёт
#
# Переменные окружения: DB_CONTAINER (по умолчанию routing_db), PGDATABASE, PGUSER.
# Если контейнер не запущен, скрипт идёт локальным psql на PGHOST (по умолчанию localhost).
set -euo pipefail

INIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/init"
CONTAINER="${DB_CONTAINER:-routing_db}"
DATABASE="${PGDATABASE:-routing}"
USERNAME="${PGUSER:-routing}"
BOOTSTRAP_FILES="001_schema.sql 002_seed.sql 003_mock_data.sql"

# Выполняет psql: в контейнере, если он поднят, иначе локально.
# client_min_messages=warning убирает «already exists, skipping» — при повторном прогоне
# идемпотентных миграций такими сообщениями завален весь вывод, а ошибки всё равно видны.
psql_run() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
    docker exec -i -e PGOPTIONS='-c client_min_messages=warning' "$CONTAINER" psql -v ON_ERROR_STOP=1 -X -q -U "$USERNAME" -d "$DATABASE" "$@"
  elif command -v psql >/dev/null; then
    PGHOST="${PGHOST:-localhost}" PGPASSWORD="${PGPASSWORD:-routing}" \
      PGOPTIONS='-c client_min_messages=warning' psql -v ON_ERROR_STOP=1 -X -q -U "$USERNAME" -d "$DATABASE" "$@"
  else
    echo "Не нашёл ни контейнера $CONTAINER, ни psql на хосте: поднимите БД (docker compose up -d postgres)" >&2
    exit 1
  fi
}

psql_run -c "
CREATE TABLE IF NOT EXISTS schema_migration (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE schema_migration IS 'Какие файлы db/init уже накачены (db/apply_migrations.sh)';"

# Первый запуск на живой базе: схема и демоданные в ней уже есть с первого старта контейнера.
for bootstrap in $BOOTSTRAP_FILES; do
  psql_run -c "INSERT INTO schema_migration (filename) VALUES ('$bootstrap') ON CONFLICT DO NOTHING;"
done

applied="$(psql_run -tA -c 'SELECT filename FROM schema_migration;')"

pending=()
for path in "$INIT_DIR"/*.sql; do
  name="$(basename "$path")"
  grep -qx "$name" <<<"$applied" || pending+=("$name")
done

if [[ "${1:-}" == "--status" ]]; then
  echo "Накачено: $(grep -c . <<<"$applied") файлов"
  if ((${#pending[@]})); then printf 'Ждёт: %s\n' "${pending[@]}"; else echo "Ждёт: ничего"; fi
  exit 0
fi

if ((${#pending[@]} == 0)); then
  echo "Новых миграций нет — БД на последней версии"
  exit 0
fi

for name in "${pending[@]}"; do
  echo "== $name"
  psql_run -f - < "$INIT_DIR/$name"
  psql_run -c "INSERT INTO schema_migration (filename) VALUES ('$name') ON CONFLICT DO NOTHING;"
done

echo "Готово: накачено ${#pending[@]}"
