-- 046: пересчёт вступает в силу сам, в тот момент, на который посчитан (docs/algoV2.md, шаг 6).
-- Если к этому моменту появились новые вводные — заявка, отмена, выбившаяся бригада, чужой
-- выезд, — он в силу не вступает: помечается недействительным с причиной, бригады продолжают
-- ехать по прежнему плану, а оператор считает заново.

ALTER TABLE plan ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS void_reason TEXT;

COMMENT ON COLUMN plan.voided_at IS 'Пересчёт не вступил в силу: момент, когда это выяснилось';
COMMENT ON COLUMN plan.void_reason IS 'Почему пересчёт не вступил в силу — текст для оператора';
