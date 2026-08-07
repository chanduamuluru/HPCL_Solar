"""JSON API backed by inverter_data_derived + inverter_daily_stats."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query

from app.config import (
    PLANT_ID,
    PLANT_LABEL,
    PLANT_LAT,
    PLANT_LON,
    SITE_TZ,
    STALE_AFTER_SEC,
    WEATHER_SAMPLE_SEC,
)
from app.db import as_float, connect, jsonable

router = APIRouter(prefix="/api")
log = logging.getLogger("hpcl.api")

HEAT_ALERT_C = 75
OV_LIMIT_V = 253.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(ts_iso: str | None) -> float | None:
    ts = _parse_ts(ts_iso)
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (_now_utc() - ts).total_seconds())


def _local_today() -> date:
    return datetime.now(SITE_TZ).date()


def _build_alerts(rows: list[dict[str, Any]], *, plant_stale: bool = False) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    if plant_stale:
        ages = [r.get("data_age_sec") for r in rows if r.get("data_age_sec") is not None]
        age = max(ages) if ages else None
        alerts.append({
            "level": "medium",
            "code": "no_fresh_data",
            "message": (
                f"No reading in the last {STALE_AFTER_SEC // 60} min"
                + (f" (last sample {int(age // 60)} min ago)" if age is not None else "")
                + " — showing last sample values"
            ),
        })

    # Only flag simultaneous zero when data is fresh (otherwise last sample may be old).
    if not plant_stale:
        zero_now = [
            r for r in rows
            if (r.get("ac_power_w") or 0) == 0 and r.get("status_code") == 2
            and not r.get("is_stale")
        ]
        if len(zero_now) >= 2:
            alerts.append({
                "level": "high",
                "code": "simultaneous_zero",
                "message": f"{len(zero_now)} inverters at 0 kW while Normal — possible plant-wide event",
            })

    for r in rows:
        inv = r.get("inverter_id")
        # Instantaneous grid checks only meaningful on fresh samples
        if not r.get("is_stale"):
            if r.get("is_overvoltage"):
                alerts.append({
                    "level": "high",
                    "code": "overvoltage",
                    "inverter_id": inv,
                    "message": f"Inv {inv}: phase voltage above {OV_LIMIT_V:.0f} V",
                })
            if r.get("is_frequency_excursion"):
                alerts.append({
                    "level": "high",
                    "code": "frequency",
                    "inverter_id": inv,
                    "message": f"Inv {inv}: grid frequency outside 49.5–50.5 Hz",
                })
        hs = r.get("heatsink_temp_c")
        if hs is not None and hs >= HEAT_ALERT_C and not r.get("is_stale"):
            alerts.append({
                "level": "medium",
                "code": "heatsink",
                "inverter_id": inv,
                "message": f"Inv {inv}: heatsink {hs} °C (alert ≥ {HEAT_ALERT_C})",
            })
        if inv == 1 and r.get("strings_voltage_matched"):
            alerts.append({
                "level": "medium",
                "code": "string_anomaly",
                "inverter_id": 1,
                "message": "Inv 1: PV1/PV2 voltages matched (<2 V) - string diagnostics unreliable",
            })
        if r.get("has_fault"):
            alerts.append({
                "level": "high",
                "code": "fault",
                "inverter_id": inv,
                "message": f"Inv {inv}: fault / protection active",
            })
    return alerts


def _zero_instantaneous(row: dict[str, Any]) -> None:
    """
    Keep last_* copies of the latest sample.

    Instantaneous fields are left as the last sample values for display so
    cards stay consistent with the live chart; is_stale tells the UI the feed
    is not fresh. Only clear grid-excursion flags (those need a live sample).
    """
    for src, dst in (
        ("ac_power_w", "last_ac_power_w"),
        ("dc_power_w", "last_dc_power_w"),
        ("pv1_power_w", "last_pv1_power_w"),
        ("pv2_power_w", "last_pv2_power_w"),
        ("pv1_current_a", "last_pv1_current_a"),
        ("pv2_current_a", "last_pv2_current_a"),
        ("ac_r_current_a", "last_ac_r_current_a"),
        ("ac_y_current_a", "last_ac_y_current_a"),
        ("ac_b_current_a", "last_ac_b_current_a"),
        ("reactive_power_var", "last_reactive_power_var"),
        ("load_factor_pct", "last_load_factor_pct"),
    ):
        row[dst] = row.get(src)
    row["is_overvoltage"] = None
    row["is_undervoltage"] = None
    row["is_frequency_excursion"] = None


def _daily_for_dates(days: list[date]) -> list[dict[str, Any]]:
    if not days:
        return []
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM public.inverter_daily_stats
            WHERE reading_date = ANY(%(days)s)
            ORDER BY reading_date DESC, inverter_id
            """,
            {"days": days},
        )
        return [jsonable(r) for r in cur.fetchall()]


