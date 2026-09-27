#!/usr/bin/env bash
# Развёртывание и обновление системы на сервере. Один и тот же запуск делает и то, и другое:
# первый раз ставит docker и клонирует репозиторий, дальше подтягивает ветку и пересобирает
# то, что изменилось. Поэтому этот же скрипт годится как шаг CD.
#
#   cp deploy/deploy.env.example deploy/deploy.env   # заполнить
#   ./deploy/deploy.sh                # развернуть или обновить
#   ./deploy/deploy.sh --force        # то же, но пересобрать всё заново
#   ./deploy/deploy.sh --follow       # развернуть и остаться на логах сервера
#   ./deploy/deploy.sh --check        # только проверить доступ и настройки
#   ./deploy/deploy.sh --logs         # хвост логов сервера
#   ./deploy/deploy.sh --status       # что запущено на сервере
#
# Обновление инкрементальное: сервер подтягивает ветку и пересобирает только те образы,
# чьи файлы поменялись в пришедших коммитах. Если не изменилось ничего — ничего и не
# трогаем. Тяжёлые Valhalla и R5 с их данными переживают обновление нетронутыми.
#
# Всё, что нужно указать, лежит в deploy/deploy.env — больше ничего спрашивать не будем.
set -euo pipefail
set -o errtrace

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${DEPLOY_ENV:-$HERE/deploy.env}"
MODE="${1:-deploy}"

# Весь вывод дублируется в файл: если что-то сорвётся, будет видно на каком шаге и что
# сказал сервер. Журналы лежат рядом со скриптом и в git не попадают.
LOG_DIR="$HERE/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

STEP="подготовка"
STEP_NO=0
STEP_AT=$(date +%s)

die() { echo "Ошибка: $*" >&2; exit 1; }

step() {
  local now
  now=$(date +%s)
  [ "$STEP_NO" -gt 0 ] && echo "   шаг «$STEP» занял $((now - STEP_AT)) с"
  STEP_NO=$((STEP_NO + 1))
  STEP="$*"
  STEP_AT=$now
  echo
  echo "== [$STEP_NO] $* · $(date +%H:%M:%S)"
}

# один отчёт на выходе: удачно — сколько заняло, неудачно — на каком шаге и куда смотреть
finish() {
  local code=$?
  if [ "$code" -ne 0 ]; then
    echo
    echo "СОРВАЛОСЬ на шаге [$STEP_NO] «$STEP», код выхода $code"
    echo "Журнал запуска: $LOG"
    echo "Что было на сервере: ./deploy/deploy.sh --logs"
  else
    [ "$STEP_NO" -gt 0 ] && echo "   шаг «$STEP» занял $(($(date +%s) - STEP_AT)) с"
    echo "Журнал запуска: $LOG"
  fi
}
trap finish EXIT

[ -f "$CONFIG" ] || die "нет файла $CONFIG. Скопируйте deploy/deploy.env.example и заполните"
# shellcheck disable=SC1090
set -a; . "$CONFIG"; set +a

: "${SERVER_HOST:?укажите SERVER_HOST}"
: "${SERVER_USER:?укажите SERVER_USER}"
DEPLOY_PATH="${DEPLOY_PATH:-~/routing}"
: "${REPO_URL:?укажите REPO_URL}"
: "${DB_PASSWORD:?укажите DB_PASSWORD}"
: "${AUTH_SECRET:?укажите AUTH_SECRET}"
SERVER_PORT="${SERVER_PORT:-22}"
REPO_BRANCH="${REPO_BRANCH:-main}"
DEPLOY_KEY_PATH="${DEPLOY_KEY_PATH:-~/.ssh/routing_deploy}"
TLS="${TLS:-true}"
TRANSIT="${TRANSIT:-true}"
GPU="${GPU:-true}"
INSTALL_DOCKER="${INSTALL_DOCKER:-true}"
DOMAIN="${DOMAIN:-$SERVER_HOST}"
[ "$TLS" = "true" ] && : "${ACME_EMAIL:?для TLS укажите ACME_EMAIL}"
[ "$TLS" = "true" ] && [ "$DOMAIN" = "$SERVER_HOST" ] && die "для TLS нужен DOMAIN, а не адрес"

# --- как ходим на сервер ----------------------------------------------------
SSH_BASE=(ssh -p "$SERVER_PORT" -o StrictHostKeyChecking=accept-new)
if [ -n "${SERVER_PASSWORD:-}" ]; then
  command -v sshpass >/dev/null || die "для входа по паролю нужен sshpass (apt install sshpass)"
  SSH=(sshpass -p "$SERVER_PASSWORD" "${SSH_BASE[@]}")
