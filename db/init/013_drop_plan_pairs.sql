-- Пары планов (baseline + cuOpt одним расчётом) заменены сравнением любых двух планов дня:
-- сравнение считается на лету по номерам планов, связывать их в БД больше не нужно.
BEGIN;
DROP INDEX IF EXISTS plan_comparison_idx;
ALTER TABLE plan DROP COLUMN IF EXISTS comparison_id;
COMMIT;
