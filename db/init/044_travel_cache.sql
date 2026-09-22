-- Кеш времени в пути R5 (docs/algoCachV1.md).
--
-- R5 — самая долгая часть расчёта: матрица по расписанию и проверка каждого плеча маршрута
-- идут минутами, а пробный пересчёт, пересчёт, подбор окон при утверждении и маршруты для
-- карты раньше каждый раз спрашивали у R5 одно и то же. Ответ R5 зависит только от точек и
-- времени выезда, поэтому хранится здесь и собирается обратно.
--
-- Расписание считаем одинаковым каждый день: ключ — время суток выезда (секунды от полуночи
-- по Москве), без даты. Два вида записей:
--   matrix — пара матрицы (/matrix, /matrix-block): оценка с окном отправления, для cuOpt;
--   route  — одна поездка (/route) с участками и линией: для проверки расписания и карты.
-- Матрица берёт только matrix, проверка — только route: числа в расчёте такие же, как без кеша.
--
-- Записи старше 7 дней удаляются раз в сутки; при смене расписания GTFS — все
-- (travel_cache_state хранит отпечаток файла расписания).
BEGIN;

CREATE TABLE IF NOT EXISTS travel_cache (
    kind text NOT NULL CHECK (kind IN ('matrix', 'route')),
    from_lat numeric(10, 6) NOT NULL,
    from_lon numeric(10, 6) NOT NULL,
    to_lat numeric(10, 6) NOT NULL,
    to_lon numeric(10, 6) NOT NULL,
    depart_seconds integer NOT NULL CHECK (depart_seconds BETWEEN 0 AND 86399),
    -- matrix: минуты R5 после досчёта изолированных точек; NULL — R5 пути не нашёл
    duration_min double precision,
    -- route: ответ R5 по плечу целиком (участки, линия, пересадки)
    route jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, depart_seconds, from_lat, from_lon, to_lat, to_lon)
);

CREATE INDEX IF NOT EXISTS travel_cache_created_idx ON travel_cache (created_at);

CREATE TABLE IF NOT EXISTS travel_cache_state (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    -- по какому файлу расписания посчитан кеш: сменился — кеш очищается целиком
    gtfs_fingerprint text,
    cleaned_at timestamptz
);

INSERT INTO travel_cache_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE travel_cache IS 'Ответы R5: пары матрицы и плечи маршрутов по времени суток выезда';
COMMENT ON TABLE travel_cache_state IS 'Отпечаток расписания GTFS, по которому посчитан кеш R5';

COMMIT;
