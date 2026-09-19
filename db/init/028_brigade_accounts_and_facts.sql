-- Бригады сами отмечают, что происходит на маршруте: выехали, на месте, выполнено, не выполнить.
--
-- Учётка бригады (роль brigade) входит в мобильное приложение и видит свой маршрут дня из
-- утверждённого плана. Строка engineer — это смена одного дня, поэтому учётка привязана не к
-- строке, а к бригаде: офис + название бригады (engineer.name). Маршрут дня — визиты
-- утверждённого плана офиса у смены с этим названием.
--
-- request_fact — что бригада отметила по заявке: когда выехала, прибыла и закончила.
-- Статус заявки меняется тем же переходом, что и у оператора, и пишется в историю;
-- здесь — время факта: по нему видно отставание от плана и строится пересчёт.
BEGIN;

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS brigade_name TEXT;
COMMENT ON COLUMN app_user.brigade_name IS 'Учётка бригады: название бригады (engineer.name) в офисе учётки';

ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;
ALTER TABLE app_user ADD CONSTRAINT app_user_role_check
    CHECK (role IN ('admin', 'dispatcher', 'brigade'));

ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_brigade_check;
ALTER TABLE app_user ADD CONSTRAINT app_user_brigade_check
    CHECK ((role = 'brigade') = (brigade_name IS NOT NULL));

CREATE TABLE IF NOT EXISTS request_fact (
    request_id  BIGINT PRIMARY KEY REFERENCES request (id) ON DELETE CASCADE,
    engineer_id BIGINT REFERENCES engineer (id) ON DELETE SET NULL,
    departed_at TIMESTAMPTZ,
    arrived_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE request_fact IS 'Отметки бригады по заявке: когда выехала, прибыла и закончила';
COMMENT ON COLUMN request_fact.finished_at IS 'Закончила: выполнила или отметила, что выполнить нельзя';

COMMIT;
