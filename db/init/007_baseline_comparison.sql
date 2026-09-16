BEGIN;
-- Для старых записей порядок поступления неизвестен: фиксируем порядок ID.
ALTER TABLE request ADD COLUMN IF NOT EXISTS input_order BIGINT;
WITH ordered AS (SELECT id, row_number() OVER (ORDER BY id) AS position FROM request)
UPDATE request t SET input_order = ordered.position FROM ordered
WHERE t.id = ordered.id AND t.input_order IS NULL;
CREATE SEQUENCE IF NOT EXISTS request_input_order_seq OWNED BY request.input_order;
SELECT setval('request_input_order_seq', GREATEST(
 COALESCE((SELECT MAX(input_order) FROM request), 0) + 1,
 (SELECT last_value FROM request_input_order_seq)), false);
ALTER TABLE request ALTER COLUMN input_order SET DEFAULT nextval('request_input_order_seq');
ALTER TABLE request ALTER COLUMN input_order SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS request_input_order_idx ON request(input_order);

-- Для старых записей порядок поступления неизвестен: фиксируем порядок ID.
ALTER TABLE engineer ADD COLUMN IF NOT EXISTS input_order BIGINT;
WITH ordered AS (SELECT id, row_number() OVER (ORDER BY id) AS position FROM engineer)
UPDATE engineer t SET input_order = ordered.position FROM ordered
WHERE t.id = ordered.id AND t.input_order IS NULL;
CREATE SEQUENCE IF NOT EXISTS engineer_input_order_seq OWNED BY engineer.input_order;
SELECT setval('engineer_input_order_seq', GREATEST(
 COALESCE((SELECT MAX(input_order) FROM engineer), 0) + 1,
 (SELECT last_value FROM engineer_input_order_seq)), false);
ALTER TABLE engineer ALTER COLUMN input_order SET DEFAULT nextval('engineer_input_order_seq');
ALTER TABLE engineer ALTER COLUMN input_order SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS engineer_input_order_idx ON engineer(input_order);

ALTER TABLE plan ADD COLUMN IF NOT EXISTS comparison_id UUID;
CREATE INDEX IF NOT EXISTS plan_comparison_idx ON plan(comparison_id);
COMMIT;
