-- Статусы заявок и допустимые переходы между ними — основа пересчёта плана.
--
-- Сценарий: план утверждён, приходит новая заявка; оператор отмечает выполненные заявки,
-- а заявки, на которые бригады уже едут, фиксируются; пересчёт строится по тому, что
-- осталось, плюс новая заявка. Для этого флаг «активна» заменяется статусом.
--
-- request_status — справочник статусов. plannable — попадает ли заявка в расчёт плана
-- (раньше это был is_active). Номера фиксированы: на них ссылается код бэкенда.
--   1 Новая     — ждёт планирования;
--   2 В плане   — закреплена за утверждённым планом (request.approved_plan_id);
--   3 Выполнена — отмечена оператором, в планирование больше не идёт;
--   4 Отменена  — в планирование не идёт (сюда переходят бывшие «выключенные» заявки).
--
-- request_status_transition — какие переходы допустимы. manual = TRUE — переход делает
-- оператор руками («В плане» -> «Выполнена»); FALSE — система сама («Новая» -> «В плане»
-- при утверждении плана). Переход, которого нет в таблице, запрещён.
BEGIN;

CREATE TABLE IF NOT EXISTS request_status (
    id        SMALLINT PRIMARY KEY,
    code      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL UNIQUE,
    plannable BOOLEAN NOT NULL
);
COMMENT ON TABLE request_status IS 'Статусы заявок';
COMMENT ON COLUMN request_status.plannable IS 'Заявка в этом статусе попадает в расчёт плана';

INSERT INTO request_status (id, code, name, plannable) VALUES
    (1, 'new',       'Новая',     TRUE),
    (2, 'planned',   'В плане',   TRUE),
    (3, 'done',      'Выполнена', FALSE),
    (4, 'cancelled', 'Отменена',  FALSE)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS request_status_transition (
    from_status_id SMALLINT NOT NULL REFERENCES request_status (id),
    to_status_id   SMALLINT NOT NULL REFERENCES request_status (id),
    manual         BOOLEAN NOT NULL,
    description    TEXT NOT NULL,
    PRIMARY KEY (from_status_id, to_status_id),
    CHECK (from_status_id <> to_status_id)
);
COMMENT ON TABLE request_status_transition IS 'Допустимые переходы статусов заявки';
COMMENT ON COLUMN request_status_transition.manual IS
    'TRUE — переход делает оператор, FALSE — система (утверждение плана и т. п.)';

INSERT INTO request_status_transition (from_status_id, to_status_id, manual, description) VALUES
    (1, 2, FALSE, 'План утверждён — заявка закреплена за ним'),
    (2, 1, FALSE, 'Утверждение плана снято — заявка снова ждёт планирования'),
    (2, 3, TRUE,  'Оператор отметил выполнение'),
    (1, 4, TRUE,  'Заявка отменена до планирования'),
    (2, 4, TRUE,  'Заявка отменена после утверждения плана'),
    (4, 1, TRUE,  'Отмена снята — заявка снова ждёт планирования')
ON CONFLICT (from_status_id, to_status_id) DO NOTHING;

-- статус заявки вместо флага «активна»; переносим один раз, пока флаг ещё есть
ALTER TABLE request ADD COLUMN IF NOT EXISTS status_id SMALLINT REFERENCES request_status (id);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'request' AND column_name = 'is_active'
    ) THEN
        UPDATE request
        SET status_id = CASE
            WHEN NOT is_active THEN 4
            WHEN approved_plan_id IS NOT NULL THEN 2
            ELSE 1
        END
        WHERE status_id IS NULL;
        ALTER TABLE request DROP COLUMN is_active;
    END IF;
END
$$;
UPDATE request SET status_id = 1 WHERE status_id IS NULL;
ALTER TABLE request ALTER COLUMN status_id SET DEFAULT 1;
ALTER TABLE request ALTER COLUMN status_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS request_status_idx ON request (status_id);
COMMENT ON COLUMN request.status_id IS 'Статус заявки (request_status)';

COMMIT;