def _plant_from_daily(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "today_energy_kwh": None,
            "max_ac_power_w": None,
            "specific_yield_kwh_per_kw": None,
            "sample_count": 0,
            "overvoltage_count": 0,
            "fault_sample_count": 0,
            "inverters": 0,
        }
    energy = sum(as_float(r.get("max_today_energy_kwh")) or 0 for r in rows)
    peak = sum((r.get("max_ac_power_w") or 0) for r in rows)
    rated = sum((r.get("rated_dc_w") or 0) for r in rows) or None
    sy = (energy * 1000.0 / rated) if rated else None
    return {
        "today_energy_kwh": round(energy, 2),
        "max_ac_power_w": peak,
        "specific_yield_kwh_per_kw": round(sy, 3) if sy is not None else None,
        "sample_count": sum((r.get("sample_count") or 0) for r in rows),
        "overvoltage_count": sum((r.get("overvoltage_count") or 0) for r in rows),
        "fault_sample_count": sum((r.get("fault_sample_count") or 0) for r in rows),
        "inverters": len(rows),
    }


def _pct_delta(today: float | None, yesterday: float | None) -> float | None:
    if today is None or yesterday is None or yesterday == 0:
        return None
    return round(100.0 * (today - yesterday) / yesterday, 1)


@router.get("/health")
def health():
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True, "db": True}
    except Exception as e:
        return {"ok": False, "db": False, "error": str(e)}


_WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm + hail",
    99: "Thunderstorm + hail",
}


def _parse_weather_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=SITE_TZ)
    return ts.astimezone(timezone.utc)


def _bucket_ts(dt: datetime, seconds: int = WEATHER_SAMPLE_SEC) -> datetime:
    """Floor timestamp to a fixed interval (default 30s) for unique weather rows."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    step = max(1, int(seconds))
    epoch = int(dt.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % step), tz=timezone.utc)


def _store_weather_sample(sample: dict[str, Any]) -> bool:
    """Upsert one Open-Meteo snapshot into plant_weather. Returns True on success."""
    # Use wall-clock 30s buckets so we get a new row every sample interval.
    # Open-Meteo current.time often stays on the same minute for a long time.
    ts = _bucket_ts(_now_utc(), WEATHER_SAMPLE_SEC)
    reading_day = ts.astimezone(SITE_TZ).date()
    loc = sample.get("location") or {}
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.plant_weather (
                    ts, reading_date, plant_id, latitude, longitude,
                    temperature_c, feels_like_c, humidity_pct, precipitation_mm,
                    cloud_cover_pct, wind_speed_kmh, wind_direction_deg,
                    ghi_wm2, weather_code, condition, source
                ) VALUES (
                    %(ts)s, %(reading_date)s, %(plant_id)s, %(lat)s, %(lon)s,
                    %(temperature_c)s, %(feels_like_c)s, %(humidity_pct)s,
                    %(precipitation_mm)s, %(cloud_cover_pct)s, %(wind_speed_kmh)s,
                    %(wind_direction_deg)s, %(ghi_wm2)s, %(weather_code)s,
                    %(condition)s, %(source)s
                )
                ON CONFLICT (plant_id, ts) DO UPDATE SET
                    temperature_c = EXCLUDED.temperature_c,
                    feels_like_c = EXCLUDED.feels_like_c,
                    humidity_pct = EXCLUDED.humidity_pct,
                    precipitation_mm = EXCLUDED.precipitation_mm,
                    cloud_cover_pct = EXCLUDED.cloud_cover_pct,
                    wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                    wind_direction_deg = EXCLUDED.wind_direction_deg,
                    ghi_wm2 = EXCLUDED.ghi_wm2,
                    weather_code = EXCLUDED.weather_code,
                    condition = EXCLUDED.condition,
                    received_at = now()
                """,
                {
                    "ts": ts,
                    "reading_date": reading_day,
                    "plant_id": PLANT_ID,
                    "lat": loc.get("latitude", PLANT_LAT),
                    "lon": loc.get("longitude", PLANT_LON),
                    "temperature_c": sample.get("temperature_c"),
                    "feels_like_c": sample.get("feels_like_c"),
                    "humidity_pct": sample.get("humidity_pct"),
                    "precipitation_mm": sample.get("precipitation_mm"),
                    "cloud_cover_pct": sample.get("cloud_cover_pct"),
                    "wind_speed_kmh": sample.get("wind_speed_kmh"),
                    "wind_direction_deg": sample.get("wind_direction_deg"),
                    "ghi_wm2": sample.get("ghi_wm2"),
                    "weather_code": sample.get("weather_code"),
                    "condition": sample.get("condition"),
                    "source": sample.get("source") or "open-meteo",
                },
            )
            conn.commit()
        log.info(
            "plant_weather stored ts=%s ghi=%s",
            ts.isoformat(),
            sample.get("ghi_wm2"),
        )
        return True
    except Exception as e:
        # Table may not exist yet — weather UI still works from live upstream.
        log.warning("plant_weather upsert failed: %s", e)
        return False