else
  key="${SERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
  key="${key/#\~/$HOME}"
  [ -f "$key" ] || die "не нашёл ключ $key — укажите SERVER_SSH_KEY или SERVER_PASSWORD"
  SSH=("${SSH_BASE[@]}" -i "$key")
fi
TARGET="$SERVER_USER@$SERVER_HOST"

# Запуск команд на сервере: тело скрипта идёт в stdin, а переменные — отдельными строками
# перед ним. Через ssh окружение само не переезжает, поэтому имена нужных переменных
# перечисляются в аргументах: on_server DEPLOY_PATH REPO_URL <<'REMOTE' ... REMOTE
on_server() {
  {
    echo 'set -euo pipefail'
    local name
    for name in "$@"; do
      printf '%s=%q\n' "$name" "${!name-}"
    done
    cat
  } | "${SSH[@]}" "$TARGET" "bash -s"
}

# --- режимы без развёртывания ----------------------------------------------
case "$MODE" in
  --check)
    step "Проверяю доступ к $TARGET"
    on_server <<'REMOTE'
echo "сервер: $(hostname), $(uname -sr)"
docker --version 2>/dev/null || echo "docker не установлен — поставлю при развёртывании"
nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "видеокарты не видно"
df -h / | awk 'NR==2 {print "свободно на диске: " $4}'
free -g | awk 'NR==2 {print "памяти всего: " $2 " ГБ"}'
REMOTE
    echo; echo "Настройки: домен $DOMAIN, TLS=$TLS, транспорт=$TRANSIT, GPU=$GPU, ветка $REPO_BRANCH"
    exit 0 ;;
  --logs)
    on_server DEPLOY_PATH <<'REMOTE'
cd "$DEPLOY_PATH"
docker compose -f docker-compose.yml -f deploy/compose.server.yml logs --tail 80
REMOTE
    exit 0 ;;
  --status)
    on_server DEPLOY_PATH <<'REMOTE'
cd "$DEPLOY_PATH"
docker compose -f docker-compose.yml -f deploy/compose.server.yml ps
REMOTE
    exit 0 ;;
  deploy|--force|--follow) ;;
  *) die "не знаю режим «$MODE». Есть: --force, --follow, --check, --logs, --status" ;;
esac
FORCE=$([ "$MODE" = "--force" ] && echo yes || echo no)
# --follow: после развёртывания остаёмся на логах сервера, пока не нажмут Ctrl+C
FOLLOW=$([ "$MODE" = "--follow" ] && echo yes || echo no)

# --- профили ----------------------------------------------------------------
PROFILES=""
[ "$TRANSIT" = "true" ] && PROFILES="--profile transit"

