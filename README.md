# hackaton_opt

Сервис планирования маршрутов выездных инженеров: PostgreSQL + FastAPI + Vue/Leaflet,
self-hosted Valhalla для дорожной сети и R5 для общественного транспорта.

```
docker compose --profile transit up
```

| Сервис | Порт | Что это |
|---|---|---|
| `frontend` | 5173 | Карта: кликаете точки — получаете маршрут |
| `backend` | 8000 | API, `GET /api/v1/health/db` для проверки |
| `postgres` | 5432 | БД |
| `valhalla` | 8002 | Маршрутизация по данным OpenStreetMap |
| `r5` | 8003 | Общественный транспорт по OSM и локальному GTFS |

**Первый запуск долгий:** Valhalla скачивает экстракт OSM по ЦФО (~877 МБ), после чего
R5 вырезает Москву и область и строит транспортный граф. Дальнейшие старты используют
данные из Docker volumes.

- Схема БД, миграции (накат — `db/apply_migrations.sh`) и допущения при наполнении —
  [db/README.md](db/README.md).
- Структура бэкенда, расчёт расстояний и замеренные особенности — [backend/README.md](backend/README.md).
- Фронтенд — [frontend/README.md](frontend/README.md).
- Пилотный сборщик GTFS и сервис R5 (автобус + метро) —
  [transit/README.md](transit/README.md).
