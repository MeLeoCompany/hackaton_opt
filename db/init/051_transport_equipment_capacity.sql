-- 051: сколько оборудования бригада физически может увезти и какой запас брать сверх плана.
--
-- Запас бригады (engineer_equipment) до сих пор заводили руками. Теперь его считает система:
-- по первому плану дня видно, сколько штук нужно бригаде на её заявки (x0), и выдаём
-- items = min(ёмкость транспорта, x0 + запас). Ёмкость зависит и от транспорта, и от вещи:
-- в машину влезет тридцать роутеров, пешеход столько не унесёт.
--
-- Запас (delta) один на всю систему и лежит рядом с параметрами расчёта: диспетчер меняет
-- его в «Система» → «Состояние».
BEGIN;

CREATE TABLE IF NOT EXISTS transport_equipment_capacity (
    transport_id SMALLINT NOT NULL REFERENCES transport (id) ON DELETE CASCADE,
    equipment_id BIGINT   NOT NULL REFERENCES equipment (id) ON DELETE CASCADE,
    max_quantity INTEGER  NOT NULL CHECK (max_quantity >= 0),
    PRIMARY KEY (transport_id, equipment_id)
);
COMMENT ON TABLE transport_equipment_capacity IS 'Сколько штук оборудования увозит бригада на этом транспорте';
COMMENT ON COLUMN transport_equipment_capacity.max_quantity IS 'Предел выдачи; 0 — этим транспортом не возят';

-- начальные пределы: машина везёт много, пешеход — сколько в руках, велосипед и
-- общественный транспорт между ними. Правятся в «Справочники» → «Оборудование»
INSERT INTO transport_equipment_capacity (transport_id, equipment_id, max_quantity) VALUES
    (1, 1, 30), (1, 2, 20),   -- автомобиль
    (2, 1, 5),  (2, 2, 2),    -- пешеход
    (3, 1, 8),  (3, 2, 3),    -- велосипед
    (4, 1, 6),  (4, 2, 3)     -- общественный транспорт
ON CONFLICT (transport_id, equipment_id) DO NOTHING;

ALTER TABLE solver_settings ADD COLUMN IF NOT EXISTS equipment_reserve SMALLINT NOT NULL DEFAULT 2
    CHECK (equipment_reserve >= 0);
COMMENT ON COLUMN solver_settings.equipment_reserve IS 'Запас штук сверх потребности плана при выдаче оборудования';

COMMIT;
