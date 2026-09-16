-- Общий пробег плана сохраняется при расчёте: список планов показывает его в строке плана,
-- не пересчитывая маршруты каждого плана через маршрутизатор.
BEGIN;
ALTER TABLE plan ADD COLUMN IF NOT EXISTS total_distance_km NUMERIC(10, 3);
COMMENT ON COLUMN plan.total_distance_km IS 'Общий пробег плана по дорогам (Valhalla /route), км';
COMMIT;
