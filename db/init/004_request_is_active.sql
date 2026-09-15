-- Активна ли заявка. Выключенная заявка хранится как есть, но не попадает в сборку задачи
-- планирования — диспетчер включает и выключает заявки, не удаляя их. По умолчанию активна.
--
-- IF NOT EXISTS — чтобы файл можно было накатить и на уже поднятую БД:
--   docker exec -i routing_db psql -U routing -d routing < db/init/004_request_is_active.sql
ALTER TABLE request ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN request.is_active IS
    'Учитывать заявку при планировании; выключенные заявки хранятся, но в модель не попадают';
