-- Параметры расчёта, которые оператор меняет без перезапуска сервиса.
--
-- У cuOpt настраивается только время поиска: чем больше лимит, тем лучше маршруты —
-- это и есть «точность». Остальное — вес пробега в целевой функции, число попыток
-- сверки плана ОТ с расписанием и подробный лог решателя.
-- Значения по умолчанию совпадают с прежними настройками из окружения (core/config.py).
BEGIN;

CREATE TABLE IF NOT EXISTS solver_settings (
    id smallint PRIMARY KEY DEFAULT 1,
    time_limit_seconds numeric(7, 2) NOT NULL DEFAULT 1.0,
    seconds_per_location numeric(6, 3) NOT NULL DEFAULT 0.2,
    max_time_limit_seconds numeric(7, 2) NOT NULL DEFAULT 120.0,
    free_locations smallint NOT NULL DEFAULT 20,
    distance_weight numeric(7, 3) NOT NULL DEFAULT 1.0,
    transit_attempts smallint NOT NULL DEFAULT 4,
    verbose_log boolean NOT NULL DEFAULT FALSE,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by bigint REFERENCES app_user (id) ON DELETE SET NULL,
    CONSTRAINT solver_settings_single_row CHECK (id = 1),
    CONSTRAINT solver_settings_limits CHECK (max_time_limit_seconds >= time_limit_seconds)
);

INSERT INTO solver_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE solver_settings IS 'Параметры расчёта: время поиска cuOpt, вес пробега, попытки сверки ОТ';
COMMENT ON COLUMN solver_settings.time_limit_seconds IS 'Минимум времени поиска решения, секунд';
COMMENT ON COLUMN solver_settings.seconds_per_location IS 'Сколько секунд добавлять за точку сверх бесплатных';
COMMENT ON COLUMN solver_settings.free_locations IS 'До скольких точек лимит не растёт';
COMMENT ON COLUMN solver_settings.distance_weight IS 'Вес пробега в целевой функции: 0 отключает выбор по пробегу';
COMMENT ON COLUMN solver_settings.transit_attempts IS 'Сколько раз пересчитывать план ОТ по фактическому расписанию';
COMMENT ON COLUMN solver_settings.verbose_log IS 'Подробный лог решателя в журнале расчёта';

COMMIT;