def _latest_stored_weather() -> dict[str, Any] | None:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts, received_at, ghi_wm2, temperature_c, humidity_pct, cloud_cover_pct,
                       wind_speed_kmh, condition
                FROM public.plant_weather
                WHERE plant_id = %(plant_id)s
                ORDER BY ts DESC
                LIMIT 1
                """,
                {"plant_id": PLANT_ID},
            )
            row = cur.fetchone()
        return jsonable(row) if row else None
    except Exception:
        return None


def _maybe_refresh_weather_store(max_age_sec: int | None = None) -> None:
    """Fetch+store weather when the latest DB sample is older than the interval."""
    interval = WEATHER_SAMPLE_SEC if max_age_sec is None else max_age_sec
    wx = _latest_stored_weather()
    if wx and wx.get("received_at"):
        recv = wx["received_at"]
        recv_iso = recv if isinstance(recv, str) else getattr(recv, "isoformat", lambda: None)()
        age = _age_seconds(recv_iso)
        if age is not None and age < interval:
            return
    elif wx and wx.get("ts"):
        ts = wx["ts"]
        ts_iso = ts if isinstance(ts, str) else getattr(ts, "isoformat", lambda: None)()
        age = _age_seconds(ts_iso)
        if age is not None and age < interval:
            return
    try:
        weather()
    except Exception as e:
        log.warning("background weather refresh failed: %s", e)


def _attach_ghi_to_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach nearest prior ghi_wm2 from plant_weather onto each series bucket."""
    if not rows:
        return rows
    times: list[datetime] = []
    for r in rows:
        ts = _parse_weather_ts(r.get("bucket_ts"))
        if ts is not None:
            times.append(ts)
    if not times:
        return rows
    t0, t1 = min(times), max(times)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts, ghi_wm2
                FROM public.plant_weather
                WHERE plant_id = %(plant_id)s
                  AND ts >= %(t0)s - interval '2 hours'
                  AND ts <= %(t1)s + interval '15 minutes'
                ORDER BY ts
                """,
                {"plant_id": PLANT_ID, "t0": t0, "t1": t1},
            )
            wx = [( _parse_weather_ts(r["ts"]), as_float(r["ghi_wm2"]) ) for r in cur.fetchall()]
            wx = [(t, g) for t, g in wx if t is not None]
    except Exception as e:
        log.warning("ghi series lookup skipped: %s", e)
        return rows

    if not wx:
        for r in rows:
            r["ghi_wm2"] = None
        return rows

    for r in rows:
        ts = _parse_weather_ts(r.get("bucket_ts"))
        if ts is None:
            r["ghi_wm2"] = None
            continue
        best = None
        for wts, ghi in wx:
            if wts <= ts:
                best = ghi
            else:
                break
        r["ghi_wm2"] = best
    return rows


@router.get("/weather")
def weather():
    """Live weather at the plant site (Open-Meteo) — also persisted to plant_weather."""
    params = urlencode({
        "latitude": PLANT_LAT,
        "longitude": PLANT_LON,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "shortwave_radiation",
        ]),
        "timezone": "Asia/Kolkata",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        req = Request(url, headers={"User-Agent": "HPCL-SolarDashboard/1.0"})
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, OSError, ValueError) as e:
        raise HTTPException(502, f"weather upstream failed: {e}") from e

    cur = payload.get("current") or {}
    code = cur.get("weather_code")
    sample = {
        "ok": True,
        "source": "open-meteo",
        "location": {
            "label": PLANT_LABEL,
            "plus_code": "XRPX+34F",
            "latitude": PLANT_LAT,
            "longitude": PLANT_LON,
        },
        "as_of": cur.get("time"),
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "precipitation_mm": cur.get("precipitation"),
        "cloud_cover_pct": cur.get("cloud_cover"),
        "wind_speed_kmh": cur.get("wind_speed_10m"),
        "wind_direction_deg": cur.get("wind_direction_10m"),
        "ghi_wm2": cur.get("shortwave_radiation"),
        "weather_code": code,
        "condition": _WMO.get(code, "—"),
        "stored": False,
    }
    sample["stored"] = _store_weather_sample(sample)
    return sample


@router.get("/latest")
def latest():
    """Latest derived reading per inverter + plant totals + staleness + alerts."""
    # Keep plant_weather filled even if the UI caches /api/weather.
    _maybe_refresh_weather_store()

    sql = """
        SELECT DISTINCT ON (inverter_id)
            inverter_id, reading_id, ts, reading_date, rated_dc_w,
            status_code, status_text, is_grid_connected, has_fault,
            grid_countdown_s,
            ac_power_w, dc_power_w, reactive_power_var,
            apparent_power_va, power_factor, efficiency_pct, load_factor_pct,
            pv1_voltage_v, pv1_current_a, pv1_power_w,
            pv2_voltage_v, pv2_current_a, pv2_power_w,
            strings_voltage_matched, dc_bus_voltage_v, dc_bus_headroom_v,
            grid_frequency_hz,
            ac_r_voltage_v, ac_y_voltage_v, ac_b_voltage_v,
            ac_r_current_a, ac_y_current_a, ac_b_current_a,
            voltage_imbalance_pct, current_imbalance_pct,
            is_frequency_excursion, is_overvoltage, is_undervoltage,
            today_energy_kwh, today_grid_minutes,
            total_energy_kwh, total_runtime_h,
            heatsink_temp_c, internal_temp_c
        FROM public.inverter_data_derived
        ORDER BY inverter_id, ts DESC
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = [jsonable(r) for r in cur.fetchall()]

    as_of = max((r["ts"] for r in rows), default=None)
    age = _age_seconds(as_of)
    stale = age is None or age > STALE_AFTER_SEC

    for r in rows:
        r_age = _age_seconds(r.get("ts"))
        r["data_age_sec"] = round(r_age) if r_age is not None else None
        r["is_stale"] = r_age is None or r_age > STALE_AFTER_SEC
        te = as_float(r.get("today_energy_kwh"))
        rated = r.get("rated_dc_w") or 0
        r["specific_yield_kwh_per_kw"] = (
            round(te * 1000.0 / rated, 3) if te is not None and rated else None
        )
        # Preserve last_* copies; keep sample values for display when stale.
        if r["is_stale"]:
            _zero_instantaneous(r)

    # Prefer last_* for plant totals when stale so Overview matches the chart.
    plant_ac = sum(
        (r.get("last_ac_power_w") if r.get("is_stale") else r.get("ac_power_w")) or 0
        for r in rows
    )
    plant_dc = sum(
        (r.get("last_dc_power_w") if r.get("is_stale") else r.get("dc_power_w")) or 0
        for r in rows
    )
    plant_last_ac = sum((r.get("last_ac_power_w") or r.get("ac_power_w") or 0) for r in rows)
    plant_last_dc = sum((r.get("last_dc_power_w") or r.get("dc_power_w") or 0) for r in rows)
    plant_today = sum(as_float(r.get("today_energy_kwh")) or 0 for r in rows)
    plant_lifetime = sum((r.get("total_energy_kwh") or 0) for r in rows)
    plant_rated = sum((r.get("rated_dc_w") or 0) for r in rows) or None

    # Expose last sample as the primary power fields when feed is stale.
    if stale:
        for r in rows:
            if r.get("last_ac_power_w") is not None:
                r["ac_power_w"] = r["last_ac_power_w"]
            if r.get("last_dc_power_w") is not None:
                r["dc_power_w"] = r["last_dc_power_w"]
            for src, dst in (
                ("last_pv1_power_w", "pv1_power_w"),
                ("last_pv2_power_w", "pv2_power_w"),
                ("last_pv1_current_a", "pv1_current_a"),
                ("last_pv2_current_a", "pv2_current_a"),
                ("last_load_factor_pct", "load_factor_pct"),
            ):
                if r.get(src) is not None:
                    r[dst] = r[src]

    wx = _latest_stored_weather() or {}
    return {
        "inverters": rows,
        "alerts": _build_alerts(rows, plant_stale=stale),
        "plant": {
            "ac_power_w": plant_ac,
            "dc_power_w": plant_dc,
            "last_ac_power_w": plant_last_ac,
            "last_dc_power_w": plant_last_dc,
            "today_energy_kwh": round(plant_today, 2),
            "total_energy_kwh": plant_lifetime,
            "specific_yield_kwh_per_kw": (
                round(plant_today * 1000.0 / plant_rated, 3) if plant_rated else None
            ),
            "inverter_count": len(rows),
            "as_of": as_of,
            "data_age_sec": round(age) if age is not None else None,
            "is_stale": stale,
            "stale_after_sec": STALE_AFTER_SEC,
            "power_is_live": not stale,
            "ghi_wm2": as_float(wx.get("ghi_wm2")),
            "ghi_as_of": wx.get("ts"),
            "weather_condition": wx.get("condition"),
        },
        "server_time": _now_utc().isoformat(),
        "site_today": _local_today().isoformat(),
    }


