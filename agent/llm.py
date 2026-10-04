"""LLM access. Owner: Rohit.

replay (default): returns recorded responses from agent/recordings/<incident_id>.json.
             No network, no key — the demo always runs in this mode.
live:        any OpenAI-compatible chat-completions endpoint (Groq, Google AI Studio,
             local Ollama, ...) configured by LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
             If the configuration is missing or a live call fails for any reason, the
             client falls back to replay for the rest of its life and records why in
             `fallback_reason`. `mode` keeps the requested mode.
RECORD=1:    every successful live response is merged into the recording under its key,
             so a later replay run reproduces the live run.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

import httpx

RECORDINGS_DIR = Path(__file__).parent / "recordings"
_RECORD_LOCK = threading.Lock()  # concurrent investigations must not interleave read-merge-write


def llm_mode() -> str:
    return os.environ.get("LLM_MODE", "replay").strip().lower() or "replay"


def recording_enabled() -> bool:
    return os.environ.get("RECORD") == "1"


class LLMClient:
    def __init__(self, incident_id: str, mode: str | None = None, record: bool | None = None):
        self.incident_id = incident_id
        self.mode = (mode or llm_mode()).lower()
        if self.mode not in ("replay", "live"):
            raise ValueError(f"unknown LLM mode: {self.mode}")
        self.record = recording_enabled() if record is None else record
        self._recordings: dict[str, str] | None = None
        self.fallback_reason: str | None = None  # set once a live call fails; replay is used from then on

    def complete(self, key: str, messages: list[dict[str, str]] | None = None) -> str:
        """Return the model's text for a prompt. `key` names the prompt so replay can look it up."""
        if self.mode == "replay" or self.fallback_reason is not None:
            return self._replay(key)
        try:
            text = self._live(messages or [{"role": "user", "content": key}])
        except Exception as error:  # missing config, network, HTTP status or malformed response
            self.fallback_reason = f"{type(error).__name__}: {error}"
            return self._replay(key)
        if self.record and isinstance(text, str) and text:
            self._record(key, text)
        return text

    def _replay(self, key: str) -> str:
        if self._recordings is None:
            path = RECORDINGS_DIR / f"{self.incident_id}.json"
            self._recordings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return self._recordings.get(key, "")

    def _record(self, key: str, text: str) -> None:
        """Merge one live response into the recording, keeping every other key and their order."""
        path = RECORDINGS_DIR / f"{self.incident_id}.json"
        with _RECORD_LOCK:
            recorded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            recorded[key] = text
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write a sibling temp file, then swap it in, so a crash never leaves a half-written recording.
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(recorded, indent=2, ensure_ascii=False) + "\n")
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        if self._recordings is not None:
            self._recordings[key] = text

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
