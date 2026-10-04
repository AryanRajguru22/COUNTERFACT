"""H5: the orchestrator takes its LLM mode from the persisted Investigation.mode."""

import pytest

from agent import orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation


@pytest.fixture
def llm_modes(monkeypatch):
    """Replace the LLM client with a silent fake that records the mode it was built with."""
    modes: list[str | None] = []

    class FakeLLM:
        fallback_reason = None

        def __init__(self, incident_id, mode=None):
            modes.append(mode)

        def complete(self, key, messages=None):
            return ""

    monkeypatch.setattr(orchestrator, "LLMClient", FakeLLM)
    return modes


def _store_with(mode: str) -> tuple[InvestigationStore, str]:
    store = InvestigationStore()
    store.put(Investigation(id="inv-test", incident=tools.get_incident("INC-2041"), mode=mode))
    return store, "inv-test"


@pytest.mark.parametrize("mode", ["replay", "live"])
def test_run_uses_persisted_mode(llm_modes, mode):
    store, investigation_id = _store_with(mode)
    orchestrator.run(investigation_id, store)
    assert llm_modes == [mode]
    assert store.get(investigation_id).stage == "awaiting_approval"
    assert store.get(investigation_id).mode == mode


@pytest.mark.parametrize("persisted, env", [("replay", "live"), ("live", "replay")])
def test_resume_uses_persisted_mode_not_env(llm_modes, monkeypatch, persisted, env):
    monkeypatch.setenv("LLM_MODE", env)
    store, investigation_id = _store_with(persisted)
    orchestrator.run(investigation_id, store)
    recommended = store.get(investigation_id).recommendation.intervention_id
    approval = Approval(intervention_id=recommended, decision="approved", approver="test")
    orchestrator.resume_after_approval(investigation_id, approval, store)
    assert llm_modes == [persisted, persisted]
    assert store.get(investigation_id).stage == "resolved"
    assert store.get(investigation_id).mode == persisted


def test_mode_argument_does_not_override_persisted_mode(llm_modes):
    store, investigation_id = _store_with("replay")
    orchestrator.run(investigation_id, store, mode="live")
    assert llm_modes == ["replay"]
    assert store.get(investigation_id).mode == "replay"
