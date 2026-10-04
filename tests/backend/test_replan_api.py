"""H15 at the API boundary: approvals must target the CURRENT ranking, and an investigation that hit the
attempt cap accepts no further decisions. The existing approve and reject paths keep working."""

import time

import pytest

from agent import tools
from contracts.models import VerificationCheck, VerificationResult


def _wait(client, investigation_id: str, stages: set[str], timeout: float = 10) -> dict:
    deadline = time.time() + timeout
    while True:
        investigation = client.get(f"/api/investigations/{investigation_id}").json()
        if investigation["stage"] in stages or time.time() > deadline:
            return investigation
        time.sleep(0.05)


def _awaiting(client) -> dict:
    response = client.post("/api/investigations", json={"incident_id": "INC-2041"})
    investigation = _wait(client, response.json()["investigation_id"], {"awaiting_approval", "failed"})
    assert investigation["stage"] == "awaiting_approval", investigation["error"]
    return investigation


def _decide(client, investigation: dict, intervention_id: str, decision: str = "approved", note: str = ""):
    return client.post(f"/api/investigations/{investigation['id']}/approval", json={
        "intervention_id": intervention_id, "decision": decision, "approver": "sre-lead", "note": note})


@pytest.fixture
def verify_fails(monkeypatch):
    def fail(execution, model, seed):
        check = VerificationCheck(name="breach minutes", expected="<= 0", observed="9", passed=False)
        return VerificationResult(intervention_id=execution.intervention_id, passed=False, checks=[check],
                                  stress_test_passed=False)

    monkeypatch.setitem(tools.TOOLS, "verify", fail)


# ---------------------------------------------------------------- approvals target the current ranking


def test_approving_an_intervention_no_longer_in_the_ranking_is_409(client):
    investigation = _awaiting(client)
    first = investigation["recommendation"]["intervention_id"]
    assert _decide(client, investigation, first, "rejected", "change freeze").status_code == 200
    replanned = _wait(client, investigation["id"], {"awaiting_approval", "failed"})
    assert first not in {r["intervention_id"] for r in replanned["ranking"]}

    response = _decide(client, replanned, first)
    assert response.status_code == 409
    current = replanned["recommendation"]["intervention_id"]
    assert response.json()["detail"] == (f"{first} is no longer in the current ranking "
                                         f"(current recommendation: {current})")
    unchanged = client.get(f"/api/investigations/{investigation['id']}").json()
    assert unchanged["stage"] == "awaiting_approval" and unchanged["attempts"] == 1


def test_rejecting_an_intervention_no_longer_in_the_ranking_is_409(client):
    investigation = _awaiting(client)
    first = investigation["recommendation"]["intervention_id"]
    _decide(client, investigation, first, "rejected", "change freeze")
    replanned = _wait(client, investigation["id"], {"awaiting_approval", "failed"})
    assert _decide(client, replanned, first, "rejected", "again").status_code == 409


def test_a_ranked_intervention_other_than_the_recommendation_can_be_approved(client):
    # Deliberate: docs/DEMO.md's replanning stretch has the operator approve a lower-ranked intervention.
    investigation = _awaiting(client)
    runner_up = investigation["ranking"][1]["intervention_id"]
    assert runner_up != investigation["recommendation"]["intervention_id"]
    assert _decide(client, investigation, runner_up).status_code == 200


def test_unknown_intervention_is_still_400(client):
    assert _decide(client, _awaiting(client), "I99").status_code == 400


# ---------------------------------------------------------------- the cap seen through the API


def test_after_the_cap_the_investigation_is_failed_and_refuses_decisions(client, verify_fails):
    investigation = _awaiting(client)
    for attempt in range(1, 4):
        current = _wait(client, investigation["id"], {"awaiting_approval", "failed"})
        assert current["stage"] == "awaiting_approval" and current["attempts"] == attempt - 1
        assert _decide(client, current, current["recommendation"]["intervention_id"]).status_code == 200
    failed = _wait(client, investigation["id"], {"failed"})
    assert failed["stage"] == "failed" and failed["attempts"] == 3
    assert failed["error"].startswith("Stopped after the maximum of 3 approval attempts without a verified fix")

    response = _decide(client, failed, failed["ranking"][0]["intervention_id"])
    assert response.status_code == 409
    assert client.get(f"/api/investigations/{investigation['id']}").json()["attempts"] == 3


# ---------------------------------------------------------------- existing paths still work


def test_approving_the_recommendation_still_resolves(client):
    investigation = _awaiting(client)
    assert _decide(client, investigation, investigation["recommendation"]["intervention_id"]).status_code == 200
    resolved = _wait(client, investigation["id"], {"resolved", "failed"})
    assert resolved["stage"] == "resolved" and resolved["attempts"] == 1 and resolved["error"] is None
    assert resolved["verification"]["passed"] is True


def test_rejecting_the_recommendation_still_replans(client):
    investigation = _awaiting(client)
    first = investigation["recommendation"]["intervention_id"]
    assert _decide(client, investigation, first, "rejected", "change freeze").status_code == 200
    replanned = _wait(client, investigation["id"], {"awaiting_approval", "failed"})
    assert replanned["stage"] == "awaiting_approval" and replanned["attempts"] == 1
    assert replanned["recommendation"]["intervention_id"] != first
