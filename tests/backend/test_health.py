"""H12: /api/health validates the fixtures the real engines read, without ever calling the LLM.

Broken fixtures live in a temp copy of data/incidents; the real files are never written.
"""

import shutil
from pathlib import Path

import pytest

from agent import llm, tools
from data import loader


@pytest.fixture
def folder(monkeypatch, tmp_path) -> Path:
    name = loader._incident_dirs()["INC-2041"].name
    shutil.copytree(loader.INCIDENTS_DIR, tmp_path / "incidents")
    monkeypatch.setattr(loader, "INCIDENTS_DIR", tmp_path / "incidents")
    loader._incident_dirs.cache_clear()
    yield tmp_path / "incidents" / name
    loader._incident_dirs.cache_clear()


@pytest.fixture
def no_llm(monkeypatch) -> list:
    """Fail loudly if anything reaches the live endpoint; returns the list of attempted calls."""
    calls = []
    monkeypatch.setattr(llm.httpx, "post", lambda *args, **kwargs: calls.append(args) or pytest.fail("LLM called"))
    return calls


def test_healthy_fixtures_are_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "llm_mode": "replay"}


@pytest.mark.parametrize("name, content", [("events.json", "{not json"), ("traces.json", "{not json"),
                                           ("config.json", "[]"), ("metrics.json", '[{"name": "x"}]')])
def test_broken_fixture_is_503_naming_the_file(client, folder, name, content):
    (folder / name).write_text(content, encoding="utf-8")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"].startswith(f"fixtures failed to load: FixtureError: INC-2041 {name}: ")


@pytest.mark.parametrize("name", ["events.json", "metrics.json", "system_model.json"])
def test_missing_required_fixture_is_503(client, folder, name):
    (folder / name).unlink()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert f"INC-2041 {name}: FileNotFoundError" in response.json()["detail"]


def test_health_never_calls_the_llm_even_in_live_mode(client, monkeypatch, no_llm):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    response = client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"ok": True, "llm_mode": "live"}
    assert no_llm == []


def test_replay_recording_check_is_preserved(client, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "RECORDINGS_DIR", tmp_path)
    assert client.get("/api/health").status_code == 200  # no recording: replay just has no narration
    (tmp_path / "INC-2041.json").write_text("{not json", encoding="utf-8")
    response = client.get("/api/health")
    assert response.status_code == 503 and "JSONDecodeError" in response.json()["detail"]


def test_health_does_not_touch_investigation_state(client, folder):
    investigation_id = client.post("/api/investigations", json={"incident_id": "INC-2041"}).json()["investigation_id"]
    before = client.get(f"/api/investigations/{investigation_id}").json()
    assert client.get("/api/health").status_code == 200
    (folder / "events.json").write_text("{not json", encoding="utf-8")
    assert client.get("/api/health").status_code == 503
    assert client.get(f"/api/investigations/{investigation_id}").json() == before
