-- Воспроизводимая политика оптимизации конкретного плана.
BEGIN;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS objective_policy JSONB;
COMMENT ON COLUMN plan.objective_policy IS
    'Строгий порядок критериев оптимизации, выбранный диспетчером при расчёте';
COMMIT;
