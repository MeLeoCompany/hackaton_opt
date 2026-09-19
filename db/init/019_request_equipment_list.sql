-- Несколько видов оборудования на заявку.
--
-- Раньше заявка требовала не больше одного типа оборудования (request.equipment_id).
-- На деле техник везёт, например, и роутер, и ТВ-приставку, поэтому требование стало
-- списком: таблица request_equipment. Существующие требования переносятся в неё,
-- а колонка request.equipment_id удаляется.
--
-- Удалить заявку — её требования удаляются вместе с ней. Удалить тип оборудования,
-- который требуют заявки, по-прежнему нельзя (внешний ключ без каскада).
BEGIN;

CREATE TABLE IF NOT EXISTS request_equipment (
    request_id   BIGINT NOT NULL REFERENCES request (id) ON DELETE CASCADE,
    equipment_id BIGINT NOT NULL REFERENCES equipment (id),
    PRIMARY KEY (request_id, equipment_id)
);
COMMENT ON TABLE request_equipment IS 'Какое оборудование нужно привезти на заявку';
CREATE INDEX IF NOT EXISTS request_equipment_equipment_idx ON request_equipment (equipment_id);

-- перенос одиночных требований; повторный запуск колонку уже не найдёт и ничего не сделает
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'request' AND column_name = 'equipment_id'
    ) THEN
        INSERT INTO request_equipment (request_id, equipment_id)
        SELECT id, equipment_id FROM request WHERE equipment_id IS NOT NULL
        ON CONFLICT DO NOTHING;
        ALTER TABLE request DROP COLUMN equipment_id;
    END IF;
END
$$;

COMMIT;
