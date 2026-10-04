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

app = FastAPI(title="COUNTERFACT", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
