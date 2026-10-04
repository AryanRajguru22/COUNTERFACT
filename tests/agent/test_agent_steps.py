"""H12 hardening: every tool call is immediately followed by a readable tool_result, and the agent's
decisions (hypothesis rejections, root cause, recommendation) are explicit decision steps."""

import pytest

from agent import orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import AgentStep, Approval, Investigation


def _run() -> tuple[InvestigationStore, Investigation]:
    store = InvestigationStore()
    store.put(Investigation(id="inv-steps", incident=tools.get_incident("INC-2041")))
    orchestrator.run("inv-steps", store)
    return store, store.get("inv-steps")


def _flow(name: str) -> Investigation:
    """Investigation plus one approval round; together the three flows exercise every tool."""
    store, inv = _run()
    if name == "approve":
        approval = Approval(intervention_id=inv.recommendation.intervention_id, decision="approved", approver="sre")
    elif name == "reject":
        approval = Approval(intervention_id=inv.recommendation.intervention_id, decision="rejected", approver="sre",
                            note="change freeze")
    else:  # approve an intervention that does not prevent the breach, so verification fails and replans
        failing = next(s.intervention_ids[0] for s in inv.simulations[1:] if not s.prevented)
        approval = Approval(intervention_id=failing, decision="approved", approver="sre")
    orchestrator.resume_after_approval(inv.id, approval, store)
    return store.get(inv.id)


def _shape(steps: list[AgentStep]) -> list[tuple]:
    return [(s.stage, s.kind, s.tool, s.input, s.output_summary) for s in steps]


FLOWS = ["approve", "reject", "failed_verification"]


@pytest.mark.parametrize("flow", FLOWS)
def test_every_tool_call_is_immediately_followed_by_its_result(flow):
    inv = _flow(flow)
    assert inv.stage in ("resolved", "awaiting_approval"), inv.error
    steps = inv.steps
    for i, call in enumerate(steps):
        if call.kind != "tool_call":
            continue
        result = steps[i + 1] if i + 1 < len(steps) else None
        assert result is not None and result.kind == "tool_result" and result.tool == call.tool, (i, call.tool)
        assert result.output_summary.strip() and not result.output_summary.startswith("Calling "), call.tool


def test_the_flows_exercise_every_tool():
    called = {s.tool for flow in FLOWS for s in _flow(flow).steps if s.kind == "tool_call"}
    assert called == set(tools.TOOLS)


def test_hypothesis_rejections_are_decision_steps():
    _, inv = _run()
    steps = inv.steps
    rejected = [h for h in inv.hypotheses if h.status == "rejected"]
    assert rejected
    decisions = [s for s in steps if s.kind == "decision" and s.tool == "test_hypothesis"]
    expected = [f"Rejected {h.id} {h.title}: {h.rejection_reason}" for h in rejected]
    assert [d.output_summary for d in decisions] == expected
    for d in decisions:  # each rejection decision comes right after that hypothesis's readable result
        i = steps.index(d)
        assert d.stage == "testing" and steps[i - 1].kind == "tool_result" and steps[i - 1].tool == "test_hypothesis"
    # the readable test results are all still there, one per hypothesis
    assert len([s for s in steps if s.kind == "tool_result" and s.tool == "test_hypothesis"]) == len(inv.hypotheses)


def test_root_cause_and_recommendation_are_decision_steps():
    _, inv = _run()
    steps = inv.steps
    [root] = [s for s in steps if s.kind == "decision" and s.tool == "determine_root_cause"]
    assert root.stage == "root_cause" and root.output_summary.startswith(f"Root cause {inv.root_cause.hypothesis_id} ")
    assert steps[steps.index(root) - 1].kind == "tool_result"
    title = next(i.title for i in inv.interventions if i.id == inv.recommendation.intervention_id)
    [recommend] = [s for s in steps if s.kind == "decision" and s.output_summary.startswith("Recommend ")]
    assert recommend.output_summary.startswith(f"Recommend {inv.recommendation.intervention_id} {title}: ")
    assert steps[-1] == recommend


def test_steps_are_deterministic_across_runs():
    assert _shape(_run()[1].steps) == _shape(_run()[1].steps)
