"""Golden end-to-end: Investigate -> awaiting_approval -> approve -> resolved."""

import time

from data.loader import load_ground_truth

STAGES = ["timeline", "hypotheses", "evidence", "testing", "root_cause", "counterfactual", "awaiting_approval"]


def _wait_for(client, investigation_id, stages, timeout=10):
    deadline = time.time() + timeout
    while True:
        investigation = client.get(f"/api/investigations/{investigation_id}").json()
        if investigation["stage"] in stages:
            return investigation
        if time.time() > deadline:
            raise AssertionError(f"stuck at {investigation['stage']}: {investigation['error']}")
        time.sleep(0.05)


def _start(client):
    response = client.post("/api/investigations", json={"incident_id": "INC-2041", "mode": "replay"})
    assert response.status_code == 200
    return response.json()["investigation_id"]


def test_investigation_reaches_awaiting_approval(client):
    truth = load_ground_truth("INC-2041")
    investigation = _wait_for(client, _start(client), {"awaiting_approval", "failed"})
    assert investigation["stage"] == "awaiting_approval", investigation["error"]
    assert investigation["mode"] == "replay"
    assert investigation["root_cause"]["hypothesis_id"] == truth["root_cause_hypothesis_id"]
    rejected = sorted(h["id"] for h in investigation["hypotheses"] if h["status"] == "rejected")
    assert rejected == sorted(truth["rejected_hypothesis_ids"])
    assert investigation["recommendation"]["prevented"] is True
    assert investigation["recommendation"]["intervention_id"] in truth["preventing_intervention_ids"]
    # steps are logged in every working stage, in order; awaiting_approval is the resting stage
    assert list(dict.fromkeys(s["stage"] for s in investigation["steps"])) == STAGES[:-1]
    assert any(s["kind"] == "thought" for s in investigation["steps"])


def test_approve_executes_and_verifies(client):
    investigation_id = _start(client)
    recommended = _wait_for(client, investigation_id, {"awaiting_approval"})["recommendation"]["intervention_id"]
    response = client.post(f"/api/investigations/{investigation_id}/approval",
                           json={"intervention_id": recommended, "decision": "approved", "approver": "aryan"})
    assert response.status_code == 200
    investigation = _wait_for(client, investigation_id, {"resolved", "failed"})
    assert investigation["stage"] == "resolved"
    assert investigation["execution"]["status"] == "applied"
    assert investigation["verification"]["passed"] is True
    assert investigation["approval"]["at"]


def test_reject_replans_to_next_recommendation(client):
    investigation_id = _start(client)
    first = _wait_for(client, investigation_id, {"awaiting_approval"})["recommendation"]["intervention_id"]
    client.post(f"/api/investigations/{investigation_id}/approval",
                json={"intervention_id": first, "decision": "rejected", "approver": "aryan", "note": "too risky"})
    investigation = _wait_for(client, investigation_id, {"awaiting_approval"})
    assert investigation["recommendation"]["intervention_id"] != first
    assert investigation["attempts"] == 1


def test_second_approval_is_409(client):
    investigation_id = _start(client)
    _wait_for(client, investigation_id, {"awaiting_approval"})
    body = {"intervention_id": "I1", "decision": "approved", "approver": "aryan"}
    client.post(f"/api/investigations/{investigation_id}/approval", json=body)
    _wait_for(client, investigation_id, {"resolved"})
    assert client.post(f"/api/investigations/{investigation_id}/approval", json=body).status_code == 409
