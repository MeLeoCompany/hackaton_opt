-- Режим демонстрации: разрешает переводить системное время и синхронизировать маршруты
-- с планом. Без него часы идут по-настоящему, а отладочные действия закрыты — чтобы в обычной
-- работе нельзя было случайно сдвинуть время или переписать отметки бригад.
BEGIN;

ALTER TABLE system_time
    ADD COLUMN IF NOT EXISTS demo_mode boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS demo_mode_changed_at timestamptz,
    ADD COLUMN IF NOT EXISTS demo_mode_changed_by bigint REFERENCES app_user (id) ON DELETE SET NULL;

-- часы уже перемотаны — значит, демонстрация идёт: иначе время застряло бы сдвинутым
UPDATE system_time SET demo_mode = TRUE WHERE offset_seconds <> 0;

COMMENT ON COLUMN system_time.demo_mode IS 'Режим демонстрации: можно переводить время и синхронизировать маршруты с планом';

COMMIT;