step "Готовлю сервер $TARGET"
# Для расчёта на видеокарте серверу нужны две разные вещи, и это частая путаница:
#   1) драйвер NVIDIA на самом сервере — его ставит администратор, нужна перезагрузка;
#   2) nvidia-container-toolkit — прокидывает видеокарту внутрь контейнера, его ставим тут.
# CUDA Toolkit с сайта NVIDIA ставить не нужно: cuOpt со своей CUDA уже внутри образа.
PREP=$(on_server INSTALL_DOCKER GPU <<'REMOTE'
# ставить пакеты может либо root, либо пользователь с sudo — разбираемся один раз
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null; then
    SUDO="sudo -n"
  else
    echo "ВНИМАНИЕ: вход не под root и sudo нет — ставить пакеты не смогу" >&2
  fi
fi

if ! command -v docker >/dev/null; then
  [ "${INSTALL_DOCKER:-true}" = "true" ] || { echo "docker не установлен, а INSTALL_DOCKER=false" >&2; exit 1; }
  echo "ставлю docker"
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker
  # чтобы не требовать sudo на каждый docker: добавляем пользователя в группу docker
  [ -n "$SUDO" ] && $SUDO usermod -aG docker "$USER" && echo "нужен повторный вход в ssh, чтобы docker заработал без sudo"
fi
docker --version

gpu_ready=no
if [ "${GPU:-true}" = "true" ]; then
  if ! command -v nvidia-smi >/dev/null; then
    if lspci 2>/dev/null | grep -qi 'nvidia'; then
      echo "ВНИМАНИЕ: видеокарта NVIDIA в сервере есть, но драйвера нет." >&2
      echo "  Поставьте драйвер и перезагрузите сервер:  ubuntu-drivers install" >&2
      echo "  CUDA Toolkit с сайта NVIDIA не нужен — CUDA идёт внутри образа бэкенда." >&2
    else
      echo "ВНИМАНИЕ: видеокарты на сервере не видно (нет ни nvidia-smi, ни устройства)." >&2
    fi
    echo "  Разворачиваю без GPU: расчёт пойдёт на OR-Tools, это рабочий вариант." >&2
  else
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true
    # Ставим контейнерный тулкит, если docker ещё не знает про nvidia. Вывод apt не глушим:
    # когда шаг не удаётся, нужно видеть, на чём именно
    if ! docker info 2>/dev/null | grep -qE '^ Runtimes:.*nvidia'; then
      echo "ставлю nvidia-container-toolkit (прокидывает видеокарту в контейнер)"
      (
        set -x
        $SUDO apt-get update
        $SUDO apt-get install -y gnupg curl ca-certificates
        $SUDO install -m 0755 -d /usr/share/keyrings
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
          | $SUDO gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
          | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
          | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        $SUDO apt-get update
        $SUDO apt-get install -y nvidia-container-toolkit
      ) >&2 || echo "ВНИМАНИЕ: установка пакета не удалась — смотрите вывод apt выше" >&2
      if command -v nvidia-ctk >/dev/null; then
        $SUDO nvidia-ctk runtime configure --runtime=docker >&2 && $SUDO systemctl restart docker
      else
        echo "ВНИМАНИЕ: nvidia-ctk так и не появился — пакет nvidia-container-toolkit не встал." >&2
        echo "  Проверьте вручную:  apt-get install -y nvidia-container-toolkit" >&2
      fi
    fi

    # Готовность проверяем без скачивания образов: нужны устройство, драйвер и знание docker
    # про nvidia. Настоящую работу на видеокарте проверит уже сам бэкенд
    if ! docker info 2>/dev/null | grep -qE '^ Runtimes:.*nvidia'; then
      echo "ВНИМАНИЕ: docker не знает про среду nvidia — разворачиваю без GPU." >&2
      echo "  Что посмотреть:  docker info | grep -i runtime  и  cat /etc/docker/daemon.json" >&2
    elif [ ! -e /dev/nvidiactl ] && [ ! -e /dev/nvidia0 ]; then
      echo "ВНИМАНИЕ: устройств /dev/nvidia* нет, хотя nvidia-smi отвечает." >&2
      echo "  Обычно помогает перезагрузка сервера после установки драйвера." >&2
    else
      gpu_ready=yes
      echo "видеокарта готова: docker знает про nvidia, устройства на месте"
    fi
  fi
fi
echo "GPU_READY=$gpu_ready"
REMOTE
)
echo "$PREP"
if [ "$GPU" = "true" ] && ! grep -q 'GPU_READY=yes' <<<"$PREP"; then
  echo "   продолжаю без видеокарты: решатель cuOpt заменит OR-Tools"
  GPU=false
fi

# оверлей с видеокартой подключаем, только когда сервер её действительно отдаёт
COMPOSE_FILES="-f docker-compose.yml -f deploy/compose.server.yml"
[ "$GPU" = "true" ] && COMPOSE_FILES="$COMPOSE_FILES -f deploy/compose.gpu.yml"

# «~» в пути — это домашний каталог того пользователя, под которым мы вошли: раскрываем
# его на сервере один раз, дальше все шаги работают с готовым абсолютным путём
DEPLOY_PATH=$(on_server DEPLOY_PATH <<'REMOTE'
printf '%s\n' "${DEPLOY_PATH/#\~/$HOME}"
REMOTE
)

