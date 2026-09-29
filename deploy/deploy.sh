#!/usr/bin/env bash
# Развёртывание и обновление системы на сервере. Один и тот же запуск делает и то, и другое:
# первый раз ставит docker и клонирует репозиторий, дальше подтягивает ветку и пересобирает
# то, что изменилось. Поэтому этот же скрипт годится как шаг CD.
#
#   cp deploy/deploy.env.example deploy/deploy.env   # заполнить
#   ./deploy/deploy.sh                # развернуть или обновить
#   ./deploy/deploy.sh --force        # то же, но пересобрать всё заново
#   ./deploy/deploy.sh --transit      # пересобрать транспорт: карту R5 и его сеть заново
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
# «~» в deploy.env раскрывает наш же шелл при чтении файла — и на сервер уезжает домашний
# каталог этой машины. Возвращаем путям вид «~/…», чтобы их развернул уже сервер: там
# домашний каталог другой (обычно /root), и ключ по чужому пути не найдётся
DEPLOY_PATH="${DEPLOY_PATH/#$HOME\//\~/}"
DEPLOY_KEY_PATH="${DEPLOY_KEY_PATH/#$HOME\//\~/}"
TLS="${TLS:-true}"
TRANSIT="${TRANSIT:-true}"
GPU="${GPU:-true}"
INSTALL_DOCKER="${INSTALL_DOCKER:-true}"
R5_WORKERS="${R5_WORKERS:-3}"
R5_MAX_MEMORY="${R5_MAX_MEMORY:-6G}"
R5_CLIENT_CONCURRENCY="${R5_CLIENT_CONCURRENCY:-$R5_WORKERS}"
[[ "$R5_WORKERS" =~ ^[1-9][0-9]*$ ]] || die "R5_WORKERS должен быть положительным целым"
[[ "$R5_CLIENT_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || \
  die "R5_CLIENT_CONCURRENCY должен быть положительным целым"
[ "$R5_CLIENT_CONCURRENCY" -le "$R5_WORKERS" ] || \
  die "R5_CLIENT_CONCURRENCY не должен превышать R5_WORKERS"
DOMAIN="${DOMAIN:-$SERVER_HOST}"
[ "$TLS" = "true" ] && : "${ACME_EMAIL:?для TLS укажите ACME_EMAIL}"
[ "$TLS" = "true" ] && [ "$DOMAIN" = "$SERVER_HOST" ] && die "для TLS нужен DOMAIN, а не адрес"

# --- доступ к репозиторию: ловим типовые ошибки до выхода на сервер ----------
case "$REPO_URL" in
  https://*)
    if [ -z "${GITHUB_TOKEN:-}" ]; then
      echo "REPO_URL по https, токена нет — попробую ключом $DEPLOY_KEY_PATH с сервера." >&2
      echo "  Если ключа там нет, забрать приватный репозиторий не выйдет: задайте токен" >&2
      echo "  или пропишите ssh-адрес git@github.com:<владелец>/<репозиторий>.git" >&2
    else
      case "$GITHUB_TOKEN" in
        ghp_*|github_pat_*|gho_*|ghs_*|ghu_*) ;;
        *)
          echo "Внимание: GITHUB_TOKEN не похож на токен GitHub." >&2
          echo "  Токены начинаются с github_pat_ (fine-grained) или ghp_ (classic)." >&2
          echo "  Похоже, в поле лежит случайная строка — GitHub ответит «Invalid username or token»." >&2
          echo "  Либо вставьте настоящий токен, либо переключитесь на ssh-адрес с ключом." >&2
          ;;
      esac
    fi
    ;;
esac

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
    # трассировку включаем после присваиваний: иначе пароли и токен попадут в лог.
    # дальше видно каждую команду, которая выполняется на сервере — сразу понятно,
    # на чём именно споткнулись, а не «шаг упал»
    echo 'PS4="+ [сервер] "'
    echo 'set -x'
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
df -h / | awk 'NR==2 {print "свободно на диске: " $4}'
free -g | awk 'NR==2 {print "памяти всего: " $2 " ГБ"}'