@router.get("/compare")
def compare():
    """Today vs yesterday from inverter_daily_stats (+ live today energy fallback)."""
    today = _local_today()
    yesterday = today - timedelta(days=1)

    # Prefer calendar "today" / "yesterday"; if today's daily row is thin
    # (partial ingest), still return latest two distinct dates present.
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT reading_date
            FROM public.inverter_daily_stats
            ORDER BY reading_date DESC
            LIMIT 5
            """
        )
        available = [r["reading_date"] for r in cur.fetchall()]

    today_rows = _daily_for_dates([today])
    yday_rows = _daily_for_dates([yesterday])

    # If no row for calendar today yet, use most recent date as "today"
    # and previous as "yesterday" so the compare panel still works.
    used_today = today
    used_yesterday = yesterday
    if not today_rows and available:
        used_today = available[0]
        today_rows = _daily_for_dates([used_today])
        if len(available) > 1:
            used_yesterday = available[1]
            yday_rows = _daily_for_dates([used_yesterday])

    today_plant = _plant_from_daily(today_rows)
    yday_plant = _plant_from_daily(yday_rows)

    # Live today energy from latest derived (more current than daily_stats max)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (inverter_id)
                inverter_id, today_energy_kwh, rated_dc_w, ac_power_w, ts
            FROM public.inverter_data_derived
            WHERE reading_date = %(day)s
            ORDER BY inverter_id, ts DESC
            """,
            {"day": used_today},
        )
        live = [jsonable(r) for r in cur.fetchall()]

    live_today_kwh = round(
        sum(as_float(r.get("today_energy_kwh")) or 0 for r in live), 2
    ) if live else today_plant["today_energy_kwh"]

    by_inv: list[dict[str, Any]] = []
    ymap = {r["inverter_id"]: r for r in yday_rows}
    tmap = {r["inverter_id"]: r for r in today_rows}
    live_map = {r["inverter_id"]: r for r in live}
    for inv in sorted(set(tmap) | set(ymap) | set(live_map)):
        t = tmap.get(inv) or {}
        y = ymap.get(inv) or {}
        lv = live_map.get(inv) or {}
        t_e = as_float(lv.get("today_energy_kwh"))
        if t_e is None:
            t_e = as_float(t.get("max_today_energy_kwh"))
        y_e = as_float(y.get("max_today_energy_kwh"))
        by_inv.append({
            "inverter_id": inv,
            "today_energy_kwh": t_e,
            "yesterday_energy_kwh": y_e,
            "delta_kwh": round(t_e - y_e, 2) if t_e is not None and y_e is not None else None,
            "delta_pct": _pct_delta(t_e, y_e),
            "today_peak_ac_w": t.get("max_ac_power_w"),
            "yesterday_peak_ac_w": y.get("max_ac_power_w"),
            "today_specific_yield": (
                as_float(t.get("specific_yield_kwh_per_kw"))
                or (
                    round(t_e * 1000.0 / lv["rated_dc_w"], 3)
                    if t_e is not None and lv.get("rated_dc_w")
                    else None
                )
            ),
            "yesterday_specific_yield": as_float(y.get("specific_yield_kwh_per_kw")),
            "today_string_match_pct": as_float(t.get("string_voltage_match_pct")),
            "yesterday_overvoltage_count": y.get("overvoltage_count"),
            "today_overvoltage_count": t.get("overvoltage_count"),
        })

    return {
        "today_date": used_today.isoformat() if hasattr(used_today, "isoformat") else str(used_today),
        "yesterday_date": (
            used_yesterday.isoformat()
            if hasattr(used_yesterday, "isoformat")
            else str(used_yesterday)
        ),
        "today": {
            **today_plant,
            "live_today_energy_kwh": live_today_kwh,
        },
        "yesterday": yday_plant,
        "delta": {
            "energy_kwh": (
                round(live_today_kwh - (yday_plant["today_energy_kwh"] or 0), 2)
                if live_today_kwh is not None and yday_plant["today_energy_kwh"] is not None
                else None
            ),
            "energy_pct": _pct_delta(live_today_kwh, yday_plant["today_energy_kwh"]),
            "peak_ac_w": (
                (today_plant["max_ac_power_w"] or 0) - (yday_plant["max_ac_power_w"] or 0)
                if today_plant["max_ac_power_w"] is not None
                and yday_plant["max_ac_power_w"] is not None
                else None
            ),
            "specific_yield_pct": _pct_delta(
                today_plant["specific_yield_kwh_per_kw"],
                yday_plant["specific_yield_kwh_per_kw"],
            ),
        },
        "inverters": by_inv,
    }


