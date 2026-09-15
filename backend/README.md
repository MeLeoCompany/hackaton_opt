# backend

FastAPI-сервис поверх БД планирования маршрутов.

## Структура (`src/`)

```
api/         — HTTP-слой: роутеры и эндпоинты (FastAPI), по одному пакету на фичу
models/      — ORM-модели (SQLAlchemy), зеркалируют схему из db/init/001_schema.sql
schemas/     — Pydantic-модели запросов/ответов для будущих доменных эндпоинтов
services/    — бизнес-логика для будущих доменных эндпоинтов
repositories/— доступ к данным для будущих доменных эндпоинтов
db/          — engine/session/Base
core/        — конфигурация (настройки из переменных окружения)
```

`api/v1/endpoints/health/` — самодостаточный пример фичи (роутер + схемы + сервис +
репозиторий в одной папке), сквозной проверкой прохождения запроса через все слои:
`GET /api/v1/health/` (liveness) и `GET /api/v1/health/db` (доступность БД).
Будущие доменные эндпоинты (заявки, инженеры, планы) будут использовать общие
`models/`, `schemas/`, `services/`, `repositories/` — эти папки сейчас пустые.

## Локальная разработка (без Docker, с дебагом в VS Code)

Postgres всё равно нужен — поднимите его отдельно: `docker compose up -d postgres`
(порт 5432 проброшен на localhost).

```
cd backend
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # DATABASE_URL для локального запуска
```

Дальше — через VS Code: F5 → "Backend: FastAPI (debug)" (`.vscode/launch.json`,
интерпретатор `backend/.venv` уже прописан в `.vscode/settings.json`). Есть и вариант
"Backend: FastAPI (reload, no debug)" — с `--reload`, но без надёжной отладки в
дочернем процессе релоадера.

Без VS Code — просто `./.venv/bin/uvicorn src.main:app --reload` из `backend/`
(переменные подтянутся из `.env`).

## В связке с БД

Из корня репозитория: `docker compose up` — поднимет `postgres` и `backend`
(порт 8000, автоперезагрузка при изменении `backend/src`).
