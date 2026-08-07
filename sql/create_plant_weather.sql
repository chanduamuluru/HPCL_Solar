-- =============================================================================
-- public.plant_weather  — time-series weather / irradiance at the plant site
--
-- Populated by the API about every 30 seconds (WEATHER_SAMPLE_SEC)
-- while the dashboard is polling /api/latest or /api/weather.
-- ts is floored to 30-second buckets so each interval gets its own row.
--
-- Run once:
--   psql $DATABASE_URL -f sql/create_plant_weather.sql
-- =============================================================================

SET search_path TO public;

CREATE TABLE IF NOT EXISTS public.plant_weather (

    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Observation time from the weather provider (prefer this over received_at)
    ts                  TIMESTAMPTZ NOT NULL,
    -- Asia/Kolkata calendar day derived from ts
    reading_date        DATE        NOT NULL,

    plant_id            INTEGER     NOT NULL DEFAULT 402,
    latitude            NUMERIC(10, 7),
    longitude           NUMERIC(10, 7),

    temperature_c       NUMERIC(5, 2),
    feels_like_c        NUMERIC(5, 2),
    humidity_pct        SMALLINT,
    precipitation_mm    NUMERIC(6, 2),
    cloud_cover_pct     SMALLINT,
    wind_speed_kmh      NUMERIC(6, 2),
    wind_direction_deg  SMALLINT,

    -- Global Horizontal Irradiance ≈ Open-Meteo shortwave_radiation (W/m²)
    ghi_wm2             NUMERIC(8, 1),

    weather_code        SMALLINT,
    condition           TEXT,
    source              TEXT        NOT NULL DEFAULT 'open-meteo',

    -- When we wrote the row into Postgres
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_plant_weather_plant_ts UNIQUE (plant_id, ts)
);

CREATE INDEX IF NOT EXISTS ix_plant_weather_ts
    ON public.plant_weather (ts DESC);

CREATE INDEX IF NOT EXISTS ix_plant_weather_date
    ON public.plant_weather (reading_date DESC, ts DESC);

CREATE INDEX IF NOT EXISTS ix_plant_weather_plant_ts
    ON public.plant_weather (plant_id, ts DESC);

COMMENT ON TABLE public.plant_weather IS
    'Site weather snapshots (Open-Meteo). ghi_wm2 is sun radiance for power correlation.';

COMMENT ON COLUMN public.plant_weather.ghi_wm2 IS
    'Global Horizontal Irradiance in W/m² (Open-Meteo shortwave_radiation).';

COMMENT ON COLUMN public.plant_weather.ts IS
    'Provider observation timestamp (Asia/Kolkata-aware timestamptz).';