@router.get("/analytics")
def analytics(
    range: str = Query("yesterday", pattern="^(yesterday|week|month)$"),
):
    """
    Analytics comparison ranges.
    yesterday — full day-over-day from daily_stats + series.
    week / month — placeholder until enough history exists.
    """
    today = _local_today()

    if range in ("week", "month"):
        need_days = 7 if range == "week" else 30
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(DISTINCT reading_date) AS n
                FROM public.inverter_daily_stats
                """
            )
            n = cur.fetchone()["n"] or 0
        return {
            "range": range,
            "available": False,
            "days_present": n,
            "days_required": need_days,
            "message": (
                f"Not enough history for {range} compare yet "
                f"({n}/{need_days} distinct days in inverter_daily_stats)."
            ),
            "plant": None,
            "inverters": [],
            "series": [],
        }

    # yesterday range — 15-min buckets for a static full-day chart
    cmp = compare()
    yday = date.fromisoformat(cmp["yesterday_date"])
    today_d = date.fromisoformat(cmp["today_date"])
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                to_timestamp(
                    floor(extract(epoch FROM ts) / 900) * 900
                ) AS bucket_ts,
                inverter_id,
                round(avg(ac_power_w))::INTEGER AS ac_power_w,
                round(avg(today_energy_kwh)::numeric, 2) AS today_energy_kwh
            FROM public.inverter_data_derived
            WHERE reading_date = %(day)s
            GROUP BY 1, inverter_id
            ORDER BY 1, inverter_id
            """,
            {"day": yday},
        )
        series = [jsonable(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT
                to_timestamp(
                    floor(extract(epoch FROM ts) / 900) * 900
                ) AS bucket_ts,
                inverter_id,
                round(avg(ac_power_w))::INTEGER AS ac_power_w,
                round(avg(today_energy_kwh)::numeric, 2) AS today_energy_kwh
            FROM public.inverter_data_derived
            WHERE reading_date = %(day)s
            GROUP BY 1, inverter_id
            ORDER BY 1, inverter_id
            """,
            {"day": today_d},
        )
        series_today = [jsonable(r) for r in cur.fetchall()]

    return {
        "range": "yesterday",
        "available": True,
        "days_present": 2,
        "days_required": 2,
        "message": None,
        "compare": cmp,
        "series": series,
        "series_today": series_today,
        "bucket_minutes": 15,
        "today": today.isoformat(),
        "yesterday_date": cmp["yesterday_date"],
        "today_date": cmp["today_date"],
    }


@router.get("/series")
def series(
    hours: float = Query(6, ge=0.25, le=168),
    bucket_seconds: int = Query(60, ge=15, le=3600),
    inverter_id: int | None = Query(None),
    day: date | None = Query(None, description="Limit to a local reading_date"),
):
    """Bucketed averages from inverter_data_derived."""
    where: list[str] = []
    params: dict[str, Any] = {"bucket": bucket_seconds}

    if day is not None:
        where.append("reading_date = %(day)s")
        params["day"] = day
    else:
        where.append("ts >= %(cutoff)s")
        params["cutoff"] = _now_utc() - timedelta(hours=hours)

    if inverter_id is not None:
        where.append("inverter_id = %(inv)s")
        params["inv"] = inverter_id

    sql = f"""
        SELECT
            to_timestamp(
                floor(extract(epoch FROM ts) / %(bucket)s) * %(bucket)s
            ) AS bucket_ts,
            inverter_id,
            round(avg(ac_power_w))::INTEGER          AS ac_power_w,
            round(avg(dc_power_w))::INTEGER          AS dc_power_w,
            round(avg(today_energy_kwh)::numeric, 2) AS today_energy_kwh,
            round(avg(efficiency_pct)::numeric, 2)   AS efficiency_pct,
            round(avg(heatsink_temp_c)::numeric, 1)  AS heatsink_temp_c,
            round(avg(grid_frequency_hz)::numeric, 2) AS grid_frequency_hz,
            round(avg(pv1_power_w))::INTEGER         AS pv1_power_w,
            round(avg(pv2_power_w))::INTEGER         AS pv2_power_w,
            count(*)::INTEGER                        AS n
        FROM public.inverter_data_derived
        WHERE {' AND '.join(where)}
        GROUP BY 1, inverter_id
        ORDER BY 1, inverter_id
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = [jsonable(r) for r in cur.fetchall()]

    rows = _attach_ghi_to_series(rows)

    return {
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "day": day.isoformat() if day else None,
        "points": rows,
    }


@router.get("/daily")
def daily(
    day: date | None = Query(None, description="Asia/Kolkata date YYYY-MM-DD"),
    days: int = Query(7, ge=1, le=90),
):
    """Rows from inverter_daily_stats (3 per calendar day)."""
    if day is not None:
        sql = """
            SELECT *
            FROM public.inverter_daily_stats
            WHERE reading_date = %(day)s
            ORDER BY inverter_id
        """
        params: dict[str, Any] = {"day": day}
    else:
        sql = """
            SELECT *
            FROM public.inverter_daily_stats
            WHERE reading_date >= (
                SELECT COALESCE(max(reading_date), CURRENT_DATE) - %(span)s
                FROM public.inverter_daily_stats
            )
            ORDER BY reading_date DESC, inverter_id
        """
        params = {"span": days - 1}

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = [jsonable(r) for r in cur.fetchall()]

    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["reading_date"], []).append(r)

    plant = []
    for d, invs in sorted(by_date.items(), reverse=True):
        plant.append({
            "reading_date": d,
            **_plant_from_daily(invs),
        })

    return {"rows": rows, "plant_by_date": plant}


@router.get("/inverter/{inverter_id}")
def inverter_detail(inverter_id: int):
    if inverter_id not in (1, 2, 3):
        raise HTTPException(404, "unknown inverter")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM public.inverter_data_derived
            WHERE inverter_id = %(id)s
            ORDER BY ts DESC
            LIMIT 1
            """,
            {"id": inverter_id},
        )
        latest_row = jsonable(cur.fetchone())

        cur.execute(
            """
            SELECT *
            FROM public.inverter_daily_stats
            WHERE inverter_id = %(id)s
            ORDER BY reading_date DESC
            LIMIT 14
            """,
            {"id": inverter_id},
        )
        daily_rows = [jsonable(r) for r in cur.fetchall()]

    return {"latest": latest_row, "daily": daily_rows}
