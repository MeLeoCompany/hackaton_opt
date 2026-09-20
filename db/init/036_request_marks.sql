-- Отметки заявки для синхронизации плана с фактом (docs/algoV2.md).
--
-- «Согласовано» — оператор созвонился с клиентом и назвал время: окно сужено до обещанного,
-- в расчёте заявка идёт ярусом ниже аварий и выше всех остальных.
-- «Перенесена» — работу двигали на другой день: в расчётах она идёт выше неперенесённых
-- своего приоритета, чтобы не кочевать изо дня в день.
-- «Требует уточнения» — отменили, потому что не дозвонились: оператор вернётся к ней позже.
-- «Выезд разрешён» — бригада отстаёт, но оператор договорился с клиентом и отпустил её.
BEGIN;

ALTER TABLE request
    ADD COLUMN IF NOT EXISTS promised_from timestamptz,
    ADD COLUMN IF NOT EXISTS promised_to timestamptz,
    ADD COLUMN IF NOT EXISTS moved_from date,
    ADD COLUMN IF NOT EXISTS needs_followup boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancel_reason text,
    ADD COLUMN IF NOT EXISTS departure_allowed_at timestamptz;

COMMENT ON COLUMN request.promised_from IS 'Начало обещанного клиенту окна (согласовано по телефону)';
COMMENT ON COLUMN request.promised_to IS 'Конец обещанного окна: раньше него бригада должна начать работу';
COMMENT ON COLUMN request.moved_from IS 'День, с которого заявку перенесли';
COMMENT ON COLUMN request.needs_followup IS 'Отменена, потому что не дозвонились: нужно перезвонить';
COMMENT ON COLUMN request.cancel_reason IS 'Почему отменили: причина оператора или бригады';
COMMENT ON COLUMN request.departure_allowed_at IS 'Оператор разрешил выезд, хотя бригада отстаёт';

COMMIT;
