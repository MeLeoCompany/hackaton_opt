-- 048: когда запись о расчёте появилась в базе, по настоящим часам.
-- started_at — время системных часов, а их в режиме демонстрации переводят: расчёт,
-- запущенный только что, по нему может оказаться «раньше» вчерашнего. Журнал же должен
-- показывать расчёты в том порядке, в каком их запускали, поэтому порядок — по recorded_at.

ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ NOT NULL DEFAULT now();

COMMENT ON COLUMN plan_run.recorded_at IS 'Когда запись появилась в базе (настоящее время): порядок журнала';

CREATE INDEX IF NOT EXISTS plan_run_recorded_at_idx ON plan_run (office_id, recorded_at DESC);
