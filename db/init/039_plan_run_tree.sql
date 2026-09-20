-- Журнал расчёта: дерево событий, источники и прерывание расчёта.
--
-- События складываются в дерево: шаг — узел, а внутри него подробности этого шага
-- (блоки матриц, попытки решателя, строки cuOpt и внешних служб). У узла есть время
-- окончания и длительность, поэтому видно, где расчёт стоял дольше всего.
-- cancel_requested — оператор нажал «Прервать»: расчёт проверяет флаг между шагами
-- и останавливается сам (жёстко прервать cuOpt на видеокарте нельзя).
BEGIN;

ALTER TABLE plan_run
    ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;

ALTER TABLE plan_run_event
    ADD COLUMN IF NOT EXISTS parent_id bigint REFERENCES plan_run_event(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'planner',
    ADD COLUMN IF NOT EXISTS finished_at timestamptz,
    ADD COLUMN IF NOT EXISTS duration_ms integer,
    ADD COLUMN IF NOT EXISTS details jsonb;

CREATE INDEX IF NOT EXISTS plan_run_event_parent_idx ON plan_run_event (parent_id);

COMMENT ON COLUMN plan_run.cancel_requested IS 'Оператор попросил прервать расчёт';
COMMENT ON COLUMN plan_run_event.parent_id IS 'Шаг, внутри которого произошло событие';
COMMENT ON COLUMN plan_run_event.source IS 'Кто написал: planner, cuopt, r5, valhalla, operator';
COMMENT ON COLUMN plan_run_event.duration_ms IS 'Сколько занял шаг, миллисекунд';

COMMIT;
