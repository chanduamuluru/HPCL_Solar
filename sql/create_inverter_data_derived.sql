-- =============================================================================
-- public.inverter_data_derived  — per-reading decode of regs[0..35]
--
-- Daily min/max / string envelopes live in inverter_daily_stats, NOT here.
-- Drop the old table first if migrating:
--     DROP TABLE IF EXISTS public.inverter_data_derived CASCADE;
-- =============================================================================

SET search_path TO public;

CREATE TABLE IF NOT EXISTS public.inverter_data_derived (

    -- =================================================================
    --  IDENTITY
    -- =================================================================
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reading_id    VARCHAR(128) UNIQUE,
    ts            TIMESTAMPTZ NOT NULL,
    inverter_id   INTEGER     NOT NULL,

    -- Local calendar date (Asia/Kolkata). Not generated: AT TIME ZONE is
    -- STABLE, so PostgreSQL rejects it in a generated expression.
    reading_date  DATE        NOT NULL,

    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Rated DC watts — not in the register block; carried for efficiency
    -- and load_factor. Replace with nameplate when known.
    rated_dc_w    INTEGER     NOT NULL DEFAULT 15000,


    -- =================================================================
    --  1. RAW REGISTERS  (reg 0 .. 35)
    --
    --  INTEGER, not SMALLINT. Modbus is UNSIGNED 16-bit (0..65535);
    --  PostgreSQL SMALLINT is signed and rejects values > 32767.
    -- =================================================================

    status_raw              INTEGER NOT NULL,   -- 0
    fault_word_1_raw        INTEGER NOT NULL,   -- 1
    fault_word_2_raw        INTEGER NOT NULL,   -- 2
    fault_word_3_raw        INTEGER NOT NULL,   -- 3
    fault_word_4_raw        INTEGER NOT NULL,   -- 4
    fault_word_5_raw        INTEGER NOT NULL,   -- 5
    pv1_voltage_raw         INTEGER NOT NULL,   -- 6   x10 V
    pv1_current_raw         INTEGER NOT NULL,   -- 7   x100 A
    pv2_voltage_raw         INTEGER NOT NULL,   -- 8   x10 V
    pv2_current_raw         INTEGER NOT NULL,   -- 9   x100 A
    pv1_power_raw           INTEGER NOT NULL,   -- 10  /10 W
    pv2_power_raw           INTEGER NOT NULL,   -- 11  /10 W
    ac_power_raw            INTEGER NOT NULL,   -- 12  /10 W
    reactive_power_raw      INTEGER NOT NULL,   -- 13  /10 var, SIGNED
    grid_frequency_raw      INTEGER NOT NULL,   -- 14  x100 Hz
    ac_r_voltage_raw        INTEGER NOT NULL,   -- 15  x10 V
    ac_r_current_raw        INTEGER NOT NULL,   -- 16  x100 A
    ac_y_voltage_raw        INTEGER NOT NULL,   -- 17  x10 V
    ac_y_current_raw        INTEGER NOT NULL,   -- 18  x100 A
    ac_b_voltage_raw        INTEGER NOT NULL,   -- 19  x10 V
    ac_b_current_raw        INTEGER NOT NULL,   -- 20  x100 A
    total_energy_high_raw   INTEGER NOT NULL,   -- 21
    total_energy_low_raw    INTEGER NOT NULL,   -- 22
    total_runtime_high_raw  INTEGER NOT NULL,   -- 23
    total_runtime_low_raw   INTEGER NOT NULL,   -- 24
    today_energy_raw        INTEGER NOT NULL,   -- 25  x100 kWh
    today_grid_minutes_raw  INTEGER NOT NULL,   -- 26  minutes
    heatsink_temp_raw       INTEGER NOT NULL,   -- 27  degC
    internal_temp_raw       INTEGER NOT NULL,   -- 28  degC
    dc_bus_voltage_raw      INTEGER NOT NULL,   -- 29  x10 V
    pv1_voltage_filt_raw    INTEGER NOT NULL,   -- 30  x10 V
    pv2_voltage_filt_raw    INTEGER NOT NULL,   -- 31  x10 V
    grid_countdown_raw      INTEGER NOT NULL,   -- 32  seconds
    reg33                   INTEGER NOT NULL,   -- 33  reserved (always 0)
    reg34                   INTEGER NOT NULL,   -- 34  reserved (always 1)
    reg35                   INTEGER NOT NULL,   -- 35  flag (64 on inv1)


    -- =================================================================
    --  2. DERIVED — this row's registers only
    -- =================================================================

    -- ---------- state ------------------------------------------------
    status_code SMALLINT GENERATED ALWAYS AS (status_raw) STORED,

    status_text TEXT GENERATED ALWAYS AS (
        CASE status_raw
            WHEN 0 THEN 'Standby'
            WHEN 1 THEN 'Starting'
            WHEN 2 THEN 'Normal'
            WHEN 3 THEN 'Fault'
            ELSE 'Unknown(' || status_raw || ')'
        END
    ) STORED,

    is_grid_connected BOOLEAN GENERATED ALWAYS AS (status_raw = 2) STORED,

    -- Counts DOWN while synchronising; pins at 60 once connected.
    -- NULL while Normal so charts do not plot a flat 60.
    grid_countdown_s SMALLINT GENERATED ALWAYS AS (
        CASE WHEN status_raw = 2 THEN NULL ELSE grid_countdown_raw END
    ) STORED,

    has_fault BOOLEAN GENERATED ALWAYS AS (
        status_raw = 3
        OR fault_word_1_raw <> 0 OR fault_word_2_raw <> 0
        OR fault_word_3_raw <> 0 OR fault_word_4_raw <> 0
        OR fault_word_5_raw <> 0
    ) STORED,

    -- ---------- DC input / strings -----------------------------------
    pv1_voltage_v NUMERIC(7,1) GENERATED ALWAYS AS (pv1_voltage_raw / 10.0) STORED,
    pv1_current_a NUMERIC(7,2) GENERATED ALWAYS AS (pv1_current_raw / 100.0) STORED,
    pv2_voltage_v NUMERIC(7,1) GENERATED ALWAYS AS (pv2_voltage_raw / 10.0) STORED,
    pv2_current_a NUMERIC(7,2) GENERATED ALWAYS AS (pv2_current_raw / 100.0) STORED,

    pv1_power_w INTEGER GENERATED ALWAYS AS (pv1_power_raw * 10) STORED,
    pv2_power_w INTEGER GENERATED ALWAYS AS (pv2_power_raw * 10) STORED,
    dc_power_w  INTEGER GENERATED ALWAYS AS ((pv1_power_raw + pv2_power_raw) * 10) STORED,

    dc_bus_voltage_v NUMERIC(7,1) GENERATED ALWAYS AS (dc_bus_voltage_raw / 10.0) STORED,

    dc_bus_headroom_v NUMERIC(7,1) GENERATED ALWAYS AS (
        (dc_bus_voltage_raw - GREATEST(pv1_voltage_raw, pv2_voltage_raw)) / 10.0
    ) STORED,

    pv1_voltage_filtered_v NUMERIC(7,1) GENERATED ALWAYS AS (pv1_voltage_filt_raw / 10.0) STORED,
    pv2_voltage_filtered_v NUMERIC(7,1) GENERATED ALWAYS AS (pv2_voltage_filt_raw / 10.0) STORED,

    -- V x I should equal the inverter power register (inv1 often fails this).
    pv1_power_check_w NUMERIC(10,1) GENERATED ALWAYS AS (
        (pv1_voltage_raw / 10.0) * (pv1_current_raw / 100.0)
    ) STORED,
    pv2_power_check_w NUMERIC(10,1) GENERATED ALWAYS AS (
        (pv2_voltage_raw / 10.0) * (pv2_current_raw / 100.0)
    ) STORED,

    -- True when both MPPT strings report nearly the same voltage.
    strings_voltage_matched BOOLEAN GENERATED ALWAYS AS (
        ABS(pv1_voltage_raw - pv2_voltage_raw) < 20   -- < 2.0 V
    ) STORED,

    -- ---------- AC output --------------------------------------------
    ac_power_w INTEGER GENERATED ALWAYS AS (ac_power_raw * 10) STORED,

    reactive_power_var INTEGER GENERATED ALWAYS AS (
        (CASE WHEN reactive_power_raw >= 32768
              THEN reactive_power_raw - 65536
              ELSE reactive_power_raw END) * 10
    ) STORED,

    apparent_power_va NUMERIC(10,1) GENERATED ALWAYS AS (
        sqrt(
            (ac_power_raw * 10.0) ^ 2
            + ((CASE WHEN reactive_power_raw >= 32768
                     THEN reactive_power_raw - 65536
                     ELSE reactive_power_raw END) * 10.0) ^ 2
        )
    ) STORED,

    power_factor NUMERIC(6,4) GENERATED ALWAYS AS (
        CASE WHEN ac_power_raw = 0 AND reactive_power_raw = 0 THEN NULL
        ELSE (ac_power_raw * 10.0) / sqrt(
                 (ac_power_raw * 10.0) ^ 2
                 + ((CASE WHEN reactive_power_raw >= 32768
                          THEN reactive_power_raw - 65536
                          ELSE reactive_power_raw END) * 10.0) ^ 2
             )
        END
    ) STORED,

    grid_frequency_hz NUMERIC(5,2) GENERATED ALWAYS AS (grid_frequency_raw / 100.0) STORED,

    ac_r_voltage_v NUMERIC(6,1) GENERATED ALWAYS AS (ac_r_voltage_raw / 10.0) STORED,
    ac_r_current_a NUMERIC(7,2) GENERATED ALWAYS AS (ac_r_current_raw / 100.0) STORED,
    ac_y_voltage_v NUMERIC(6,1) GENERATED ALWAYS AS (ac_y_voltage_raw / 10.0) STORED,
    ac_y_current_a NUMERIC(7,2) GENERATED ALWAYS AS (ac_y_current_raw / 100.0) STORED,
    ac_b_voltage_v NUMERIC(6,1) GENERATED ALWAYS AS (ac_b_voltage_raw / 10.0) STORED,
    ac_b_current_a NUMERIC(7,2) GENERATED ALWAYS AS (ac_b_current_raw / 100.0) STORED,

    max_phase_voltage_v NUMERIC(6,1) GENERATED ALWAYS AS (
        GREATEST(ac_r_voltage_raw, ac_y_voltage_raw, ac_b_voltage_raw) / 10.0
    ) STORED,

    voltage_imbalance_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        CASE WHEN (ac_r_voltage_raw + ac_y_voltage_raw + ac_b_voltage_raw) = 0 THEN NULL
        ELSE (GREATEST(ac_r_voltage_raw, ac_y_voltage_raw, ac_b_voltage_raw)
              - LEAST(ac_r_voltage_raw, ac_y_voltage_raw, ac_b_voltage_raw))
             * 300.0 / (ac_r_voltage_raw + ac_y_voltage_raw + ac_b_voltage_raw)
        END
    ) STORED,

    current_imbalance_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        CASE WHEN (ac_r_current_raw + ac_y_current_raw + ac_b_current_raw) = 0 THEN NULL
        ELSE (GREATEST(ac_r_current_raw, ac_y_current_raw, ac_b_current_raw)
              - LEAST(ac_r_current_raw, ac_y_current_raw, ac_b_current_raw))
             * 300.0 / (ac_r_current_raw + ac_y_current_raw + ac_b_current_raw)
        END
    ) STORED,

    is_frequency_excursion BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN status_raw = 2
             THEN (grid_frequency_raw < 4950 OR grid_frequency_raw > 5050)
             ELSE NULL END
    ) STORED,

    is_overvoltage BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN status_raw = 2
             THEN (GREATEST(ac_r_voltage_raw, ac_y_voltage_raw, ac_b_voltage_raw) > 2530)
             ELSE NULL END
    ) STORED,

    is_undervoltage BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN status_raw = 2
             THEN (LEAST(ac_r_voltage_raw, ac_y_voltage_raw, ac_b_voltage_raw) < 2070)
             ELSE NULL END
    ) STORED,

    -- ---------- energy and runtime -----------------------------------
    total_energy_kwh BIGINT GENERATED ALWAYS AS (
        total_energy_high_raw::BIGINT * 65536 + total_energy_low_raw
    ) STORED,

    total_runtime_h BIGINT GENERATED ALWAYS AS (
        total_runtime_high_raw::BIGINT * 65536 + total_runtime_low_raw
    ) STORED,

    today_energy_kwh NUMERIC(8,2) GENERATED ALWAYS AS (today_energy_raw / 100.0) STORED,

    -- Grid-connected minutes, not producing minutes. Null overnight residual.
    today_grid_minutes SMALLINT GENERATED ALWAYS AS (
        CASE WHEN today_energy_raw > 0 OR status_raw IN (1, 2)
             THEN today_grid_minutes_raw ELSE NULL END
    ) STORED,

    -- ---------- thermal ----------------------------------------------
    heatsink_temp_c SMALLINT GENERATED ALWAYS AS (heatsink_temp_raw) STORED,
    internal_temp_c SMALLINT GENERATED ALWAYS AS (internal_temp_raw) STORED,

    -- ---------- efficiency and load ----------------------------------
    -- NULL below ~20% load — 10 W granularity makes low-load η noise.
    efficiency_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        CASE WHEN (pv1_power_raw + pv2_power_raw) * 10 > rated_dc_w * 0.20
             THEN (ac_power_raw * 100.0) / NULLIF(pv1_power_raw + pv2_power_raw, 0)
             ELSE NULL END
    ) STORED,

    load_factor_pct NUMERIC(6,2) GENERATED ALWAYS AS (
        (ac_power_raw * 1000.0) / NULLIF(rated_dc_w, 0)
    ) STORED,


    -- =================================================================
    --  CONSTRAINTS
    -- =================================================================
    CONSTRAINT idd_reg_range CHECK (
        status_raw             BETWEEN 0 AND 65535 AND
        fault_word_1_raw       BETWEEN 0 AND 65535 AND
        fault_word_2_raw       BETWEEN 0 AND 65535 AND
        fault_word_3_raw       BETWEEN 0 AND 65535 AND
        fault_word_4_raw       BETWEEN 0 AND 65535 AND
        fault_word_5_raw       BETWEEN 0 AND 65535 AND
        pv1_voltage_raw        BETWEEN 0 AND 65535 AND
        pv1_current_raw        BETWEEN 0 AND 65535 AND
        pv2_voltage_raw        BETWEEN 0 AND 65535 AND
        pv2_current_raw        BETWEEN 0 AND 65535 AND
        pv1_power_raw          BETWEEN 0 AND 65535 AND
        pv2_power_raw          BETWEEN 0 AND 65535 AND
        ac_power_raw           BETWEEN 0 AND 65535 AND
        reactive_power_raw     BETWEEN 0 AND 65535 AND
        grid_frequency_raw     BETWEEN 0 AND 65535 AND
        ac_r_voltage_raw       BETWEEN 0 AND 65535 AND
        ac_r_current_raw       BETWEEN 0 AND 65535 AND
        ac_y_voltage_raw       BETWEEN 0 AND 65535 AND
        ac_y_current_raw       BETWEEN 0 AND 65535 AND
        ac_b_voltage_raw       BETWEEN 0 AND 65535 AND
        ac_b_current_raw       BETWEEN 0 AND 65535 AND
        total_energy_high_raw  BETWEEN 0 AND 65535 AND
        total_energy_low_raw   BETWEEN 0 AND 65535 AND
        total_runtime_high_raw BETWEEN 0 AND 65535 AND
        total_runtime_low_raw  BETWEEN 0 AND 65535 AND
        today_energy_raw       BETWEEN 0 AND 65535 AND
        today_grid_minutes_raw BETWEEN 0 AND 65535 AND
        heatsink_temp_raw      BETWEEN 0 AND 65535 AND
        internal_temp_raw      BETWEEN 0 AND 65535 AND
        dc_bus_voltage_raw     BETWEEN 0 AND 65535 AND
        pv1_voltage_filt_raw   BETWEEN 0 AND 65535 AND
        pv2_voltage_filt_raw   BETWEEN 0 AND 65535 AND
        grid_countdown_raw     BETWEEN 0 AND 65535 AND
        reg33                  BETWEEN 0 AND 65535 AND
        reg34                  BETWEEN 0 AND 65535 AND
        reg35                  BETWEEN 0 AND 65535
    ),
    CONSTRAINT idd_rated_positive CHECK (rated_dc_w > 0)
);

CREATE INDEX IF NOT EXISTS ix_idd_inverter_ts
    ON public.inverter_data_derived (inverter_id, ts DESC);

CREATE INDEX IF NOT EXISTS ix_idd_reading_date
    ON public.inverter_data_derived (reading_date, inverter_id);

CREATE INDEX IF NOT EXISTS ix_idd_ts
    ON public.inverter_data_derived (ts DESC);

COMMENT ON TABLE public.inverter_data_derived IS
    'Per-reading decode of inverter_data.regs. Daily envelopes are in inverter_daily_stats.';
