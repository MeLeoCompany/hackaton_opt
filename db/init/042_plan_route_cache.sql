-- Готовые маршруты плана: линия для карты, участки и пробег каждой бригады.
--
-- Маршрут строит маршрутизатор (Valhalla, а для общественного транспорта — R5 по каждому
-- плечу), и на большом дне это минуты. Раньше это делалось при каждом открытии плана;
-- теперь маршруты строятся один раз при расчёте и лежат здесь. fingerprint — отпечаток того,
-- по чему маршрут строился (транспорт, точки, время отправлений): не совпал — строим заново.
BEGIN;

CREATE TABLE IF NOT EXISTS plan_route (
    plan_id bigint NOT NULL REFERENCES plan (id) ON DELETE CASCADE,
    engineer_id bigint NOT NULL REFERENCES engineer (id) ON DELETE CASCADE,
    fingerprint text NOT NULL,
    travel jsonb NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, engineer_id)
);

COMMENT ON TABLE plan_route IS 'Построенные маршруты плана: чтобы не строить их при каждом открытии';
COMMENT ON COLUMN plan_route.fingerprint IS 'По чему строился маршрут: транспорт, точки, время отправлений';

COMMIT;
