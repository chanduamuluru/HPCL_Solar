#!/usr/bin/env python3
"""
Loader for inverter_data_derived + inverter_daily_stats.

Reads raw regs from public.inverter_data and:

    backfill        decode every row -> inverter_data_derived
    sync            decode recent rows only
    aggregate       upsert one row per inverter per day -> inverter_daily_stats
    verify          sanity checks

    python -m scripts.load_derived backfill
    python -m scripts.load_derived backfill --and-aggregate
    python -m scripts.load_derived sync --since 1h --and-aggregate
    python -m scripts.load_derived watch --interval 15 --since 2h --and-aggregate
    python -m scripts.load_derived repair-ts
    python -m scripts.load_derived aggregate --date 2026-08-02
    python -m scripts.load_derived verify

Prerequisites
-------------
    psql $DATABASE_URL -f sql/recreate_derived_tables.sql

The GENERATED ALWAYS AS ... STORED columns must NOT appear in any INSERT.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python scripts/load_derived.py` / `python -m scripts.load_derived` from repo root
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
for _p in (_BACKEND, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import DEFAULT_RATED_DC_W, DSN, RATED_DC_W, SITE_TZ

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("load_derived")

BATCH_SIZE = 5000


# ---------------------------------------------------------------------------
# Register mapping — index IS the Modbus register number
# ---------------------------------------------------------------------------

REGISTER_ORDER: tuple[str, ...] = (
    "status_raw",              # 0
    "fault_word_1_raw",        # 1
    "fault_word_2_raw",        # 2
    "fault_word_3_raw",        # 3
    "fault_word_4_raw",        # 4
    "fault_word_5_raw",        # 5
    "pv1_voltage_raw",         # 6   x10 V
    "pv1_current_raw",         # 7   x100 A
    "pv2_voltage_raw",         # 8   x10 V
    "pv2_current_raw",         # 9   x100 A
    "pv1_power_raw",           # 10  /10 W
    "pv2_power_raw",           # 11  /10 W
    "ac_power_raw",            # 12  /10 W
    "reactive_power_raw",      # 13  /10 var, SIGNED
    "grid_frequency_raw",      # 14  x100 Hz
    "ac_r_voltage_raw",        # 15  x10 V
    "ac_r_current_raw",        # 16  x100 A
    "ac_y_voltage_raw",        # 17  x10 V
    "ac_y_current_raw",        # 18  x100 A
    "ac_b_voltage_raw",        # 19  x10 V
    "ac_b_current_raw",        # 20  x100 A
    "total_energy_high_raw",   # 21
    "total_energy_low_raw",    # 22
    "total_runtime_high_raw",  # 23
    "total_runtime_low_raw",   # 24
    "today_energy_raw",        # 25  x100 kWh
    "today_grid_minutes_raw",  # 26
    "heatsink_temp_raw",       # 27
    "internal_temp_raw",       # 28
    "dc_bus_voltage_raw",      # 29  x10 V
    "pv1_voltage_filt_raw",    # 30  x10 V
    "pv2_voltage_filt_raw",    # 31  x10 V
    "grid_countdown_raw",      # 32
    "reg33",                   # 33
    "reg34",                   # 34
    "reg35",                   # 35
)
assert len(REGISTER_ORDER) == 36

META_COLUMNS: tuple[str, ...] = (
    "reading_id",
    "ts",
    "inverter_id",
    "reading_date",
    "rated_dc_w",
    "received_at",
)

INSERT_COLUMNS: tuple[str, ...] = META_COLUMNS + REGISTER_ORDER


def rated_dc_w(inverter_id: int) -> int:
    return RATED_DC_W.get(inverter_id, DEFAULT_RATED_DC_W)


def reading_date(ts: datetime):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(SITE_TZ).date()


def build_row(
    reading_id,
    ts,
    inverter_id: int,
    regs: list[int],
    received_at: datetime | None = None,
) -> tuple:
    """Build an insert tuple. ``ts`` / ``received_at`` are copied verbatim from inverter_data."""
    if len(regs) != 36:
        raise ValueError(f"expected 36 registers, got {len(regs)}")
    for i, v in enumerate(regs):
        if not 0 <= v <= 65535:
            raise ValueError(f"register {i} out of range: {v}")
    return (
        reading_id,
        ts,  # exact device timestamp from inverter_data.ts
        inverter_id,
        reading_date(ts),
        rated_dc_w(inverter_id),
        received_at if received_at is not None else datetime.now(timezone.utc),
        *regs,
    )


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

INSERT_SQL = sql.SQL(
    """
    INSERT INTO public.inverter_data_derived ({cols})
    VALUES ({vals})
    ON CONFLICT (reading_id) DO UPDATE SET
        ts = EXCLUDED.ts,
        reading_date = EXCLUDED.reading_date,
        received_at = COALESCE(EXCLUDED.received_at, public.inverter_data_derived.received_at)
    """
).format(
    cols=sql.SQL(", ").join(sql.Identifier(c) for c in INSERT_COLUMNS),
    vals=sql.SQL(", ").join(sql.Placeholder() * len(INSERT_COLUMNS)),
)

# One UPSERT per inverter per day. Grid figures filtered to status_code = 2.
AGGREGATE_SQL = """
INSERT INTO public.inverter_daily_stats (
    inverter_id,
    reading_date,
    rated_dc_w,
    first_ts,
    last_ts,
    first_total_energy_kwh,
    last_total_energy_kwh,
    first_total_runtime_h,
    last_total_runtime_h,
    max_ac_power_w,
    max_dc_power_w,
    max_today_energy_kwh,
    max_grid_minutes,
    min_pv1_voltage_v,
    max_pv1_voltage_v,
    min_pv1_current_a,
    max_pv1_current_a,
    max_pv1_power_w,
    min_pv2_voltage_v,
    max_pv2_voltage_v,
    min_pv2_current_a,
    max_pv2_current_a,
    max_pv2_power_w,
    string_voltage_match_pct,
    min_heatsink_temp_c,
    max_heatsink_temp_c,
    max_internal_temp_c,
    min_grid_frequency_hz,
    max_grid_frequency_hz,
    min_phase_voltage_v,
    max_phase_voltage_v,
    max_dc_bus_voltage_v,
    min_efficiency_pct,
    max_efficiency_pct,
    sample_count,
    fault_sample_count,
    overvoltage_count,
    updated_at
)
SELECT
    inverter_id,
    reading_date,
    max(rated_dc_w)                                                   AS rated_dc_w,
    min(ts)                                                           AS first_ts,
    max(ts)                                                           AS last_ts,
    (array_agg(total_energy_kwh ORDER BY ts))[1]                      AS first_total_energy_kwh,
    (array_agg(total_energy_kwh ORDER BY ts DESC))[1]                 AS last_total_energy_kwh,
    (array_agg(total_runtime_h  ORDER BY ts))[1]                      AS first_total_runtime_h,
    (array_agg(total_runtime_h  ORDER BY ts DESC))[1]                 AS last_total_runtime_h,
    max(ac_power_w)                                                   AS max_ac_power_w,
    max(dc_power_w)                                                   AS max_dc_power_w,
    max(today_energy_kwh)                                             AS max_today_energy_kwh,
    max(today_grid_minutes)                                           AS max_grid_minutes,
    min(pv1_voltage_v)                                                AS min_pv1_voltage_v,
    max(pv1_voltage_v)                                                AS max_pv1_voltage_v,
    min(pv1_current_a)                                                AS min_pv1_current_a,
    max(pv1_current_a)                                                AS max_pv1_current_a,
    max(pv1_power_w)                                                  AS max_pv1_power_w,
    min(pv2_voltage_v)                                                AS min_pv2_voltage_v,
    max(pv2_voltage_v)                                                AS max_pv2_voltage_v,
    min(pv2_current_a)                                                AS min_pv2_current_a,
    max(pv2_current_a)                                                AS max_pv2_current_a,
    max(pv2_power_w)                                                  AS max_pv2_power_w,
    round(
        100.0 * count(*) FILTER (WHERE strings_voltage_matched)
        / NULLIF(count(*), 0), 2
    )                                                                 AS string_voltage_match_pct,
    min(heatsink_temp_c)                                              AS min_heatsink_temp_c,
    max(heatsink_temp_c)                                              AS max_heatsink_temp_c,
    max(internal_temp_c)                                              AS max_internal_temp_c,
    min(grid_frequency_hz)   FILTER (WHERE status_code = 2)           AS min_grid_frequency_hz,
    max(grid_frequency_hz)   FILTER (WHERE status_code = 2)           AS max_grid_frequency_hz,
    min(LEAST(ac_r_voltage_v, ac_y_voltage_v, ac_b_voltage_v))
                             FILTER (WHERE status_code = 2)           AS min_phase_voltage_v,
    max(max_phase_voltage_v) FILTER (WHERE status_code = 2)           AS max_phase_voltage_v,
    max(dc_bus_voltage_v)    FILTER (WHERE status_code = 2)           AS max_dc_bus_voltage_v,
    min(efficiency_pct)                                               AS min_efficiency_pct,
    max(efficiency_pct)                                               AS max_efficiency_pct,
    count(*)::INTEGER                                                 AS sample_count,
    count(*) FILTER (WHERE has_fault)::INTEGER                        AS fault_sample_count,
    count(*) FILTER (WHERE is_overvoltage)::INTEGER                   AS overvoltage_count,
    now()                                                             AS updated_at
