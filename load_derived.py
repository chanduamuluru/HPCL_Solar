#!/usr/bin/env python3
"""Convenience entry: python load_derived.py … → scripts.load_derived.

Ensures backend/ is on sys.path so `app.config` resolves.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"
for _p in (_BACKEND, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scripts.load_derived import main

if __name__ == "__main__":
    raise SystemExit(main())
