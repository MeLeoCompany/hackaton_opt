-- Оборудование, которое бригада везёт с собой: тип из справочника и количество.
--
-- engineer_equipment — сколько штук каждого типа у бригады (роутеров 3, приставок 1).
-- Удалить бригаду — её запас удаляется вместе с ней. Удалить тип оборудования, который
-- есть у бригад, нельзя (внешний ключ без каскада), как и тип, который требуют заявки.
-- Планировщик запас пока не учитывает: это справочная информация для диспетчера.
BEGIN;

CREATE TABLE IF NOT EXISTS engineer_equipment (
    engineer_id  BIGINT NOT NULL REFERENCES engineer (id) ON DELETE CASCADE,
    equipment_id BIGINT NOT NULL REFERENCES equipment (id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (engineer_id, equipment_id)
);
COMMENT ON TABLE engineer_equipment IS 'Какое оборудование и сколько везёт бригада';
CREATE INDEX IF NOT EXISTS engineer_equipment_equipment_idx ON engineer_equipment (equipment_id);

COMMIT;
