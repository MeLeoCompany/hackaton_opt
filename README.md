# hackaton_opt

Сервис планирования маршрутов выездных инженеров: PostgreSQL + FastAPI-бэкенд.

```
docker compose up
```

Поднимет БД (порт 5432) и API (порт 8000, `GET /api/v1/health/db` для проверки).

- Схема БД, миграции и допущения при наполнении — [db/README.md](db/README.md).
- Структура бэкенда — [backend/README.md](backend/README.md).