step "Забираю код: $REPO_BRANCH из $REPO_URL"
# сервер возвращает список того, что поменялось: по нему и решаем, что пересобирать
CHANGED=$(on_server DEPLOY_PATH REPO_URL REPO_BRANCH GITHUB_TOKEN DEPLOY_KEY_PATH <<'REMOTE'
# Приватный репозиторий: либо ssh-ключ, либо токен — смотря какой адрес у репозитория.
ASKPASS=""
FETCH_URL="$REPO_URL"
case "$REPO_URL" in
  git@*|ssh://*)
    key="${DEPLOY_KEY_PATH/#\~/$HOME}"
    if [ -f "$key" ]; then
      # IdentitiesOnly: иначе ssh предложит серверу другие свои ключи и получит отказ
      export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
      echo "беру код по ssh, ключ $key" >&2
    else
      export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
      echo "ключа $key нет — пробую ssh с ключом по умолчанию" >&2
    fi
    ;;
esac
if [ -n "${GITHUB_TOKEN:-}" ]; then
  ASKPASS="$(mktemp)"
  printf '#!/bin/sh\necho "$GIT_TOKEN"\n' > "$ASKPASS"
  chmod 700 "$ASKPASS"
  export GIT_ASKPASS="$ASKPASS" GIT_TOKEN="$GITHUB_TOKEN" GIT_TERMINAL_PROMPT=0
  # имя пользователя в адресе — чтобы git спросил только пароль и получил его от askpass
  FETCH_URL=$(printf '%s' "$REPO_URL" | sed -E 's#^https://#https://x-access-token@#')
fi
# return 0 обязателен: иначе неуспех последней проверки станет кодом выхода всего шага
cleanup() { [ -n "$ASKPASS" ] && rm -f "$ASKPASS"; return 0; }
trap cleanup EXIT

if [ ! -d "$DEPLOY_PATH/.git" ]; then
  mkdir -p "$DEPLOY_PATH"
  git clone --quiet --branch "$REPO_BRANCH" "$FETCH_URL" "$DEPLOY_PATH"
  cd "$DEPLOY_PATH"
  git remote set-url origin "$REPO_URL"   # без токена в настройках
  echo "ВСЁ"                              # первый раз собираем всё
else
  cd "$DEPLOY_PATH"
  git remote set-url origin "$REPO_URL"
  before=$(git rev-parse HEAD)
  git fetch --quiet "$FETCH_URL" "$REPO_BRANCH"
  git checkout --quiet -B "$REPO_BRANCH" FETCH_HEAD
  after=$(git rev-parse HEAD)
  if [ "$before" = "$after" ]; then
    echo "НИЧЕГО"
  else
    git diff --name-only "$before" "$after"
  fi
fi
git --no-pager log -1 --format='версия: %h %s' >&2
REMOTE
)

# что пересобирать: образ трогаем, только если поменялись его файлы
build_backend=no; build_web=no; build_r5=no; changed_compose=no
case "$CHANGED" in
  *ВСЁ*) build_backend=yes; build_web=yes; build_r5=yes; changed_compose=yes ;;
  *НИЧЕГО*) echo "новых коммитов нет" ;;