FROM public.inverter_data_derived
WHERE (%(day)s::DATE IS NULL OR reading_date = %(day)s::DATE)
GROUP BY inverter_id, reading_date
ON CONFLICT (inverter_id, reading_date) DO UPDATE SET
    rated_dc_w               = EXCLUDED.rated_dc_w,
    first_ts                 = EXCLUDED.first_ts,
    last_ts                  = EXCLUDED.last_ts,
    first_total_energy_kwh   = EXCLUDED.first_total_energy_kwh,
    last_total_energy_kwh    = EXCLUDED.last_total_energy_kwh,
    first_total_runtime_h    = EXCLUDED.first_total_runtime_h,
    last_total_runtime_h     = EXCLUDED.last_total_runtime_h,
    max_ac_power_w           = EXCLUDED.max_ac_power_w,
    max_dc_power_w           = EXCLUDED.max_dc_power_w,
    max_today_energy_kwh     = EXCLUDED.max_today_energy_kwh,
    max_grid_minutes         = EXCLUDED.max_grid_minutes,
    min_pv1_voltage_v        = EXCLUDED.min_pv1_voltage_v,
    max_pv1_voltage_v        = EXCLUDED.max_pv1_voltage_v,
    min_pv1_current_a        = EXCLUDED.min_pv1_current_a,
    max_pv1_current_a        = EXCLUDED.max_pv1_current_a,
    max_pv1_power_w          = EXCLUDED.max_pv1_power_w,
    min_pv2_voltage_v        = EXCLUDED.min_pv2_voltage_v,
    max_pv2_voltage_v        = EXCLUDED.max_pv2_voltage_v,
    min_pv2_current_a        = EXCLUDED.min_pv2_current_a,
    max_pv2_current_a        = EXCLUDED.max_pv2_current_a,
    max_pv2_power_w          = EXCLUDED.max_pv2_power_w,
    string_voltage_match_pct = EXCLUDED.string_voltage_match_pct,
    min_heatsink_temp_c      = EXCLUDED.min_heatsink_temp_c,
    max_heatsink_temp_c      = EXCLUDED.max_heatsink_temp_c,
    max_internal_temp_c      = EXCLUDED.max_internal_temp_c,
    min_grid_frequency_hz    = EXCLUDED.min_grid_frequency_hz,
    max_grid_frequency_hz    = EXCLUDED.max_grid_frequency_hz,
    min_phase_voltage_v      = EXCLUDED.min_phase_voltage_v,
    max_phase_voltage_v      = EXCLUDED.max_phase_voltage_v,
    max_dc_bus_voltage_v     = EXCLUDED.max_dc_bus_voltage_v,
    min_efficiency_pct       = EXCLUDED.min_efficiency_pct,
    max_efficiency_pct       = EXCLUDED.max_efficiency_pct,
    sample_count             = EXCLUDED.sample_count,
    fault_sample_count       = EXCLUDED.fault_sample_count,
    overvoltage_count        = EXCLUDED.overvoltage_count,
    updated_at               = EXCLUDED.updated_at
