"""H5: the requested mode is persisted on the Investigation and exposed by GET."""

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


def test_unknown_mode_is_422(client):
    assert client.post("/api/investigations", json={"incident_id": "INC-2041", "mode": "bogus"}).status_code == 422