# видеокарта: по пунктам, чтобы сразу было видно, какого звена не хватает
echo "— видеокарта —"
if nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null; then
  echo "  драйвер: на месте"
else
  echo "  драйвер: нет (nvidia-smi не отвечает) — cuOpt не поедет"
fi
if command -v nvidia-ctk >/dev/null; then
  echo "  тулкит: $(nvidia-ctk --version 2>/dev/null | head -1)"
else
  echo "  тулкит: нет (nvidia-ctk не найден)"
fi
if docker info 2>/dev/null | grep -qE '^ Runtimes:.*nvidia'; then
  echo "  docker: среда nvidia подключена"
else
  echo "  docker: про nvidia не знает — нужен nvidia-ctk runtime configure --runtime=docker"
fi
if ls /dev/nvidia* >/dev/null 2>&1; then
  echo "  устройства: $(ls /dev/nvidia* | tr '\n' ' ')"
else
  echo "  устройства: /dev/nvidia* нет — обычно помогает перезагрузка"
fi
# итоговая проверка — настоящим запуском контейнера, если образ уже есть или качается
if docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L 2>/dev/null; then
  echo "  ИТОГ: контейнер видит видеокарту, cuOpt поедет"
else
  echo "  ИТОГ: из контейнера видеокарта не видна — развернётся без GPU, на OR-Tools"
fi
REMOTE
    echo; echo "Настройки: домен $DOMAIN, TLS=$TLS, транспорт=$TRANSIT, GPU=$GPU, ветка $REPO_BRANCH"
    exit 0 ;;
  --logs)
    on_server DEPLOY_PATH TRANSIT <<'REMOTE'
cd "$DEPLOY_PATH"
# с профилем transit: иначе журналы r5 и подготовки карты остаются за кадром
profile=""
[ "$TRANSIT" = "true" ] && profile="--profile transit"
docker compose -f docker-compose.yml -f deploy/compose.server.yml $profile logs --tail 80
REMOTE
    exit 0 ;;
  --status)
    on_server DEPLOY_PATH TRANSIT <<'REMOTE'
cd "$DEPLOY_PATH"
profile=""
[ "$TRANSIT" = "true" ] && profile="--profile transit"
docker compose -f docker-compose.yml -f deploy/compose.server.yml $profile ps
REMOTE
    exit 0 ;;
  deploy|--force|--follow|--transit) ;;
  *) die "не знаю режим «$MODE». Есть: --force, --transit, --follow, --check, --logs, --status" ;;
esac
FORCE=$([ "$MODE" = "--force" ] && echo yes || echo no)
# транспорт (профиль transit) собирается долго и живёт в своих томах: карта-экстракт и
# сеть R5. Обычное обновление их не трогает, а этот флаг просит собрать их заново
REBUILD_TRANSIT=$([ "$MODE" = "--transit" ] && echo yes || echo no)
[ "$REBUILD_TRANSIT" = "yes" ] && [ "$TRANSIT" != "true" ] && \
  die "--transit при TRANSIT=false: включите TRANSIT=true в deploy/deploy.env"
# --follow: после развёртывания остаёмся на логах сервера, пока не нажмут Ctrl+C
FOLLOW=$([ "$MODE" = "--follow" ] && echo yes || echo no)

# --- профили ----------------------------------------------------------------
PROFILES=""
[ "$TRANSIT" = "true" ] && PROFILES="--profile transit"

