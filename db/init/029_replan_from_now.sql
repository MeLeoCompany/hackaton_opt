-- Пересчёт утверждённого плана с текущего момента.
--
-- Бригады уже работают по утверждённому плану, отмечают выезд и выполнение. Когда кто-то
-- выбился из графика, появились новые заявки или часть сняли, диспетчер пересчитывает
-- остаток дня: выполненные и начатые заявки остаются за своими бригадами, бригада стартует
-- оттуда, где она сейчас, остальное решатель раскладывает заново.
--
-- plan.parent_plan_id — какой утверждённый план пересчитали; plan.replanned_at — на какой
-- момент (с какого времени бригады свободны). Утверждение пересчёта заменяет родителя:
-- plan.superseded_at — когда план заменили; утверждённым на день считается только
-- незаменённый план, поэтому уникальный индекс «один утверждённый план на офис и день»
-- теперь не учитывает заменённые.
BEGIN;

ALTER TABLE plan ADD COLUMN IF NOT EXISTS parent_plan_id BIGINT REFERENCES plan (id) ON DELETE SET NULL;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS replanned_at TIMESTAMPTZ;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;
COMMENT ON COLUMN plan.parent_plan_id IS 'Пересчёт: какой утверждённый план пересчитан';
COMMENT ON COLUMN plan.replanned_at IS 'Пересчёт: на какой момент — с него бригады свободны';
COMMENT ON COLUMN plan.superseded_at IS 'Когда план заменили утверждённым пересчётом';

DROP INDEX IF EXISTS plan_approved_office_day_idx;
CREATE UNIQUE INDEX plan_approved_office_day_idx ON plan (office_id, plan_date)
    WHERE approved_at IS NOT NULL AND superseded_at IS NULL;

COMMIT;
