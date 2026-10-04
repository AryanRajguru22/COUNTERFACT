"""H15: a rejection or failed verification replans to a new recommendation, attempts are capped at 3, and an
exhausted or empty replan stops in `failed` with a clear error instead of waiting for an approval forever.

Verification, replan and rank outcomes are forced through tools.TOOLS (restored by monkeypatch), so these tests
do not depend on the simulator's current catalogue or canned results.
"""

import pytest

from agent import orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation, VerificationCheck, VerificationResult

ID = "inv-h15"


def _verification(execution, passed: bool) -> VerificationResult:
    check = VerificationCheck(name="breach minutes", expected="<= 0", observed="0" if passed else "9", passed=passed)
    return VerificationResult(intervention_id=execution.intervention_id, passed=passed, checks=[check],
                              stress_test_passed=passed)


@pytest.fixture
def verify_fails(monkeypatch):
    monkeypatch.setitem(tools.TOOLS, "verify", lambda execution, model, seed: _verification(execution, False))


def _run() -> InvestigationStore:
    store = InvestigationStore()
    store.put(Investigation(id=ID, incident=tools.get_incident("INC-2041")))
    orchestrator.run(ID, store)
    assert store.get(ID).stage == "awaiting_approval", store.get(ID).error
    return store


def _decide(store: InvestigationStore, decision: str = "approved", note: str = "") -> Investigation:
    """Decide on the current recommendation, as the UI does."""
    recommended = store.get(ID).recommendation.intervention_id
    orchestrator.resume_after_approval(ID, Approval(intervention_id=recommended, decision=decision,
                                                    approver="sre-lead", note=note), store)
    return store.get(ID)


def _replan_calls(inv: Investigation) -> int:
    return sum(s.kind == "tool_call" and s.tool == "replan" for s in inv.steps)


# ---------------------------------------------------------------- the loop


def test_failed_verification_replans_to_a_new_recommendation(verify_fails):
    store = _run()
    first = store.get(ID).recommendation.intervention_id
    inv = _decide(store)
    assert inv.stage == "awaiting_approval", inv.error
    assert inv.attempts == 1
    assert inv.verification.passed is False
    assert inv.recommendation.intervention_id != first
    assert first not in {r.intervention_id for r in inv.ranking}
    stages = list(dict.fromkeys(s.stage for s in inv.steps))
    assert stages[-3:] == ["executing", "verifying", "replanning"]
    assert _replan_calls(inv) == 1


def test_every_approval_decision_counts_as_an_attempt(verify_fails):
    store = _run()
    assert _decide(store).attempts == 1  # approve, verification fails
    assert _decide(store, "rejected", "change freeze").attempts == 2  # reject
    assert store.get(ID).stage == "awaiting_approval"


# ---------------------------------------------------------------- the cap


def test_third_failed_verification_stops_in_failed_with_a_clear_error(verify_fails):
    store = _run()
    assert [_decide(store).stage for _ in range(2)] == ["awaiting_approval", "awaiting_approval"]
    last = store.get(ID).recommendation.intervention_id
    inv = _decide(store)
    assert inv.stage == "failed"
    assert inv.attempts == orchestrator.MAX_ATTEMPTS == 3
    assert inv.error.startswith("Stopped after the maximum of 3 approval attempts without a verified fix (last: "
                                f"{last} ")
    assert "failed verification" in inv.error
    assert inv.steps[-1].kind == "decision" and inv.steps[-1].output_summary == inv.error
    assert _replan_calls(inv) == 2  # no pointless replan once no further approval is allowed


def test_rejections_count_towards_the_cap():
    store = _run()
    for _ in range(2):
        assert _decide(store, "rejected", "change freeze").stage == "awaiting_approval"
    last = store.get(ID).recommendation.intervention_id
    inv = _decide(store, "rejected", "still frozen")
    assert inv.stage == "failed" and inv.attempts == 3
    assert f"(last: sre-lead rejected {last} " in inv.error and inv.error.endswith("still frozen)")


def test_a_verified_fix_on_the_last_attempt_still_resolves(monkeypatch):
    outcomes = iter([False, False, True])
    monkeypatch.setitem(tools.TOOLS, "verify",
                        lambda execution, model, seed: _verification(execution, next(outcomes)))
    store = _run()
    _decide(store), _decide(store)
    inv = _decide(store)
    assert inv.stage == "resolved" and inv.attempts == 3 and inv.error is None


# ---------------------------------------------------------------- nothing left to recommend


@pytest.mark.parametrize("decision, note, why", [("approved", "", "failed verification"),
                                                 ("rejected", "change freeze", "rejected")])
def test_empty_replan_fails_instead_of_awaiting_approval(monkeypatch, verify_fails, decision, note, why):
    monkeypatch.setitem(tools.TOOLS, "replan", lambda failed, ranking, model: [])
    store = _run()
    first = store.get(ID).recommendation.intervention_id
    inv = _decide(store, decision, note)
    assert inv.stage == "failed"
    assert inv.recommendation is None and inv.ranking == []
    assert inv.error.startswith("No intervention left to recommend after 1 approval attempt (last: ")
    assert first in inv.error and why in inv.error


def test_empty_initial_ranking_fails_instead_of_awaiting_approval(monkeypatch):
    monkeypatch.setitem(tools.TOOLS, "rank", lambda results, interventions: [])
    store = InvestigationStore()
    store.put(Investigation(id=ID, incident=tools.get_incident("INC-2041")))
    orchestrator.run(ID, store)
    inv = store.get(ID)
    assert inv.stage == "failed" and inv.recommendation is None
    assert inv.error == "No intervention to recommend: the ranking returned no candidates"
