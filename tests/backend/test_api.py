"""API health, incident listing and the simulate endpoint."""


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "llm_mode": "replay"}


def test_list_incidents(client):
    response = client.get("/api/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert [i["id"] for i in incidents] == ["INC-2041"]
    assert incidents[0]["window"]["minutes"] == 60


def test_unknown_ids_are_404(client):
    assert client.post("/api/investigations", json={"incident_id": "NOPE"}).status_code == 404
    assert client.get("/api/investigations/inv-missing").status_code == 404


def test_simulate_endpoint(client):
    response = client.post("/api/simulate", json={"incident_id": "INC-2041", "intervention_ids": ["I1"]})
    assert response.status_code == 200
    assert response.json()["prevented"] is True