"""


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def load_from_inverter_data(dsn: str, since: timedelta | None = None) -> int:
    """
    Decode rows from inverter_data into inverter_data_derived.

    Copies ``ts`` and ``received_at`` exactly from inverter_data.
    Sync window uses received_at (ingest time) so delayed batches are not missed
    when device ``ts`` is older than the watch window.
    Only rows missing from derived (or with mismatched ts) are selected.
    """
    params: dict = {}
    time_filter = ""
    if since is not None:
        # Prefer received_at: collector may insert older ts values in a later batch.
        time_filter = """
          AND (
            d.received_at >= %(cutoff)s
            OR d.ts >= %(cutoff)s
          )
        """
        params["cutoff"] = datetime.now(timezone.utc) - since

    select = f"""
        SELECT d.reading_id, d.ts, d.inverter_id, d.regs, d.received_at
        FROM public.inverter_data d
        LEFT JOIN public.inverter_data_derived x ON x.reading_id = d.reading_id
        WHERE jsonb_array_length(d.regs) = 36
          AND (
            x.reading_id IS NULL
            OR x.ts IS DISTINCT FROM d.ts
            OR x.received_at IS DISTINCT FROM d.received_at
          )
          {time_filter}
        ORDER BY d.id
    """

    inserted = skipped = 0
    batch: list[tuple] = []

    with psycopg.connect(dsn) as read_conn, psycopg.connect(dsn) as write_conn:
        read_conn.read_only = True

        with read_conn.cursor(name="src_cursor", row_factory=dict_row) as src, \
             write_conn.cursor() as dst:
            src.itersize = BATCH_SIZE
            src.execute(select, params)

            for row in src:
                regs = row["regs"]
                if isinstance(regs, str):
                    regs = json.loads(regs)
                try:
                    batch.append(build_row(
                        row["reading_id"],
                        row["ts"],
                        row["inverter_id"],
                        regs,
                        row.get("received_at"),
                    ))
                except ValueError as e:
                    skipped += 1
                    log.warning("skipping %s: %s", row["reading_id"], e)
                    continue

                if len(batch) >= BATCH_SIZE:
                    dst.executemany(INSERT_SQL, batch)
                    write_conn.commit()
                    inserted += len(batch)
                    log.info("upserted %d rows so far", inserted)
                    batch.clear()

            if batch:
                dst.executemany(INSERT_SQL, batch)
                write_conn.commit()
                inserted += len(batch)

        read_conn.rollback()

    log.info(
        "load complete: %d new/updated rows, %d malformed skipped",
        inserted,
        skipped,
    )
    return inserted


def repair_timestamps(dsn: str) -> int:
    """Force derived.ts / received_at to match inverter_data for all reading_ids."""
    sql_txt = """
        UPDATE public.inverter_data_derived AS d
        SET
            ts = r.ts,
            reading_date = (r.ts AT TIME ZONE 'Asia/Kolkata')::date,
            received_at = r.received_at
        FROM public.inverter_data AS r
        WHERE d.reading_id = r.reading_id
          AND (
            d.ts IS DISTINCT FROM r.ts
            OR d.received_at IS DISTINCT FROM r.received_at
          )
    """
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql_txt)
        n = cur.rowcount
        conn.commit()
    log.info("repaired ts/received_at on %d derived rows", n)
    return n


def insert_reading(conn, reading_id: str, ts: datetime,
                   inverter_id: int, regs: list[int],
                   received_at: datetime | None = None) -> bool:
    row = build_row(reading_id, ts, inverter_id, regs, received_at)
    with conn.cursor() as cur:
        cur.execute(INSERT_SQL, row)
        return cur.rowcount == 1


def refresh_aggregates(conn, day=None) -> int:
    """Upsert inverter_daily_stats. Pass a date to limit the work."""
    with conn.cursor() as cur:
        cur.execute(AGGREGATE_SQL, {"day": day})
        n = cur.rowcount
    conn.commit()
    log.info("daily_stats upserted: %d rows (%s)", n, day or "all dates")
    return n


def verify(conn) -> None:
    checks = [
        ("power_factor above 1 (impossible)",
         "SELECT count(*) FROM public.inverter_data_derived WHERE power_factor > 1.0001"),
        ("countdown not NULL while Normal",
         "SELECT count(*) FROM public.inverter_data_derived "
         "WHERE status_code = 2 AND grid_countdown_s IS NOT NULL"),
        ("negative total energy",
         "SELECT count(*) FROM public.inverter_data_derived WHERE total_energy_kwh < 0"),
        ("daily_stats > 3 rows for any day",
         "SELECT count(*) FROM ("
         "  SELECT reading_date FROM public.inverter_daily_stats "
         "  GROUP BY reading_date HAVING count(*) > 3"
         ") t"),
    ]
    with conn.cursor() as cur:
        for label, q in checks:
            cur.execute(q)
            n = cur.fetchone()[0]
            log.info("%-42s %s", label, "OK" if n == 0 else f"*** {n} ROWS ***")

        cur.execute(
            "SELECT count(*), min(reactive_power_var) "
            "FROM public.inverter_data_derived WHERE reactive_power_var < 0"
        )
        n, mn = cur.fetchone()
        log.info("%-42s %s rows, min %s var", "negative reactive power (expected)", n, mn)

        cur.execute(
            "SELECT inverter_id, count(*), max(total_energy_kwh), "
            "       round(avg(efficiency_pct), 1) "
            "FROM public.inverter_data_derived "
            "GROUP BY inverter_id ORDER BY inverter_id"
        )
        for inv, cnt, energy, eff in cur.fetchall():
            log.info("derived  inv %s: %s rows, lifetime %s kWh, avg η %s%%",
                     inv, cnt, energy, eff)

        cur.execute(
            "SELECT reading_date, inverter_id, sample_count, max_today_energy_kwh, "
            "       max_ac_power_w, string_voltage_match_pct "
            "FROM public.inverter_daily_stats "
            "ORDER BY reading_date, inverter_id"
        )
        for day, inv, n, today, peak, match in cur.fetchall():
            log.info(
                "daily    %s inv %s: %s samples, today=%s kWh, peak=%s W, "
                "string_match=%s%%",
                day, inv, n, today, peak, match,
            )


def parse_since(text: str) -> timedelta:
    unit = text[-1].lower()
    value = int(text[:-1])
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    if unit == "m":
        return timedelta(minutes=value)
    raise argparse.ArgumentTypeError("use e.g. 30m, 6h, 2d")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "command",
        choices=["backfill", "sync", "aggregate", "verify", "live-demo", "watch", "repair-ts"],
    )
    p.add_argument("--since", type=parse_since, default=None,
                   help="for sync/watch: how far back (received_at or ts), e.g. 30m, 2h")
    p.add_argument("--date", default=None,
                   help="for aggregate: a single YYYY-MM-DD, default all")
    p.add_argument("--and-aggregate", action="store_true",
                   help="refresh inverter_daily_stats after loading")
    p.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="for watch: seconds between sync cycles (default 15)",
    )
    p.add_argument("--dsn", default=DSN)
    args = p.parse_args()

    if args.command == "backfill":
        load_from_inverter_data(args.dsn)
        if args.and_aggregate:
            with psycopg.connect(args.dsn) as conn:
                refresh_aggregates(conn)
        return 0

    if args.command == "sync":
        load_from_inverter_data(args.dsn, since=args.since or timedelta(hours=2))
        if args.and_aggregate:
            with psycopg.connect(args.dsn) as conn:
                refresh_aggregates(conn, day=datetime.now(SITE_TZ).date())
        return 0

    if args.command == "repair-ts":
        repair_timestamps(args.dsn)
        return 0

    if args.command == "watch":
        since = args.since or timedelta(hours=2)
        interval = max(2.0, float(args.interval))
        log.info(
            "watching: sync every %.0fs (since=%s via received_at|ts, aggregate=%s) — Ctrl+C to stop",
            interval,
            since,
            args.and_aggregate,
        )
        while True:
            try:
                load_from_inverter_data(args.dsn, since=since)
                if args.and_aggregate:
                    with psycopg.connect(args.dsn) as conn:
                        refresh_aggregates(conn, day=datetime.now(SITE_TZ).date())
            except KeyboardInterrupt:
                log.info("watch stopped")
                return 0
            except Exception:
                log.exception("watch cycle failed; retrying in %.0fs", interval)
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                log.info("watch stopped")
                return 0

    with psycopg.connect(args.dsn) as conn:
        if args.command == "aggregate":
            refresh_aggregates(conn, day=args.date)

        elif args.command == "verify":
            verify(conn)

        elif args.command == "live-demo":
            regs = [2, 0, 0, 0, 0, 0, 5761, 1933, 6391, 719, 1114, 462, 1530,
                    11, 5004, 2435, 2104, 2422, 2098, 2425, 2097, 1, 9340, 0,
                    13361, 3039, 311, 55, 53, 6590, 5743, 6372, 60, 0, 1, 0]
            ok = insert_reading(
                conn, "INV-3-DEMO-0001",
                datetime(2026, 8, 2, 5, 38, 28, tzinfo=timezone.utc), 3, regs,
            )
            conn.commit()
            log.info("inserted: %s", ok)
            refresh_aggregates(conn, day="2026-08-02")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT status_text, ac_power_w, dc_power_w, efficiency_pct, "
                    "       power_factor, total_energy_kwh, today_energy_kwh, "
                    "       voltage_imbalance_pct, dc_bus_headroom_v, "
                    "       strings_voltage_matched "
                    "FROM public.inverter_data_derived WHERE reading_id = %s",
                    ("INV-3-DEMO-0001",),
                )
                for k, v in (cur.fetchone() or {}).items():
                    log.info("   %-24s %s", k, v)

    return 0


if __name__ == "__main__":
    sys.exit(main())
