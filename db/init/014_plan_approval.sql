-- Утверждение плана дня.
--
-- Заявка с окном через полночь (23:00–02:00) попадает в дни по обе стороны полуночи, и планы
-- обоих дней вправе её взять — тогда её выполнят дважды. Поэтому диспетчер утверждает один
-- план на день, и его заявки закрепляются за этим планом: в планы других дней они больше
-- не попадают.
--
-- plan.approved_at — когда план утверждён; NULL — черновик. На день может быть утверждён
-- только один план: частичный уникальный индекс не даст утвердить второй.
-- request.approved_plan_id — за каким утверждённым планом закреплена заявка. Удалили план —
-- ссылка снимается сама (ON DELETE SET NULL), и заявка снова доступна любому дню.
BEGIN;

ALTER TABLE plan ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
COMMENT ON COLUMN plan.approved_at IS 'Когда план утверждён диспетчером; NULL — черновик';

CREATE UNIQUE INDEX IF NOT EXISTS plan_approved_day_idx
    ON plan (plan_date)
    WHERE approved_at IS NOT NULL;

ALTER TABLE request
    ADD COLUMN IF NOT EXISTS approved_plan_id BIGINT REFERENCES plan (id) ON DELETE SET NULL;
COMMENT ON COLUMN request.approved_plan_id IS
    'Заявка закреплена за утверждённым планом и в планы других дней не попадает';

CREATE INDEX IF NOT EXISTS request_approved_plan_idx ON request (approved_plan_id);

COMMIT;
