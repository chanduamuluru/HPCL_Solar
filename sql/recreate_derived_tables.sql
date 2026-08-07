-- =============================================================================
-- Recreate derived + daily_stats tables (keeps inverter_data intact)
--
-- From project root:
--   psql %DATABASE_URL% -f sql/recreate_derived_tables.sql
--   python -m scripts.load_derived backfill --and-aggregate
--
-- \ir paths are relative to this file's directory (sql/).
-- =============================================================================

SET search_path TO public;

DROP TABLE IF EXISTS public.inverter_daily_stats CASCADE;
DROP TABLE IF EXISTS public.inverter_data_derived CASCADE;

\ir create_inverter_data_derived.sql
\ir create_inverter_daily_stats.sql
