"""H12 hardening at the API boundary: approval rules, double approval, health and engine failures."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import BackgroundTasks, HTTPException

from agent import llm, orchestrator, tools
from backend import routes
from contracts.models import Approval


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


def _approval_url(investigation: dict) -> str:
    return f"/api/investigations/{investigation['id']}/approval"


# ---------------------------------------------------------------- rejection needs a note


@pytest.mark.parametrize("extra", [{}, {"note": ""}, {"note": "   "}], ids=["missing", "empty", "blank"])
def test_rejection_without_a_note_is_refused(client, extra):
    investigation = _awaiting(client)
    body = {"intervention_id": investigation["recommendation"]["intervention_id"], "decision": "rejected",
            "approver": "sre-lead", **extra}
    response = client.post(_approval_url(investigation), json=body)
    assert response.status_code == 422
    assert "note" in response.json()["detail"]
    unchanged = client.get(f"/api/investigations/{investigation['id']}").json()
    assert unchanged["stage"] == "awaiting_approval" and unchanged["approval"] is None


def test_rejection_with_a_note_replans(client):
    investigation = _awaiting(client)
    first = investigation["recommendation"]["intervention_id"]
    response = client.post(_approval_url(investigation), json={
        "intervention_id": first, "decision": "rejected", "approver": "sre-lead", "note": "change freeze"})
    assert response.status_code == 200
    replanned = _wait(client, investigation["id"], {"awaiting_approval", "failed"})
    assert replanned["recommendation"]["intervention_id"] != first
    assert replanned["approval"]["note"] == "change freeze"


def test_approval_still_needs_no_note(client):
    investigation = _awaiting(client)
    response = client.post(_approval_url(investigation), json={
        "intervention_id": investigation["recommendation"]["intervention_id"], "decision": "approved",
        "approver": "sre-lead"})
    assert response.status_code == 200
    assert _wait(client, investigation["id"], {"resolved", "failed"})["stage"] == "resolved"


# ---------------------------------------------------------------- double approval


def test_second_approval_while_the_first_is_in_flight_is_409(client, monkeypatch):
    resumed = []
    # Hold the first approval "in flight": the resume never runs, so the investigation stays executing.
    monkeypatch.setattr(orchestrator, "resume_after_approval", lambda *args, **kwargs: resumed.append(args))
    investigation = _awaiting(client)
    recommended = investigation["recommendation"]["intervention_id"]

    first = client.post(_approval_url(investigation), json={
        "intervention_id": recommended, "decision": "approved", "approver": "first"})
    assert first.status_code == 200 and first.json()["stage"] == "executing"
    assert client.get(f"/api/investigations/{investigation['id']}").json()["stage"] == "executing"

    for body in ({"intervention_id": recommended, "decision": "approved", "approver": "second"},
                 {"intervention_id": recommended, "decision": "rejected", "approver": "second", "note": "no"}):
        assert client.post(_approval_url(investigation), json=body).status_code == 409
    assert len(resumed) == 1
    assert client.get(f"/api/investigations/{investigation['id']}").json()["approval"]["approver"] == "first"


def test_concurrent_approvals_cannot_both_be_accepted(client, monkeypatch):
    investigation = _awaiting(client)
    recommended = investigation["recommendation"]["intervention_id"]
    # Force the race: both submissions read the investigation while it is still awaiting_approval.
    barrier = threading.Barrier(2, timeout=5)
    original_get = routes.store.get

    def racing_get(investigation_id):
        current = original_get(investigation_id)
        barrier.wait()
        return current

    monkeypatch.setattr(routes.store, "get", racing_get)

    def submit(approver: str):
        approval = Approval(intervention_id=recommended, decision="approved", approver=approver)
        try:  # BackgroundTasks is never run here, so the resume stays pending, like a real in-flight approval
            return routes.submit_approval(investigation["id"], approval, BackgroundTasks()).approval.approver
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ["first", "second"]))

    assert outcomes.count(409) == 1  # exactly one submission was refused...
    [winner] = [o for o in outcomes if o != 409]
    stored = original_get(investigation["id"])
    assert stored.stage == "executing" and stored.approval.approver == winner  # ...and only the winner was stored


# ---------------------------------------------------------------- health


def test_health_does_not_depend_on_the_live_llm(client, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert client.get("/api/health").json() == {"ok": True, "llm_mode": "live"}


def _raise(error):
    def fail(*args, **kwargs):
        raise error
    return fail


@pytest.mark.parametrize("breakage", ["incident", "no_incidents", "system_model", "recording"])
def test_health_fails_when_fixtures_cannot_load(client, monkeypatch, tmp_path, breakage):
    if breakage == "incident":
        monkeypatch.setattr(tools, "list_incidents", _raise(FileNotFoundError("incident.json missing")))
    elif breakage == "no_incidents":
        monkeypatch.setattr(tools, "list_incidents", lambda: [])
    elif breakage == "system_model":
        monkeypatch.setitem(tools.TOOLS, "load_system_model", _raise(ValueError("system_model.json invalid")))
    else:
        (tmp_path / "INC-2041.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(llm, "RECORDINGS_DIR", tmp_path)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"].startswith("fixtures failed to load: ")


# ---------------------------------------------------------------- engine failures


@pytest.mark.parametrize("engine", ["build_timeline", "simulate"])
def test_engine_exception_during_investigation_fails_with_a_clear_error(client, monkeypatch, engine):
    monkeypatch.setitem(tools.TOOLS, engine, _raise(RuntimeError(f"{engine} engine exploded")))
    response = client.post("/api/investigations", json={"incident_id": "INC-2041"})
    investigation = _wait(client, response.json()["investigation_id"], {"failed", "awaiting_approval"})
    assert investigation["stage"] == "failed"
    assert investigation["error"] == f"RuntimeError: {engine} engine exploded"


def test_engine_exception_after_approval_fails_with_a_clear_error(client, monkeypatch):
    investigation = _awaiting(client)
    monkeypatch.setitem(tools.TOOLS, "execute", _raise(RuntimeError("executor unavailable")))
    client.post(_approval_url(investigation), json={
        "intervention_id": investigation["recommendation"]["intervention_id"], "decision": "approved",
        "approver": "sre-lead"})
    failed = _wait(client, investigation["id"], {"failed", "resolved"})
    assert failed["stage"] == "failed"
    assert failed["error"] == "RuntimeError: executor unavailable"
