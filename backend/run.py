#!/usr/bin/env python3
"""Start the HPCL Solar Dashboard API.

    cd backend
    python run.py
    python run.py --port 8080 --reload
"""

from __future__ import annotations

import argparse

import uvicorn

from app.config import HOST, PORT


def main() -> None:
    p = argparse.ArgumentParser(description="HPCL Solar Dashboard API")
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
