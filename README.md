# hackaton_opt

Сервис планирования маршрутов выездных инженеров: PostgreSQL + FastAPI + Vue/Leaflet
поверх self-hosted маршрутизатора Valhalla.

```
docker compose up
```

| Сервис | Порт | Что это |
|---|---|---|
| `frontend` | 5173 | Карта: кликаете точки — получаете маршрут |
| `backend` | 8000 | API, `GET /api/v1/health/db` для проверки |
| `postgres` | 5432 | БД |
| `valhalla` | 8002 | Маршрутизация по данным OpenStreetMap |

**Первый запуск долгий:** Valhalla скачивает экстракт OSM по ЦФО (~877 МБ) и собирает
тайлы. Дальнейшие старты мгновенные — тайлы лежат в томе и переиспользуются.

- Схема БД, миграции (накат — `db/apply_migrations.sh`) и допущения при наполнении —
  [db/README.md](db/README.md).
- Структура бэкенда, расчёт расстояний и замеренные особенности — [backend/README.md](backend/README.md).
- Фронтенд — [frontend/README.md](frontend/README.md).

