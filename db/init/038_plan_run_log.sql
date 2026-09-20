-- Журнал расчётов: что именно считает система и как долго.
--
-- На большом дне расчёт идёт минутами (матрицы Valhalla и R5, cuOpt, проверка расписания),
-- и без журнала интерфейс выглядит зависшим. Каждый запуск пишет свой ход: текущий шаг,
-- процент и события по порядку. По ним рисуется прогресс и строится «Система → Журнал».
BEGIN;

CREATE TABLE IF NOT EXISTS plan_run (
    id uuid PRIMARY KEY,
    office_id bigint NOT NULL REFERENCES office(id) ON DELETE CASCADE,
    plan_date date,
    kind text NOT NULL,              -- build / replan / preview
    solver text,
    status text NOT NULL,            -- running / done / failed
    step text NOT NULL DEFAULT '',   -- что считается прямо сейчас
    progress smallint NOT NULL DEFAULT 0,  -- 0..100
    plan_id bigint REFERENCES plan(id) ON DELETE SET NULL,
    error text,
    user_id bigint REFERENCES app_user(id) ON DELETE SET NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS plan_run_event (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
    at timestamptz NOT NULL DEFAULT now(),
    level text NOT NULL DEFAULT 'info',   -- info / warning / error
    step text NOT NULL DEFAULT '',
    message text NOT NULL,
    progress smallint
);

CREATE INDEX IF NOT EXISTS plan_run_office_started_idx ON plan_run (office_id, started_at DESC);
CREATE INDEX IF NOT EXISTS plan_run_event_run_idx ON plan_run_event (run_id, id);

COMMENT ON TABLE plan_run IS 'Запуск расчёта плана: чем считали, на каком шаге и чем кончилось';
COMMENT ON TABLE plan_run_event IS 'Ход расчёта по шагам: что считалось и когда';

COMMIT;
