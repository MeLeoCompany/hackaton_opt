-- Системное время для демонстрации: его можно перемотать вперёд, чтобы показать работу плана
-- «с текущего момента» без ожидания. Храним сдвиг в базе: он один на весь сервер и переживает
-- перезапуск. Пустая таблица означала бы нулевой сдвиг, поэтому строка заводится сразу.
BEGIN;

CREATE TABLE IF NOT EXISTS system_time (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    offset_seconds bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by bigint REFERENCES app_user (id) ON DELETE SET NULL
);

INSERT INTO system_time (id, offset_seconds) VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE system_time IS 'Сдвиг системного времени в секундах: 0 — настоящее время';

COMMIT;
