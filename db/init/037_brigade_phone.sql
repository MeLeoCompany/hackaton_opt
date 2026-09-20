-- Телефон бригады: оператор звонит прямо из системы, когда бригада выбилась из плана
-- (docs/algoV2.md, шаги 8-10).
BEGIN;

ALTER TABLE brigade ADD COLUMN IF NOT EXISTS phone text;

COMMENT ON COLUMN brigade.phone IS 'Телефон бригады для звонка оператора';

COMMIT;
