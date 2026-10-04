"""LLM access. Owner: Rohit.

replay (default): returns recorded responses from agent/recordings/<incident_id>.json.
             No network, no key — the demo always runs in this mode.
live:        any OpenAI-compatible chat-completions endpoint (Groq, Google AI Studio,
             local Ollama, ...) configured by LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

RECORDINGS_DIR = Path(__file__).parent / "recordings"


def llm_mode() -> str:
    return os.environ.get("LLM_MODE", "replay").strip().lower() or "replay"


class LLMClient:
    def __init__(self, incident_id: str, mode: str | None = None):
        self.incident_id = incident_id
        self.mode = (mode or llm_mode()).lower()
        if self.mode not in ("replay", "live"):
            raise ValueError(f"unknown LLM mode: {self.mode}")
        self._recordings: dict[str, str] | None = None

    def complete(self, key: str, messages: list[dict[str, str]] | None = None) -> str:
        """Return the model's text for a prompt. `key` names the prompt so replay can look it up."""
        if self.mode == "replay":
            return self._replay(key)
        return self._live(messages or [{"role": "user", "content": key}])

    def _replay(self, key: str) -> str:
        if self._recordings is None:
            path = RECORDINGS_DIR / f"{self.incident_id}.json"
            self._recordings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return self._recordings.get(key, "")

    def _live(self, messages: list[dict[str, str]]) -> str:
        base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        model = os.environ.get("LLM_MODEL", "")
        if not base_url or not model:
            raise RuntimeError("LLM_MODE=live needs LLM_BASE_URL and LLM_MODEL (see .env.example)")
        headers = {}
        if api_key := os.environ.get("LLM_API_KEY"):
            headers["Authorization"] = f"Bearer {api_key}"
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "temperature": 0},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
