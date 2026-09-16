-- Сравнение базового алгоритма с cuOpt убрано: планы считает только cuOpt,
-- связывать пары планов больше нечем.
BEGIN;
DROP INDEX IF EXISTS plan_comparison_idx;
ALTER TABLE plan DROP COLUMN IF EXISTS comparison_id;
COMMIT;
