-- Статус «В пути» — бригада выехала, но ещё не на месте.
--
-- Раньше «В работе» значило и «едет», и «работает». Теперь это два статуса:
--   6 В пути   — выехала на заявку (отметка «Выехали» в мобильном приложении);
--   5 В работе — на месте, работает (отметка «На месте»).
-- Ведут себя одинаково: заявка уже занята бригадой, в пересчёт плана она не идёт
-- (plannable = FALSE) и при пересчёте остаётся за своей бригадой.
BEGIN;

INSERT INTO request_status (id, code, name, plannable) VALUES
    (6, 'en_route', 'В пути', FALSE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO request_status_transition (from_status_id, to_status_id, manual, description) VALUES
    (2, 6, TRUE, 'Бригада выехала на заявку — в пересчёт она больше не идёт'),
    (6, 5, TRUE, 'Бригада на месте — идут работы'),
    (6, 3, TRUE, 'Работы выполнены'),
    (6, 4, TRUE, 'Заявка отменена, когда бригада была в пути')
ON CONFLICT (from_status_id, to_status_id) DO NOTHING;

UPDATE request_status_transition
SET description = 'Бригада на месте — идут работы'
WHERE from_status_id = 2 AND to_status_id = 5;

COMMIT;
