-- Отметка о том, что при первом старте контейнера выполнились все файлы db/init.
--
-- Postgres прогоняет docker-entrypoint-initdb.d целиком, когда том пустой: в такой базе уже
-- есть всё, что лежало в каталоге на тот момент. Журнал миграций (schema_migration) об этом
-- не знал, и db/apply_migrations.sh потом пытался накатить старые файлы заново — на базе,
-- где давно есть более поздние изменения. Так ломалось, например, 009: оно вставляет типы
-- работ без priority_id, а этот столбец стал обязательным в 032.
--
-- Файл идёт последним по имени, поэтому выполняется после остальных и записывает их все.
-- db/apply_migrations.sh сам его не выполняет (он в списке BOOTSTRAP_FILES): иначе на живой
-- базе он отметил бы применёнными миграции, которых там ещё нет.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migration (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE schema_migration IS 'Какие файлы db/init уже накачены (db/apply_migrations.sh)';

INSERT INTO schema_migration (filename)
SELECT name
FROM pg_ls_dir('/docker-entrypoint-initdb.d') AS name
WHERE name LIKE '%.sql'
ON CONFLICT DO NOTHING;

COMMIT;
