# Единственный контейнер, смотрящий наружу: отдаёт собранные интерфейсы и проксирует API.
# Контекст сборки — корень репозитория: внутрь нужны оба фронтенда сразу.
FROM node:22-alpine AS build
WORKDIR /src

# зависимости ставятся по package-lock, чтобы сборка на сервере совпадала с локальной
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY frontend frontend
RUN cd frontend && npm run build

COPY mobile/package.json mobile/package-lock.json mobile/
RUN cd mobile && npm ci
COPY mobile mobile
# приложение бригады живёт по /mobile/: адреса его файлов должны это учитывать
RUN cd mobile && VITE_BASE=/mobile/ npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache wget
COPY --from=build /src/frontend/dist /usr/share/nginx/html
COPY --from=build /src/mobile/dist /usr/share/nginx/html/mobile
COPY deploy/nginx/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
