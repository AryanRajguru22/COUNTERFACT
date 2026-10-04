import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_agent_delay(monkeypatch):
    monkeypatch.setenv("STEP_DELAY_MS", "0")
    monkeypatch.setenv("LLM_MODE", "replay")


@pytest.fixture
def client():
    from backend.main import app

    return TestClient(app)
