"""H5: the requested mode is persisted on the Investigation and exposed by GET.
H6: a live investigation without LLM configuration falls back to replay and still completes."""

import time

import pytest


@pytest.mark.parametrize("body, expected", [
    ({"incident_id": "INC-2041"}, "replay"),
    ({"incident_id": "INC-2041", "mode": "replay"}, "replay"),
    ({"incident_id": "INC-2041", "mode": "live"}, "live"),
])
def test_mode_is_persisted_and_exposed(client, monkeypatch, body, expected):
    # No live endpoint configured, so a live run can never reach the network.
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    response = client.post("/api/investigations", json=body)
    assert response.status_code == 200
    investigation = client.get(f"/api/investigations/{response.json()['investigation_id']}").json()
    assert investigation["mode"] == expected


def test_live_without_config_falls_back_and_completes(client, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    response = client.post("/api/investigations", json={"incident_id": "INC-2041", "mode": "live"})
    investigation_id = response.json()["investigation_id"]
    deadline = time.time() + 10
    while (investigation := client.get(f"/api/investigations/{investigation_id}").json())["stage"] not in (
            "awaiting_approval", "failed") and time.time() < deadline:
        time.sleep(0.05)
    assert investigation["stage"] == "awaiting_approval", investigation["error"]
    assert investigation["mode"] == "live"
    assert any(s["kind"] == "decision" and s["output_summary"].startswith("Live LLM unavailable")
               for s in investigation["steps"])


def test_unknown_mode_is_422(client):
    assert client.post("/api/investigations", json={"incident_id": "INC-2041", "mode": "bogus"}).status_code == 422
