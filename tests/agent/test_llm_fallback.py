"""H6: a live investigation whose LLM is unavailable falls back to replay instead of failing."""

import pytest

from agent import orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation


@pytest.fixture(autouse=True)
def _no_live_config(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)


def _run(mode: str) -> tuple[InvestigationStore, str]:
    store = InvestigationStore()
    store.put(Investigation(id=f"inv-{mode}", incident=tools.get_incident("INC-2041"), mode=mode))
    orchestrator.run(f"inv-{mode}", store)
    return store, f"inv-{mode}"


def _fallback_steps(investigation: Investigation):
    return [s for s in investigation.steps
            if s.kind == "decision" and s.output_summary.startswith("Live LLM unavailable")]


def _thoughts(investigation: Investigation) -> list[str]:
    return [s.output_summary for s in investigation.steps if s.kind == "thought"]


def test_live_without_config_completes_on_replay():
    store, investigation_id = _run("live")
    investigation = store.get(investigation_id)
    assert investigation.stage == "awaiting_approval", investigation.error
    assert investigation.error is None
    assert investigation.mode == "live"
    [fallback] = _fallback_steps(investigation)
    assert fallback.stage == "timeline"
    assert "LLM_BASE_URL" in fallback.output_summary
    # Narration comes from the recordings, exactly as in a replay investigation.
    replay_store, replay_id = _run("replay")
    assert _thoughts(investigation) == _thoughts(replay_store.get(replay_id))
    assert _fallback_steps(replay_store.get(replay_id)) == []


def test_live_fallback_approve_resolves():
    store, investigation_id = _run("live")
    recommended = store.get(investigation_id).recommendation.intervention_id
    approval = Approval(intervention_id=recommended, decision="approved", approver="test")
    orchestrator.resume_after_approval(investigation_id, approval, store)
    investigation = store.get(investigation_id)
    assert investigation.stage == "resolved", investigation.error
    assert investigation.verification.passed is True
    assert investigation.mode == "live"


def test_live_fallback_reject_replans_on_a_fresh_client():
    store, investigation_id = _run("live")
    first = store.get(investigation_id).recommendation.intervention_id
    approval = Approval(intervention_id=first, decision="rejected", approver="test", note="too risky")
    orchestrator.resume_after_approval(investigation_id, approval, store)
    investigation = store.get(investigation_id)
    assert investigation.stage == "awaiting_approval", investigation.error
    assert investigation.recommendation.intervention_id != first
    assert investigation.mode == "live"
    # The resume run builds a new client, which tries live once and falls back again.
    assert [s.stage for s in _fallback_steps(investigation)] == ["timeline", "replanning"]
