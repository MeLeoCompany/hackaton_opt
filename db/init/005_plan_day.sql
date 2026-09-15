-- День, на который построен план, и каким решателем он посчитан.
-- Дата нужна, чтобы находить планы конкретного дня; решатель — чтобы отличать cuOpt
-- от будущих baseline и резервного решателя.
--
-- На уже поднятую БД (повторный запуск безопасен):
--   docker exec -i routing_db psql -U routing -d routing < db/init/005_plan_day.sql
ALTER TABLE plan ADD COLUMN IF NOT EXISTS plan_date DATE;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS solver TEXT;

-- у уже существующих планов день берём из их заявок (по московскому времени начала окна)
UPDATE plan
SET plan_date = (
    SELECT MIN((request.window_start AT TIME ZONE 'Europe/Moscow')::date)
    FROM assignment
    JOIN request ON request.id = assignment.request_id
    WHERE assignment.plan_id = plan.id
)
WHERE plan_date IS NULL;

CREATE INDEX IF NOT EXISTS plan_plan_date_idx ON plan (plan_date);

COMMENT ON COLUMN plan.plan_date IS 'День, на который построен план (по московскому времени)';
COMMENT ON COLUMN plan.solver IS 'Чем посчитан план: cuopt, baseline и т.п.';
