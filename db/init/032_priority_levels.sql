-- Три уровня приоритета заявок: Авария -> Подключение -> Ремонт и дозаказ.
--
-- Приоритет распределения задаёт заказчик: авария важнее подключения, подключение важнее
-- ремонта и дозаказа. Уровень (priority.level, 1 — самый важный) читает оптимизатор: он
-- сначала берёт аварии, потом подключения, потом остальное.
--
-- Приоритет подставляется по типу работ (work_type.priority_id) и остаётся редактируемым в
-- заявке: тип работ — это «что делаем», приоритет — «насколько срочно», и у конкретной
-- заявки он может отличаться.
BEGIN;

ALTER TABLE priority ADD COLUMN IF NOT EXISTS level SMALLINT;
COMMENT ON COLUMN priority.level IS 'Уровень распределения: 1 — авария, дальше по убыванию важности';

-- прежние «Срочная» и «Обычная» становятся уровнями заказчика
UPDATE priority SET name = 'Авария', level = 1 WHERE id = 2;
UPDATE priority SET name = 'Ремонт и дозаказ', level = 3 WHERE id = 1;
INSERT INTO priority (id, name, level) VALUES (3, 'Подключение', 2)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, level = EXCLUDED.level;
UPDATE priority SET level = 3 WHERE level IS NULL;
ALTER TABLE priority ALTER COLUMN level SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS priority_level_idx ON priority (level);

-- приоритет по умолчанию у типа работ: его подставляет форма заявки и загрузка CSV
ALTER TABLE work_type ADD COLUMN IF NOT EXISTS priority_id SMALLINT REFERENCES priority (id);
COMMENT ON COLUMN work_type.priority_id IS 'Приоритет, который подставляется новой заявке этого типа';
UPDATE work_type SET priority_id = CASE
    WHEN name ILIKE '%авари%' THEN 2   -- Авария
    WHEN name ILIKE '%подключени%' THEN 3  -- Подключение
    ELSE 1                              -- Ремонт и дозаказ
END
WHERE priority_id IS NULL;
ALTER TABLE work_type ALTER COLUMN priority_id SET NOT NULL;

-- заявки, у которых приоритет остался прежним «Обычная», выравниваем по типу работ:
-- у подключений он теперь «Подключение», у остальных — «Ремонт и дозаказ».
-- Явно отмеченные «Срочная» (теперь «Авария») не трогаем
UPDATE request SET priority_id = work_type.priority_id
FROM work_type
WHERE request.work_type_id = work_type.id AND request.priority_id = 1;

COMMIT;
