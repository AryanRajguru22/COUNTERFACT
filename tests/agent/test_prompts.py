"""H9: stage-specific prompts filled with real investigation state, unchanged replay keys, readable steps."""

import json

import pytest

from agent import orchestrator, tools
from agent.llm import RECORDINGS_DIR
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation

# Spelled out on purpose: renaming any of these would orphan the recorded replay narration.
REPLAY_KEYS = [
    "thought.timeline",
    "thought.hypotheses",
    "thought.evidence",
    "thought.testing",
    "thought.root_cause",
    "thought.counterfactual",
    "thought.recommendation",
]


@pytest.fixture
def calls(monkeypatch):
    """Replace the LLM client with a silent spy that records every (key, messages) it is asked for."""
    captured: list[tuple[str, list[dict[str, str]]]] = []

    class SpyLLM:
        fallback_reason = None

        def __init__(self, incident_id, mode=None):
            pass

        def complete(self, key, messages=None):
            captured.append((key, messages))
            return ""

    monkeypatch.setattr(orchestrator, "LLMClient", SpyLLM)
    return captured


def _run() -> tuple[InvestigationStore, Investigation]:
    store = InvestigationStore()
    store.put(Investigation(id="inv-h9", incident=tools.get_incident("INC-2041")))
    orchestrator.run("inv-h9", store)
    return store, store.get("inv-h9")


def _prompts(calls) -> dict[str, str]:
    return {key: messages[-1]["content"] for key, messages in calls}


def _recordings() -> dict[str, str]:
    return json.loads((RECORDINGS_DIR / "INC-2041.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- replay keys


def test_replay_keys_templates_and_recordings_line_up(calls):
    _run()
    assert [key for key, _ in calls] == REPLAY_KEYS
    assert list(_recordings()) == REPLAY_KEYS
    assert sorted(p.stem for p in orchestrator.PROMPTS_DIR.glob("thought.*.md")) == sorted(REPLAY_KEYS)


def test_replay_narration_is_the_recorded_text():
    _, investigation = _run()
    recordings = _recordings()
    assert [s.output_summary for s in investigation.steps if s.kind == "thought"] == [recordings[k] for k in REPLAY_KEYS]


# ---------------------------------------------------------------- prompt content


def test_prompts_carry_real_investigation_state(calls):
    _, inv = _run()
    prompts = _prompts(calls)
    timeline = tools.call("build_timeline", incident_id="INC-2041")
    changes = [e for e in timeline if e.state_change]

    assert inv.incident.title in prompts["thought.timeline"]
    assert f"{len(timeline)} events and {len(changes)} state changes" in prompts["thought.hypotheses"]
    assert all(e.id in prompts["thought.hypotheses"] for e in changes)
    for key in ("thought.evidence", "thought.testing"):
        assert all(f"{h.id} {h.title}" in prompts[key] for h in inv.hypotheses), key
    rejected = [h.id for h in inv.hypotheses if h.status == "rejected"]
    assert f"Rejected hypotheses: {', '.join(rejected)}." in prompts["thought.root_cause"]
    assert inv.root_cause.statement in prompts["thought.counterfactual"]
    recommended = next(i for i in inv.interventions if i.id == inv.recommendation.intervention_id)
    assert f"Recommended: {recommended.id} {recommended.title}" in prompts["thought.recommendation"]
    assert f"for {inv.simulations[0].breach_minutes} minutes" in prompts["thought.recommendation"]
    assert "Replanning context: none, this is the first recommendation." in prompts["thought.recommendation"]


def test_every_prompt_has_the_system_message_and_no_gaps(calls):
    _run()
    system = (orchestrator.PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()
    for key, messages in calls:
        assert [m["role"] for m in messages] == ["system", "user"], key
        assert messages[0]["content"] == system, key
        user = messages[1]["content"]
        assert "unknown" not in user and "{" not in user and "}" not in user, key


def test_missing_placeholder_renders_unknown_instead_of_raising():
    assert orchestrator.fill_prompt("{present} and {absent}", {"present": "here"}) == "here and unknown"
    for key in REPLAY_KEYS:  # every real template survives an empty investigation
        assert "unknown" in orchestrator.fill_prompt(orchestrator.load_template(key), {})


def test_replan_prompt_explains_the_rejection(calls):
    store, inv = _run()
    first = inv.recommendation.intervention_id
    orchestrator.resume_after_approval(inv.id, Approval(intervention_id=first, decision="rejected",
                                                        approver="sre-lead", note="change freeze"), store)
    key, messages = calls[-1]
    assert key == "thought.recommendation"
    prompt = messages[-1]["content"]
    assert f"Replanning context: sre-lead rejected {first}" in prompt and "change freeze" in prompt
    assert f"Recommended: {store.get(inv.id).recommendation.intervention_id} " in prompt


def test_replan_prompt_explains_a_failed_verification(calls):
    store, inv = _run()
    failing = next((s.intervention_ids[0] for s in inv.simulations[1:] if not s.prevented), None)
    if failing is None:
        pytest.skip("every intervention prevents the breach, so none can fail verification")
    orchestrator.resume_after_approval(inv.id, Approval(intervention_id=failing, decision="approved",
                                                        approver="sre-lead"), store)
    assert store.get(inv.id).verification.passed is False
    key, messages = calls[-1]
    assert key == "thought.recommendation"
    assert f"Replanning context: {failing} " in messages[-1]["content"]
    assert "failed verification" in messages[-1]["content"]


# ---------------------------------------------------------------- readable agent steps


def test_agent_steps_are_readable(calls):
    _, inv = _run()
    steps = inv.steps
    assert not [s.output_summary for s in steps if s.output_summary.startswith("Calling ")]
    # The contract shape is untouched: tool names on every tool step, scalar-only inputs.
    assert all(s.tool for s in steps if s.kind in ("tool_call", "tool_result"))
    assert all(isinstance(v, (str, int, float, bool)) for s in steps if s.input for v in s.input.values())

    titles = [f"{h.id} {h.title}" for h in inv.hypotheses]
    gathered = [s.output_summary for s in steps if s.kind == "tool_result" and s.tool == "gather_evidence"]
    tested = [s.output_summary for s in steps if s.kind == "tool_result" and s.tool == "test_hypothesis"]
    assert [g.startswith(f"{t}:") for g, t in zip(gathered, titles)] == [True] * len(titles)
    assert [t2.startswith(f"{t}:") for t2, t in zip(tested, titles)] == [True] * len(titles)

    simulated = [s.output_summary for s in steps if s.kind == "tool_call" and s.tool == "simulate"]
    assert simulated == ["Simulating the baseline (no intervention)"] + [
        f"Simulating {i.id} {i.title}" for i in inv.interventions]

    [ranked] = [s for s in steps if s.kind == "tool_result" and s.tool == "rank"]
    assert all(f"{r.rank}. {r.intervention_id} " in ranked.output_summary for r in inv.ranking)

    recommended = next(i for i in inv.interventions if i.id == inv.recommendation.intervention_id)
    assert steps[-1].kind == "decision"
    assert steps[-1].output_summary.startswith(f"Recommend {recommended.id} {recommended.title}: ")
