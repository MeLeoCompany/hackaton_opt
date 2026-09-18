-- Синхронизация дня с временем: до какого момента статусы заявок дня приведены к плану.
--
-- Оператор жмёт «Синхронизировать»: заявки утверждённого плана, работы по которым к этому
-- времени по плану закончились, становятся «Выполнена», те, к которым бригада уже выехала, —
-- «В работе»; «Новые» заявки вне плана с прошедшим окном — «Отменена». Время синхронизации
-- запоминается на день и офис: назад его не откатывают (статусы уже сменились), следующая
-- синхронизация — только на то же время или позже. Каждая смена статуса — в истории заявки.
BEGIN;

CREATE TABLE IF NOT EXISTS day_sync (
    office_id BIGINT NOT NULL REFERENCES office (id) ON DELETE CASCADE,
    plan_date DATE NOT NULL,
    synced_to TIMESTAMPTZ NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id   BIGINT REFERENCES app_user (id) ON DELETE SET NULL,
    PRIMARY KEY (office_id, plan_date)
);
COMMENT ON TABLE day_sync IS 'До какого времени статусы заявок дня офиса синхронизированы с планом';
COMMENT ON COLUMN day_sync.synced_to IS 'Время, на которое синхронизировали (может быть задано вручную)';
COMMENT ON COLUMN day_sync.synced_at IS 'Когда синхронизацию выполнили';

COMMIT;
