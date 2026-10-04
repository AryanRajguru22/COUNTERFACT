import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_agent_delay(monkeypatch):
    monkeypatch.setenv("STEP_DELAY_MS", "0")
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("RECORD", "0")  # "0", not unset: backend/main.py's .env loader never overrides a set var
    monkeypatch.setenv("LLM_HYPOTHESES", "0")  # same reason; H18 tests opt in explicitly


@pytest.fixture
def client():
    from backend.main import app

    return TestClient(app)
