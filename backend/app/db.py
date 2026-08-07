"""Database helpers."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import DSN


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


def jsonable(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, int):
            out[k] = v
        elif isinstance(v, float):
            out[k] = v
        elif hasattr(v, "as_integer_ratio"):  # Decimal
            out[k] = float(v)
        else:
            out[k] = v
    return out


def as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x
