-- 047: короткие подписи источников в журнале расчёта.
-- В колонку источника помещается восемь знаков, а «ortools_solver» обрезался на полуслове.
-- Новые строки пишутся уже коротко (run_log.log_source), старые журналы подписываем так же.

UPDATE plan_run_event SET source = 'or-tools' WHERE source = 'ortools_solver';
UPDATE plan_run_event SET source = 'базовый' WHERE source = 'baseline_solver';
UPDATE plan_run_event SET source = 'кеш' WHERE source = 'travel_cache';
UPDATE plan_run_event SET source = 'planner'
WHERE source IN ('planner_loader', 'planning_service', 'replan_service', 'window_suggestions');
