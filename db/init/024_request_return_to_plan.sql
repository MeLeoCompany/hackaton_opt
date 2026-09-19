-- Вернуть отменённую заявку в утверждённый план без пересчёта.
--
-- Отменённая заявка утверждённого плана сохраняет связь с ним (request.approved_plan_id) и своё
-- место в маршруте бригады. Раньше вернуть её можно было только в «Новая» — и она оставалась
-- «Новой», но закреплённой за планом. Теперь:
--   «Отменена» -> «В плане» — оператор возвращает заявку на её место в маршруте (бэкенд
--     проверяет, что план утверждён, заявка в нём назначена и бригада не ушла дальше по маршруту);
--   «Отменена» -> «Новая» — заявка отвязывается от плана и ждёт нового расчёта.
-- Заявки, которые уже успели стать «Новыми» с привязкой к плану, чинятся: если план утверждён
-- и заявка в нём назначена бригаде — возвращаются «В план», иначе отвязываются.
BEGIN;

INSERT INTO request_status_transition (from_status_id, to_status_id, manual, description) VALUES
    (4, 2, TRUE, 'Отмена снята — заявка возвращается в утверждённый план на своё место в маршруте')
ON CONFLICT (from_status_id, to_status_id) DO NOTHING;

UPDATE request_status_transition
SET description = 'Отмена снята — заявка ждёт нового расчёта плана'
WHERE from_status_id = 4 AND to_status_id = 1;

-- «Новая», но закреплена за утверждённым планом, где у неё есть место в маршруте, — обратно «В план»
WITH returned AS (
    UPDATE request
    SET status_id = 2
    FROM plan, assignment
    WHERE request.status_id = 1
      AND plan.id = request.approved_plan_id
      AND plan.approved_at IS NOT NULL
      AND assignment.plan_id = plan.id
      AND assignment.request_id = request.id
      AND assignment.engineer_id IS NOT NULL
    RETURNING request.id, request.approved_plan_id
)
INSERT INTO request_status_history (request_id, from_status_id, to_status_id, manual, plan_id, comment)
SELECT id, 1, 2, FALSE, approved_plan_id,
       'Возвращена в утверждённый план: была «Новой», но осталась закреплённой за ним'
FROM returned;

-- остальные «Новые» с привязкой — отвязываем: места в утверждённом плане у них нет
UPDATE request SET approved_plan_id = NULL
WHERE status_id = 1 AND approved_plan_id IS NOT NULL;

COMMIT;
