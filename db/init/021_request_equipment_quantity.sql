-- Количество оборудования в требовании заявки.
--
-- Заявке бывает нужно несколько штук одного типа (два роутера), поэтому у требования
-- появилось количество — так же, как у запаса бригады (engineer_equipment.quantity).
-- Существующим требованиям ставится одна штука.
BEGIN;

ALTER TABLE request_equipment
    ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0);
COMMENT ON COLUMN request_equipment.quantity IS 'Сколько штук этого оборудования нужно на заявку';

COMMIT;
