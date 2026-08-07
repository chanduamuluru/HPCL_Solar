"""
HPCL Solar Dashboard — FastAPI API (no UI).

    cd backend
    python run.py
    # or: uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import CORS_ORIGINS

app = FastAPI(title="HPCL Solar Dashboard API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "HPCL Solar Dashboard API",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }
