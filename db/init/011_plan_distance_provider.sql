-- Источник сохранённого пробега: Valhalla, приближённый haversine fallback или mixed.
-- У старых планов источник неизвестен и остаётся NULL.
BEGIN;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS distance_provider TEXT;
COMMENT ON COLUMN plan.distance_provider IS
    'Источник total_distance_km: valhalla, haversine или mixed; NULL у старых планов';
COMMIT;