step "Готовлю сервер $TARGET"
# Для расчёта на видеокарте серверу нужны две разные вещи, и это частая путаница:
#   1) драйвер NVIDIA на самом сервере — ставим его из репозитория дистрибутива, модуль
#      собирает dkms; если модуль удаётся загрузить сразу, перезагрузка не нужна;
#   2) nvidia-container-toolkit — прокидывает видеокарту внутрь контейнера, ставим следом.
# CUDA Toolkit с сайта NVIDIA ставить не нужно: cuOpt со своей CUDA уже внутри образа.
# tee: то же самое и на экран по ходу дела, и в переменную для разбора ниже
PREP=$(on_server INSTALL_DOCKER GPU <<'REMOTE' | tee /dev/stderr
# ставить пакеты может либо root, либо пользователь с sudo — разбираемся один раз
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null; then
    SUDO="sudo -n"
  else
    echo "ВНИМАНИЕ: вход не под root и sudo нет — ставить пакеты не смогу" >&2
  fi
fi

# git на сервере нужен самому деплою: код забирается там, а не заливается отсюда.
# В чистых образах Ubuntu его нет, и без этой проверки шаг «забираю код» падал бы
# с «command not found», что читалось как отказ в доступе к репозиторию
if ! command -v git >/dev/null; then
  echo "ставлю git"
  $SUDO apt-get update >&2
  $SUDO apt-get install -y git >&2
fi
git --version

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
# «драйвер работает» — это не наличие nvidia-smi, а то, что он отвечает: после установки
# пакетов утилита есть, а модуля в ядре может ещё не быть
gpu_live() { nvidia-smi -L >/dev/null 2>&1; }

if [ "${GPU:-true}" = "true" ]; then
  # Видеокарта в сервере есть, а драйвера нет — ставим сами, как советует NVIDIA для Ubuntu:
  # пакет драйвера из репозитория дистрибутива плюс заголовки ядра, чтобы dkms собрал модуль.
  # Готовые подписанные модули (linux-modules-nvidia-*) не берём: в архиве они регулярно
  # отстают от версии драйвера, и apt упирается в неразрешимые зависимости.
  if ! gpu_live && lspci 2>/dev/null | grep -qi 'nvidia'; then
    if apt-mark showhold 2>/dev/null | grep -qE '^(nvidia|linux-(image|headers|modules))'; then
      echo "ВНИМАНИЕ: пакеты драйвера или ядра закреплены провайдером — сам их не трогаю." >&2
      echo "  Поставьте драйвер вручную:  ubuntu-drivers install" >&2
    else
      echo "видеокарта NVIDIA есть, драйвера нет — ставлю драйвер"
      (
        $SUDO apt-get update
        $SUDO apt-get install -y ubuntu-drivers-common
        # какой драйвер подходит этой видеокарте, знает сам дистрибутив
        driver=$(ubuntu-drivers devices 2>/dev/null | awk '/recommended/ {print $3}' | head -1)
        [ -n "$driver" ] || driver=$(apt-cache search '^nvidia-driver-[0-9]+-open$' \
          | awk '{print $1}' | sort -V | tail -1)
        [ -n "$driver" ] || { echo "не нашёл пакет драйвера в репозитории" >&2; exit 1; }
        # графической оболочки на сервере нет: headless-вариант того же драйвера ставит
        # ядро драйвера и утилиты без иксов — на несколько сотен мегабайт меньше
        headless=$(echo "$driver" | sed 's/^nvidia-driver-/nvidia-headless-/')
        branch=$(echo "$driver" | sed -n 's/^nvidia-driver-\([0-9]\+\).*/\1/p')
        echo "подходит $driver, ставлю $headless"
        # без заголовков ядра dkms молча пропускает сборку, поэтому они идут первыми
        $SUDO apt-get install -y "linux-headers-$(uname -r)"
        $SUDO apt-get install -y "$headless" "nvidia-utils-$branch" \
          || $SUDO apt-get install -y "$driver"
        $SUDO dkms autoinstall -k "$(uname -r)" || true
        # перезагрузка не нужна, если nouveau удаётся выгрузить и модуль встаёт сразу
        $SUDO modprobe -r nouveau 2>/dev/null || true
        $SUDO modprobe nvidia && $SUDO modprobe nvidia_uvm
      ) >&2 || echo "ВНИМАНИЕ: установка драйвера не удалась." >&2
      if gpu_live; then
        echo "драйвер поставлен и работает без перезагрузки"
      elif command -v nvidia-smi >/dev/null; then
        echo "ВНИМАНИЕ: драйвер установлен, но ядро его ещё не отдаёт." >&2
        echo "  Перезагрузите сервер и запустите деплой снова:  reboot" >&2
      fi
    fi
  fi

  if ! gpu_live; then
    if lspci 2>/dev/null | grep -qi 'nvidia'; then
      echo "ВНИМАНИЕ: видеокарта NVIDIA в сервере есть, но драйвер не отвечает." >&2
      echo "  CUDA Toolkit с сайта NVIDIA не нужен — CUDA идёт внутри образа бэкенда." >&2
    else
      echo "ВНИМАНИЕ: видеокарты на сервере не видно (нет ни nvidia-smi, ни устройства)." >&2
    fi
    echo "  Разворачиваю без GPU: расчёт пойдёт на OR-Tools, это рабочий вариант." >&2
  else
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || true

    # Сначала смотрим, работает ли уже: если видеокарта видна из контейнера, в систему
    # не лезем вовсе. Так настройки, сделанные провайдером образа, остаются нетронутыми
    if docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L >/dev/null 2>&1; then
      gpu_ready=yes
      echo "видеокарта уже доступна из контейнера — ничего не трогаю"
    else
      echo "ставлю nvidia-container-toolkit (прокидывает видеокарту в контейнер)"
      # Часть пакетов может быть зафиксирована провайдером (apt-mark hold). Ломать эту
      # фиксацию нельзя: под неё подобраны версии всей связки. Поэтому подстраиваемся —
      # ставим тулкит ровно той версии, что стоит у закреплённой библиотеки
      held=$(apt-mark showhold 2>/dev/null | grep -E 'nvidia-container' | tr '\n' ' ' || true)
      pinned=$(dpkg-query -W -f='${Version}' libnvidia-container1 2>/dev/null || true)
      # Закрепить можно и пакет, который не установлен. Тогда ломать нечего: фиксация
      # просто не даёт его поставить. Разделяем эти два случая
      held_present=""; held_absent=""
      for pkg in $held; do
        if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed'; then
          held_present="$held_present $pkg"
        else
          held_absent="$held_absent $pkg"
        fi
      done
      held_present="${held_present# }"; held_absent="${held_absent# }"
      if [ -n "$held_absent" ] && [ -z "$held_present" ]; then
        echo "  закреплены, но не установлены: $held_absent" >&2
        echo "  ставлю их и возвращаю фиксацию обратно — заменять в системе нечего" >&2
      fi
      (
        $SUDO apt-get update
        $SUDO apt-get install -y gnupg curl ca-certificates
        $SUDO install -m 0755 -d /usr/share/keyrings
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
          | $SUDO gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
          | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
          | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        $SUDO apt-get update
        if [ -n "$held_present" ] && [ -n "$pinned" ]; then
          # установленные библиотеки провайдера не трогаем: берём тулкит их же версии
          $SUDO apt-get install -y \
            "nvidia-container-toolkit=$pinned" "nvidia-container-toolkit-base=$pinned"
        elif [ -n "$held_absent" ]; then
          # снимаем фиксацию только с неустановленных пакетов и сразу возвращаем её
          $SUDO apt-mark unhold $held_absent
          $SUDO apt-get install -y \
            nvidia-container-toolkit nvidia-container-toolkit-base \
            libnvidia-container-tools libnvidia-container1 || true
          $SUDO apt-mark hold $held_absent
          command -v nvidia-ctk >/dev/null
        else
          $SUDO apt-get install -y \
            nvidia-container-toolkit nvidia-container-toolkit-base \
            libnvidia-container-tools libnvidia-container1
        fi
      ) >&2 || {
        echo "ВНИМАНИЕ: установка не удалась." >&2
        if [ -n "$held_present" ]; then
          echo "  Провайдер зафиксировал установленные пакеты: $held_present" >&2
          echo "  Версия закреплённой библиотеки: ${pinned:-неизвестна}" >&2
          echo "  Фиксацию я намеренно не снимаю — под неё подобрана вся связка." >&2
          echo "  Если решите снять сами:  apt-mark unhold $held_present && ./deploy/deploy.sh" >&2
        elif [ -n "$held_absent" ]; then
          echo "  Закреплены (но не установлены): $held_absent" >&2
          echo "  Я снимал фиксацию на время установки и вернул её обратно." >&2
        fi
        echo "  Откуда apt берёт версии:" >&2
        apt-cache policy nvidia-container-toolkit nvidia-container-toolkit-base \
          libnvidia-container-tools libnvidia-container1 >&2 2>/dev/null || true
      }
      if command -v nvidia-ctk >/dev/null; then
        $SUDO nvidia-ctk runtime configure --runtime=docker >&2 && $SUDO systemctl restart docker
      fi
      # решает не наличие пакетов, а то, видно ли видеокарту из контейнера на самом деле
      if docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L >/dev/null 2>&1; then
        gpu_ready=yes
        echo "видеокарта доступна из контейнера"
      else
        echo "ВНИМАНИЕ: из контейнера видеокарта не видна — разворачиваю без GPU." >&2
        echo "  Проверить по шагам:  ./deploy/deploy.sh --check" >&2
      fi
    fi
  fi
fi
echo "GPU_READY=$gpu_ready"
REMOTE
)
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
if ! CHANGED=$(on_server DEPLOY_PATH REPO_URL REPO_BRANCH GITHUB_TOKEN DEPLOY_KEY_PATH <<'REMOTE'
# Приватный репозиторий: либо ssh-ключ, либо токен — смотря какой адрес у репозитория.
# git не должен ничего спрашивать: терминала нет, и вопрос обернулся бы «не могу прочитать
# имя пользователя» вместо внятной ошибки
export GIT_TERMINAL_PROMPT=0
command -v git >/dev/null || { echo "на сервере нет git: apt-get install -y git" >&2; exit 1; }
ASKPASS=""
FETCH_URL="$REPO_URL"
key="${DEPLOY_KEY_PATH/#\~/$HOME}"

# https-адрес без токена, но на сервере лежит ключ — идём ключом. Так работает и тогда,
# когда в настройках остался https, а доступ заведён как deploy key
case "$REPO_URL" in
  https://github.com/*)
    if [ -z "${GITHUB_TOKEN:-}" ] && [ -f "$key" ]; then
      FETCH_URL="git@github.com:${REPO_URL#https://github.com/}"
      REPO_URL="$FETCH_URL"
      echo "токена нет, но есть ключ $key — беру код по ssh" >&2
    fi
    ;;
esac
case "$REPO_URL" in
  git@*|ssh://*)
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

# Запасной путь: токен мог протухнуть или быть скопирован с ошибкой. Если на сервере
# лежит рабочий ключ — переходим на него, а не валим весь деплой из-за одной строки
SSH_FALLBACK=""
case "$FETCH_URL" in
  https://github.com/*|https://x-access-token@github.com/*)
    [ -f "$key" ] && SSH_FALLBACK="git@github.com:${REPO_URL#https://github.com/}"
    ;;
esac
use_ssh() {
  export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
  unset GIT_ASKPASS GIT_TOKEN
  FETCH_URL="$SSH_FALLBACK"
  REPO_URL="$SSH_FALLBACK"
  echo "по https не пустили — перехожу на ssh-ключ $key" >&2
}

if [ ! -d "$DEPLOY_PATH/.git" ]; then
  mkdir -p "$DEPLOY_PATH"
  if ! git clone --quiet --branch "$REPO_BRANCH" "$FETCH_URL" "$DEPLOY_PATH"; then
    [ -n "$SSH_FALLBACK" ] || exit 1
    use_ssh
    rm -rf "$DEPLOY_PATH"
    git clone --quiet --branch "$REPO_BRANCH" "$FETCH_URL" "$DEPLOY_PATH"
  fi
  cd "$DEPLOY_PATH"
  git remote set-url origin "$REPO_URL"   # без токена в настройках
  echo "ВСЁ"                              # первый раз собираем всё
else
  cd "$DEPLOY_PATH"
  git remote set-url origin "$REPO_URL"
  before=$(git rev-parse HEAD)
  if ! git fetch --quiet "$FETCH_URL" "$REPO_BRANCH"; then
    [ -n "$SSH_FALLBACK" ] || exit 1
    use_ssh
    git remote set-url origin "$REPO_URL"
    git fetch --quiet "$FETCH_URL" "$REPO_BRANCH"
  fi
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
); then
  echo
  echo "Сервер не смог забрать код. Обычные причины:" >&2
  echo "  · https-адрес и негодный GITHUB_TOKEN — GitHub отвечает «Invalid username or token»;" >&2
  echo "  · ssh-адрес, а ключа DEPLOY_KEY_PATH на сервере нет или он не добавлен в Deploy keys." >&2
  echo "Проверить ключ прямо с сервера:  ssh -i ~/.ssh/routing_deploy -T git@github.com" >&2
  die "нет доступа к $REPO_URL"
