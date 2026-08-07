-- =============================================================================
-- public.inverter_daily_stats  — one row per inverter per local day
--
-- With 3 inverters this means exactly 3 rows per calendar day.
-- UNIQUE (inverter_id, reading_date) enforces that.
--
-- Populate via:  python load_derived.py aggregate [--date YYYY-MM-DD]
-- Also create site weather history:
--   psql $DATABASE_URL -f sql/create_plant_weather.sql
-- =============================================================================

SET search_path TO public;

CREATE TABLE IF NOT EXISTS public.inverter_daily_stats (

    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inverter_id     INTEGER NOT NULL,
    reading_date    DATE    NOT NULL,          -- Asia/Kolkata calendar day
    rated_dc_w      INTEGER NOT NULL DEFAULT 15000,

    -- Time span of samples used for this day
    first_ts        TIMESTAMPTZ,
    last_ts         TIMESTAMPTZ,

    -- Lifetime counter bookends → day energy / runtime from counters
    first_total_energy_kwh  BIGINT,
    last_total_energy_kwh   BIGINT,
    first_total_runtime_h   BIGINT,
    last_total_runtime_h    BIGINT,

    -- Peaks
    max_ac_power_w          INTEGER,
    max_dc_power_w          INTEGER,
    max_today_energy_kwh    NUMERIC(8,2),
    max_grid_minutes        INTEGER,

    -- ---------- string (MPPT) envelopes --------------------------------
    min_pv1_voltage_v       NUMERIC(7,1),
    max_pv1_voltage_v       NUMERIC(7,1),
    min_pv1_current_a       NUMERIC(7,2),
    max_pv1_current_a       NUMERIC(7,2),
    max_pv1_power_w         INTEGER,

    min_pv2_voltage_v       NUMERIC(7,1),
    max_pv2_voltage_v       NUMERIC(7,1),
    min_pv2_current_a       NUMERIC(7,2),
    max_pv2_current_a       NUMERIC(7,2),
    max_pv2_power_w         INTEGER,

    -- Share of samples where |pv1_v - pv2_v| < 2 V (inv1 anomaly signal)
    string_voltage_match_pct NUMERIC(6,2),

    -- ---------- thermal ------------------------------------------------
    min_heatsink_temp_c     SMALLINT,
    max_heatsink_temp_c     SMALLINT,
    max_internal_temp_c     SMALLINT,

    -- ---------- grid envelope (status = Normal only) -------------------
    min_grid_frequency_hz   NUMERIC(5,2),
    max_grid_frequency_hz   NUMERIC(5,2),
    min_phase_voltage_v     NUMERIC(6,1),
    max_phase_voltage_v     NUMERIC(6,1),
    max_dc_bus_voltage_v    NUMERIC(7,1),

    -- ---------- efficiency (above 20% load frames only) ----------------
    min_efficiency_pct      NUMERIC(6,2),
    max_efficiency_pct      NUMERIC(6,2),

    -- ---------- counts -------------------------------------------------
    sample_count            INTEGER NOT NULL DEFAULT 0,
    fault_sample_count      INTEGER NOT NULL DEFAULT 0,
    overvoltage_count       INTEGER NOT NULL DEFAULT 0,

    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),


    -- =================================================================
    --  GENERATED — from the aggregates above
    -- =================================================================

    day_energy_from_counter_kwh BIGINT GENERATED ALWAYS AS (
        last_total_energy_kwh - first_total_energy_kwh
    ) STORED,

    day_runtime_from_counter_h BIGINT GENERATED ALWAYS AS (
        last_total_runtime_h - first_total_runtime_h
    ) STORED,

    -- Disagreement between counter delta and today_energy register.
    energy_source_delta_kwh NUMERIC(8,2) GENERATED ALWAYS AS (
        (last_total_energy_kwh - first_total_energy_kwh)
        - max_today_energy_kwh
    ) STORED,

    heatsink_span_c SMALLINT GENERATED ALWAYS AS (
        max_heatsink_temp_c - min_heatsink_temp_c
    ) STORED,

    frequency_span_hz NUMERIC(5,2) GENERATED ALWAYS AS (
        max_grid_frequency_hz - min_grid_frequency_hz
    ) STORED,

    phase_voltage_span_v NUMERIC(6,1) GENERATED ALWAYS AS (
        max_phase_voltage_v - min_phase_voltage_v
    ) STORED,

    efficiency_span_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        max_efficiency_pct - min_efficiency_pct
    ) STORED,

    -- Fair cross-inverter comparison: kWh per kW rated DC
    specific_yield_kwh_per_kw NUMERIC(8,3) GENERATED ALWAYS AS (
        max_today_energy_kwh * 1000.0 / NULLIF(rated_dc_w, 0)
    ) STORED,

    fault_rate_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        fault_sample_count * 100.0 / NULLIF(sample_count, 0)
    ) STORED,

    overvoltage_rate_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        overvoltage_count * 100.0 / NULLIF(sample_count, 0)
    ) STORED,

    CONSTRAINT ids_unique_day UNIQUE (inverter_id, reading_date),
    CONSTRAINT ids_rated_positive CHECK (rated_dc_w > 0),
    CONSTRAINT ids_sample_nonneg CHECK (sample_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_ids_reading_date
    ON public.inverter_daily_stats (reading_date DESC);

CREATE INDEX IF NOT EXISTS ix_ids_inverter_date
    ON public.inverter_daily_stats (inverter_id, reading_date DESC);

COMMENT ON TABLE public.inverter_daily_stats IS
    'One row per inverter per Asia/Kolkata day (3 rows/day for the HPCL fleet). String + power/grid/thermal min/max envelopes.';
