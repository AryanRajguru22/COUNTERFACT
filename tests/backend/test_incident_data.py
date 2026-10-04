"""Read-only incident data endpoints the UI charts from: the system model (SLO) and observed metrics."""


def test_system_model_endpoint(client):
    response = client.get("/api/incidents/INC-2041/system-model")
    assert response.status_code == 200
    model = response.json()
    assert model["slo"] == {"max_error_rate": 0.05, "max_breach_minutes": 0}
    assert model["params"]["pool_size"] == 50
    assert [c["event_id"] for c in model["param_changes"]] == ["E-001", "E-004", "E-009"]
    assert len(model["exogenous"]["demand_rps"]) == 60


def test_metrics_endpoint(client):
    response = client.get("/api/incidents/INC-2041/metrics")
    assert response.status_code == 200
    series = {s["name"]: s for s in response.json()}
    assert "checkout_5xx_rate" in series
    assert series["checkout_5xx_rate"]["unit"] == "ratio"
    assert all(len(s["points"]) == 60 for s in series.values())
    assert max(p["value"] for p in series["checkout_5xx_rate"]["points"]) > 0.3


def test_unknown_incident_is_404(client):
    assert client.get("/api/incidents/NOPE/system-model").status_code == 404
    assert client.get("/api/incidents/NOPE/metrics").status_code == 404
