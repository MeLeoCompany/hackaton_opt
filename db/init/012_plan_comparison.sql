-- Связывает baseline и cuOpt, рассчитанные на одном снимке и одних матрицах.
-- На уже поднятую БД (повторный запуск безопасен):
--   docker exec -i routing_db psql -U routing -d routing < db/init/012_plan_comparison.sql
BEGIN;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS comparison_id UUID;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS solve_duration_ms NUMERIC(12, 3);
CREATE INDEX IF NOT EXISTS plan_comparison_idx ON plan(comparison_id);
COMMENT ON COLUMN plan.comparison_id IS 'Общий UUID пары baseline и оптимизированного плана';
COMMENT ON COLUMN plan.solve_duration_ms IS 'Время работы решателя без загрузки матриц и расчёта геометрии, мс';
COMMIT;
