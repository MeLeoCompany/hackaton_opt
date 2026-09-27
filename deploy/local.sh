#!/usr/bin/env bash
# Локальный запуск: всё на одной машине, без домена и сертификата.
# Ничего заполнять не нужно — ни deploy.env, ни DNS.
#
#   ./deploy/local.sh            # поднять (или обновить) и дождаться готовности
#   ./deploy/local.sh --light    # без общественного транспорта: быстрее и легче по памяти
#
# Видеокарта не обязательна: без неё расчёт идёт на OR-Tools, скрипт скажет об этом сам.
#   ./deploy/local.sh --stop     # остановить, данные сохранить
#   ./deploy/local.sh --reset    # остановить и стереть данные вместе с томами
#   ./deploy/local.sh --logs     # хвост логов
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-up}"
PROFILES="--profile transit"
[ "$MODE" = "--light" ] && { PROFILES=""; MODE=up; }

command -v docker >/dev/null || { echo "нет docker — поставьте Docker Desktop или docker engine" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker не запущен — запустите Docker Desktop" >&2; exit 1; }

# Видеокарта нужна только решателю cuOpt. Если её нет, базовый compose всё равно попросил бы
# у docker устройство GPU и контейнер бэкенда не создался бы — снимаем это требование
# оверлеем. Система поднимается целиком, планы считает OR-Tools на процессоре.
FILES="-f docker-compose.yml"
if docker info 2>/dev/null | grep -qE '^ Runtimes:.*nvidia'; then
  SOLVER="cuOpt на видеокарте"
else
  FILES="$FILES -f deploy/compose.nogpu.yml"
  SOLVER="OR-Tools на процессоре (видеокарты NVIDIA не видно)"
fi
# shellcheck disable=SC2086
compose() { docker compose $FILES $PROFILES "$@"; }

case "$MODE" in
  --stop)  compose down; exit 0 ;;
  --reset) compose down -v; echo "данные стёрты: следующий запуск соберёт всё заново"; exit 0 ;;
  --logs)  compose logs --tail 80 -f; exit 0 ;;
  up) ;;
  *) echo "не знаю режим «$MODE». Есть: --light, --stop, --reset, --logs" >&2; exit 1 ;;
esac

echo "== Поднимаю систему · расчёт: $SOLVER"
compose up -d --build

echo "== Жду базу и накатываю миграции"
for i in $(seq 1 30); do
  compose exec -T postgres pg_isready -U routing -d routing >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "база не отвечает минуту — смотрите docker compose logs postgres" >&2; exit 1; }
  sleep 2
done
bash db/apply_migrations.sh

echo "== Жду бэкенд"
for i in $(seq 1 60); do
  state=$(compose ps --format '{{.Name}} {{.Status}}' | grep routing_backend || true)
  case "$state" in *healthy*) break ;; esac
  [ $((i % 6)) = 0 ] && echo "   жду, прошло $((i * 5)) с: ${state:-контейнера ещё нет}"
  [ "$i" = 60 ] && echo "   бэкенд не стал здоровым за 5 минут — смотрите ./deploy/local.sh --logs" >&2
  sleep 5
done

compose ps --format '{{.Name}}\t{{.Status}}'
cat <<'TXT'

Готово:
  Диспетчер   http://localhost:5173
  Бригады     http://localhost:5175
  API         http://localhost:8000/docs
Первый вход: admin / admin — смените пароль в «Справочники» → «Пользователи».

Первый запуск долгий: Valhalla качает карту ЦФО (~877 МБ) и строит тайлы, R5 после этого
собирает транспортный граф. Данные остаются в томах docker, следующие запуски быстрые.
TXT