fi

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
if [ "$REBUILD_TRANSIT" = "yes" ]; then
  echo "--transit: собираю транспорт заново"
  build_r5=yes
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
ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
# на чистом сервере valhalla сначала качает карту (~700 МБ), и подготовка карты для R5
# ждёт её. Часа хватает с запасом; локально по умолчанию 15 минут
R5_SOURCE_WAIT_SECONDS=${R5_SOURCE_WAIT_SECONDS:-3600}"
for name in R5_WALKING_SPEED_KMH R5_TIMEOUT_SECONDS R5_MATRIX_MAX_POINTS \
            R5_WORKERS R5_MAX_MEMORY R5_CLIENT_CONCURRENCY R5_SKIP_WHEN_WALK_MINUTES \
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

if [ "$REBUILD_TRANSIT" = "yes" ]; then
  step "Сбрасываю данные транспорта"
  on_server DEPLOY_PATH COMPOSE_FILES PROFILES <<'REMOTE'
cd "$DEPLOY_PATH"
COMPOSE="docker compose $COMPOSE_FILES $PROFILES"
# останавливаем то, что держит тома, иначе удалить их не дадут
# shellcheck disable=SC2086
$COMPOSE rm -sf r5 r5-osm || true
# экстракт карты и собранная сеть R5 — их и пересобираем. Карту valhalla (сотни мегабайт)
# не трогаем: она качается заново часами, а для экстракта годится та же
for suffix in r5_osm r5_cache; do
  for volume in $(docker volume ls -q | grep -E "_${suffix}\$" || true); do
    docker volume rm "$volume" && echo "удалён том $volume"
  done
done
REMOTE
fi

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
if ! $COMPOSE up -d --remove-orphans; then
  # сам compose говорит только «service … didn't complete successfully» — дополняем
  # журналом упавших контейнеров, чтобы причина была в этом же логе
  echo "--- журналы упавших контейнеров ---" >&2
  # shellcheck disable=SC2086
  for c in $($COMPOSE ps -a --status exited --format '{{.Service}}' 2>/dev/null); do
    echo "--- $c ---" >&2
    $COMPOSE logs --tail 40 "$c" >&2 || true
  done
  exit 1
fi
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
on_server DEPLOY_PATH PROFILES <<'REMOTE'
cd "$DEPLOY_PATH"
# с профилем: без него compose не считает r5 и подготовку карты частью проекта
COMPOSE="docker compose -f docker-compose.yml -f deploy/compose.server.yml $PROFILES"
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
  on_server DEPLOY_PATH PROFILES <<'REMOTE'
cd "$DEPLOY_PATH"
docker compose -f docker-compose.yml -f deploy/compose.server.yml $PROFILES logs -f --tail 30
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
