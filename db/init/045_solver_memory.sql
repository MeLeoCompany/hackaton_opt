-- Память решений cuOpt: одинаковая задача — одинаковый ответ (docs/algoCachV1.md).
--
-- cuOpt ищет на видеокарте параллельно и ограничен только временем: на один и тот же вход
-- он каждый раз находит немного другое решение того же качества (замер: 5 разных решений из 5
-- и при 3, и при 30 секундах). Поэтому решение запоминается по отпечатку всего входа — матрицы,
-- окна, награды, бригады, цель и лимит времени. Такой же вход — берём то же решение без поиска.
-- Изменился вход или лимит — ищем заново. Записи старше 7 дней удаляются вместе с кешем R5.
BEGIN;

CREATE TABLE IF NOT EXISTS solver_memory (
    input_hash text PRIMARY KEY,
    -- таблица маршрутов cuOpt строками: truck_id, route, arrival_stamp, location, type
    route_records jsonb NOT NULL,
    objective double precision,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS solver_memory_created_idx ON solver_memory (created_at);

COMMENT ON TABLE solver_memory IS 'Решения cuOpt по отпечатку входа: одинаковая задача — одинаковый ответ';

COMMIT;
