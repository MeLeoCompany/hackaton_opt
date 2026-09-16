-- Типы работ с нормативами времени (таблица нормативов из ТЗ).
--
-- Технические работы и оформление документов сложены в одну колонку work_minutes: на месте
-- это одна непрерывная работа, и планировщику важна только её длительность.
-- Дорога до клиента/ТКД хранится отдельно (travel_minutes) — это норматив из ТЗ; в плане
-- дорога считается по Valhalla между конкретными адресами, норматив нужен для оценки
-- и как справочная величина.
-- baseline_minutes — «базовый норматив» из ТЗ, сумма дороги и работы на месте.
BEGIN;

CREATE TABLE IF NOT EXISTS work_type (
    id               SMALLINT PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    skill_id         SMALLINT NOT NULL REFERENCES skill (id),
    travel_minutes   INTEGER NOT NULL CHECK (travel_minutes >= 0),
    work_minutes     INTEGER NOT NULL CHECK (work_minutes > 0),
    baseline_minutes INTEGER GENERATED ALWAYS AS (travel_minutes + work_minutes) STORED
);

COMMENT ON COLUMN work_type.travel_minutes IS 'Норматив дороги до клиента/ТКД, мин';
COMMENT ON COLUMN work_type.work_minutes IS 'Работа на месте: технические работы + документы, мин';
COMMENT ON COLUMN work_type.baseline_minutes IS 'Базовый норматив ТЗ: дорога + работа на месте, мин';

INSERT INTO work_type (id, name, skill_id, travel_minutes, work_minutes) VALUES
    (1, 'Подключение клиентов, базовая', 2, 20, 70),
    (2, 'Авария на ТКД', 3, 20, 80),
    (3, 'Дозаказ оборудования', 2, 20, 20),
    (4, 'Локальная заявка / ремонт у клиента', 1, 20, 30)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE request ADD COLUMN IF NOT EXISTS work_type_id SMALLINT REFERENCES work_type (id);
CREATE INDEX IF NOT EXISTS request_work_type_id_idx ON request (work_type_id);

-- У существующих заявок типа работ не было: проставляем по требуемому навыку.
-- Длительность заявок не трогаем — она могла быть задана вручную и отличаться от норматива.
UPDATE request SET work_type_id = CASE skill_id
    WHEN 1 THEN 4
    WHEN 2 THEN 1
    WHEN 3 THEN 2
END WHERE work_type_id IS NULL;

COMMIT;