esac
while IFS= read -r file; do
  case "$file" in
    backend/*) build_backend=yes ;;
    frontend/*|mobile/*|deploy/nginx/*) build_web=yes ;;
    transit/r5_service/*|transit/osm_extract/*) build_r5=yes ;;
    docker-compose.yml|deploy/compose*.yml) changed_compose=yes ;;
  esac
done <<< "$CHANGED"
if [ "$FORCE" = "yes" ]; then
  echo "--force: пересобираю всё"
  build_backend=yes; build_web=yes; build_r5=yes; changed_compose=yes
fi

TO_BUILD=""
[ "$build_backend" = "yes" ] && TO_BUILD="$TO_BUILD backend"
[ "$build_web" = "yes" ] && TO_BUILD="$TO_BUILD web"
[ "$build_r5" = "yes" ] && [ "$TRANSIT" = "true" ] && TO_BUILD="$TO_BUILD r5 r5-osm"
if [ -n "$TO_BUILD" ]; then
  echo "пересобираю:$TO_BUILD"
else
  echo "пересобирать нечего — проверю, что всё запущено"
fi

step "Кладу настройки в $DEPLOY_PATH/.env"
# то, что нужно compose на сервере: пароли и домен. Остальное у сервисов есть по умолчанию
SERVER_ENV="# создан deploy/deploy.sh — правьте deploy.env и запускайте скрипт заново
DOMAIN=$DOMAIN
TLS=$TLS
DB_PASSWORD=$DB_PASSWORD
AUTH_SECRET=$AUTH_SECRET
ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}"
for name in R5_WALKING_SPEED_KMH R5_TIMEOUT_SECONDS R5_MATRIX_MAX_POINTS \
            CUOPT_TIME_LIMIT_SECONDS CUOPT_MAX_TIME_LIMIT_SECONDS CUOPT_DISTANCE_WEIGHT; do
  value="${!name-}"
  [ -n "$value" ] && SERVER_ENV="$SERVER_ENV
$name=$value"
done
on_server DEPLOY_PATH SERVER_ENV <<'REMOTE'
printf '%s\n' "$SERVER_ENV" > /tmp/routing.env
install -m 600 /tmp/routing.env "$DEPLOY_PATH/.env"
rm -f /tmp/routing.env
echo "настройки записаны"
REMOTE

step "Собираю и поднимаю"
on_server DEPLOY_PATH COMPOSE_FILES PROFILES TO_BUILD <<'REMOTE'
cd "$DEPLOY_PATH"
COMPOSE="docker compose $COMPOSE_FILES $PROFILES"
# сборка идёт со слоёным кэшом: неизменившиеся зависимости не скачиваются заново
# shellcheck disable=SC2086
[ -n "$TO_BUILD" ] && $COMPOSE build $TO_BUILD
# up без --build: поднимает недостающее и перезапускает только то, у чего сменился образ
# или настройки. Базу, Valhalla и R5 с их томами это не трогает
# shellcheck disable=SC2086
$COMPOSE up -d --remove-orphans
REMOTE

step "Накатываю миграции базы"
on_server DEPLOY_PATH <<'REMOTE'
cd "$DEPLOY_PATH"
for i in $(seq 1 30); do
  docker compose -f docker-compose.yml -f deploy/compose.server.yml exec -T postgres pg_isready -U routing -d routing >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "база не отвечает минуту — смотрите docker compose logs postgres" >&2; exit 1; }
  sleep 2
done
DB_CONTAINER=routing_db bash db/apply_migrations.sh
REMOTE

if [ "$TLS" = "true" ]; then
  step "Сертификат для $DOMAIN"
  on_server DEPLOY_PATH DOMAIN ACME_EMAIL <<'REMOTE'
cd "$DEPLOY_PATH"
COMPOSE="docker compose -f docker-compose.yml -f deploy/compose.server.yml"
if $COMPOSE run --rm --entrypoint sh certbot -c "test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
  echo "сертификат уже есть, обновится сам"
else
  $COMPOSE run --rm --entrypoint sh certbot -c \
    "certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --email $ACME_EMAIL --agree-tos --no-eff-email --non-interactive"
  echo "сертификат выпущен"
fi
$COMPOSE up -d certbot
REMOTE
fi

step "Проверяю, что поднялось"
on_server DEPLOY_PATH <<'REMOTE'
cd "$DEPLOY_PATH"
COMPOSE="docker compose -f docker-compose.yml -f deploy/compose.server.yml"
# Первый запуск долгий: пока Valhalla строит тайлы, бэкенд уже поднимается, но здоровым
# становится не сразу. Показываем, что говорят контейнеры, — иначе ожидание выглядит
# зависанием, и непонятно, поднимается система или падает по кругу
shown=""
for i in $(seq 1 60); do
  state=$($COMPOSE ps --format '{{.Name}} {{.Status}}' | grep routing_backend || true)
  case "$state" in *healthy*) echo "бэкенд здоров"; break;; esac
  fresh=$($COMPOSE logs --tail 3 backend 2>/dev/null || true)
  if [ -n "$fresh" ] && [ "$fresh" != "$shown" ]; then
    printf '%s\n' "$fresh" | sed 's/^/   | /'
    shown="$fresh"
  fi
  [ $((i % 6)) = 0 ] && echo "   жду бэкенд, прошло $((i * 5)) с: ${state:-контейнера ещё нет}"
  if [ "$i" = 60 ]; then
    echo "бэкенд не стал здоровым за 5 минут — вот что он пишет:" >&2
    $COMPOSE logs --tail 40 backend >&2 || true
  fi
  sleep 5
done
$COMPOSE ps --format '{{.Name}}\t{{.Status}}'
curl -fsS -o /dev/null -w 'веб: HTTP %{http_code}\n' http://localhost/healthz 2>/dev/null \
  || { echo "веб пока не отвечает, вот его логи:"; $COMPOSE logs --tail 20 web || true; }
# маршрутизаторы собираются долго и после развёртывания: говорим, готовы ли они
for name in routing_valhalla routing_r5; do
  line=$($COMPOSE ps --format '{{.Name}} {{.Status}}' | grep "$name" || true)
  case "$line" in
    *healthy*) echo "$name: готов" ;;
    "") ;;
    *) echo "$name: ещё собирает данные — это нормально, следите ./deploy/deploy.sh --logs" ;;
  esac
done
REMOTE

if [ "$FOLLOW" = "yes" ]; then
  step "Логи сервера · выход Ctrl+C"
  on_server DEPLOY_PATH <<'REMOTE'
cd "$DEPLOY_PATH"
docker compose -f docker-compose.yml -f deploy/compose.server.yml logs -f --tail 30
REMOTE
fi

echo
if [ "$TLS" = "true" ]; then
  echo "Готово. Диспетчер: https://$DOMAIN  ·  бригады: https://$DOMAIN/mobile/"
else
  echo "Готово. Диспетчер: http://$SERVER_HOST  ·  бригады: http://$SERVER_HOST/mobile/"
fi
if [ -n "${ADMIN_PASSWORD:-}" ]; then
  echo "Вход: admin с паролем из ADMIN_PASSWORD."
else
  echo "Первый вход: admin / admin — смените пароль в «Справочники» → «Пользователи»."
fi
