#!/bin/sh
# Конфиг nginx собирается на старте: домен подставляется, TLS включается только когда
# сертификат уже лежит на месте. Пока его нет, сайт работает по http — этого достаточно,
# чтобы Let's Encrypt проверил владение доменом и выдал сертификат.
set -eu

DOMAIN="${DOMAIN:?не задан домен}"
TLS="${TLS:-true}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
CONF="/etc/nginx/conf.d/default.conf"

# то, что отдаёт сайт: диспетчер в корне, приложение бригады в /mobile/, API на бэкенд
app_body() {
  cat <<'BODY'
    client_max_body_size 32m;

    # имя бэкенда разрешается на каждом запросе через встроенный DNS docker, а не один раз
    # при старте: иначе nginx не поднимется, пока бэкенд не запущен, и ляжет вместе с ним
    resolver 127.0.0.11 valid=10s ipv6=off;

    location /api/ {
        set $upstream "http://backend:8000";
        proxy_pass $upstream$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # расчёт плана идёт минутами: обычные 60 секунд рвут запрос на середине
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # Файлы сборки уникальны по хешу в имени — их можно кешировать надолго.
    # А вот index.html кешировать нельзя: ссылки на скрипты лежат внутри него, и браузер
    # с закешированной страницей продолжает исполнять старую сборку, не замечая обновления
    location ~* ^/(assets|mobile/assets)/ {
        root /usr/share/nginx/html;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location = /index.html {
        root /usr/share/nginx/html;
        add_header Cache-Control "no-cache";
    }

    location = /mobile/index.html {
        alias /usr/share/nginx/html/mobile/index.html;
        add_header Cache-Control "no-cache";
    }

    location /mobile/ {
        alias /usr/share/nginx/html/mobile/;
        try_files $uri $uri/ /mobile/index.html;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
BODY
}

render() {
  if [ "$TLS" = "true" ] && [ -f "${CERT_DIR}/fullchain.pem" ]; then
    # сертификат есть: http только для проверки домена и редиректа, всё остальное по https
    {
      cat <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location = /healthz { access_log off; return 200 "ok\n"; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name ${DOMAIN};

    ssl_certificate ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    location = /healthz { access_log off; return 200 "ok\n"; }
EOF
      app_body
      echo "}"
    } > "$CONF"
    echo "nginx: домен ${DOMAIN}, сертификат найден — работаем по https"
  else
    {
      cat <<EOF
server {
    listen 80 default_server;
    server_name ${DOMAIN} _;

    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location = /healthz { access_log off; return 200 "ok\n"; }
EOF
      app_body
      echo "}"
    } > "$CONF"
    if [ "$TLS" = "true" ]; then
      echo "nginx: сертификата для ${DOMAIN} пока нет — работаем по http и ждём его"
    else
      echo "nginx: TLS выключен — работаем по http"
    fi
  fi
}

render
had_cert=$([ -f "${CERT_DIR}/fullchain.pem" ] && echo yes || echo no)

# следим за сертификатом: появился после выпуска или обновился — перечитываем конфиг,
# иначе nginx продолжит отдавать старый до перезапуска контейнера
watch_cert() {
  while sleep 60; do
    now=$([ -f "${CERT_DIR}/fullchain.pem" ] && echo yes || echo no)
    if [ "$now" != "$had_cert" ]; then
      had_cert="$now"
      render
      nginx -s reload || true
    fi
  done
}

watch_cert &
exec nginx -g 'daemon off;'
