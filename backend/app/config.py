"""Application configuration."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

# backend/ package root; repo root is one level up (sql/, data/, scripts/)
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SQL_DIR = REPO_ROOT / "sql"
DATA_DIR = REPO_ROOT / "data"

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://USER:PASSWORD@127.0.0.1:5432/hpcl_solar",
)

SITE_TZ = ZoneInfo("Asia/Kolkata")

# Plant site — Devanagonthi terminal (exact plant coords)
PLANT_LAT = float(os.environ.get("PLANT_LAT", "12.9862093"))
PLANT_LON = float(os.environ.get("PLANT_LON", "77.8467266"))
PLANT_LABEL = os.environ.get("PLANT_LABEL", "Devanagonthi, Karnataka")
PLANT_ID = int(os.environ.get("PLANT_ID", "402"))

# Peak-observed DC watts (lower bounds). Replace with nameplate figures.
RATED_DC_W: dict[int, int] = {
    1: 13750,
    2: 18100,
    3: 27990,
}
DEFAULT_RATED_DC_W = 15000

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

# No fresh sample within this window => treat feed as stale (UI dims / alerts).
# Plant Modbus polls are often every few minutes; 2 min was too aggressive.
STALE_AFTER_SEC = int(os.environ.get("STALE_AFTER_SEC", str(20 * 60)))

# Persist Open-Meteo snapshots into plant_weather this often.
WEATHER_SAMPLE_SEC = int(os.environ.get("WEATHER_SAMPLE_SEC", "30"))

_DEFAULT_CORS = "http://127.0.0.1:5173,http://localhost:5173"
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", _DEFAULT_CORS).split(",")
    if o.strip()
]
