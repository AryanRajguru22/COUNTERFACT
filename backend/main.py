"""FastAPI app. Owner: Rohit. Run from the repo root: uvicorn backend.main:app --reload"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _load_dotenv(path: Path = Path(__file__).resolve().parent.parent / ".env") -> None:
    """Minimal .env reader (avoids a python-dotenv dependency). Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

from backend.routes import router  # noqa: E402  (env must be loaded first)

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API: CORS_ORIGINS (comma separated) plus the local dev server."""
    extra = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    return DEV_ORIGINS + [o for o in extra if o not in DEV_ORIGINS]


app = FastAPI(title="COUNTERFACT", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
