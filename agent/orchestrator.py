"""Investigation state machine. Owner: Rohit.

created -> timeline -> hypotheses -> evidence -> testing -> root_cause
        -> counterfactual -> awaiting_approval
approval -> executing -> verifying -> resolved | replanning -> awaiting_approval
rejection -> replanning -> awaiting_approval

The LLM only narrates (thought steps); every decision comes from the engines
via agent/tools.py. The orchestrator works on its own copy of the
Investigation and publishes snapshots to the store after every step.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Protocol

from agent import tools
from agent.llm import LLMClient
from contracts.models import AgentStep, Approval, Investigation, Stage, VerificationCheck, VerificationResult


class Store(Protocol):
    def get(self, investigation_id: str) -> Investigation | None: ...
    def put(self, investigation: Investigation) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Run:
    def __init__(self, investigation_id: str, store: Store):
        current = store.get(investigation_id)
        if current is None:
            raise KeyError(f"unknown investigation: {investigation_id}")
        self.inv = current.model_copy(deep=True)
        self.store = store
        # The persisted Investigation.mode is authoritative, so resume runs in the mode the investigation started in.
        self.llm = LLMClient(self.inv.incident.id, self.inv.mode)
        self.delay_s = int(os.environ.get("STEP_DELAY_MS", "600")) / 1000

    def publish(self, pause: bool = True) -> None:
        self.store.put(self.inv)
        if pause and self.delay_s:
            time.sleep(self.delay_s)

    def stage(self, stage: Stage) -> None:
        self.inv.stage = stage
        self.publish()

    def step(self, kind: str, summary: str, tool: str | None = None, input: dict[str, Any] | None = None) -> None:
        self.inv.steps.append(AgentStep(n=len(self.inv.steps) + 1, stage=self.inv.stage, kind=kind, tool=tool,
                                        input=input, output_summary=summary, at=_now()))
        self.publish(pause=kind != "tool_call")

    def think(self, key: str) -> None:
        prompt = [{"role": "user", "content":
                   f"You are investigating incident {self.inv.incident.id} ({self.inv.incident.title}). "
                   f"In two sentences, narrate your reasoning for the '{self.inv.stage}' stage."}]
        text = self.llm.complete(f"thought.{key}", prompt)
        if text:
            self.step("thought", text)

    def tool(self, name: str, *args, **kwargs):
        # Only scalar arguments are recorded; models and lists would bloat every poll.
        scalars = {k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))}
        self.step("tool_call", f"Calling {name}", tool=name, input=scalars or None)
        return tools.call(name, *args, **kwargs)

    def fail(self, error: Exception) -> None:
        self.inv.error = f"{type(error).__name__}: {error}"
        self.inv.stage = "failed"
        self.store.put(self.inv)


def run(investigation_id: str, store: Store, mode: str | None = None) -> None:
    # `mode` is kept only for signature compatibility; Investigation.mode is the source of truth.
    r = _Run(investigation_id, store)
    try:
        _investigate(r)
    except Exception as error:  # surface any engine failure in the UI instead of hanging
        r.fail(error)


def _investigate(r: _Run) -> None:
    inv = r.inv
    incident_id = inv.incident.id

    r.stage("timeline")
    r.think("timeline")
    inv.timeline = r.tool("build_timeline", incident_id=incident_id)
    changes = sum(1 for e in inv.timeline if e.state_change)
    r.step("tool_result", f"{len(inv.timeline)} events, {changes} state changes", tool="build_timeline")

    r.stage("hypotheses")
    r.think("hypotheses")
    inv.hypotheses = r.tool("seed_hypotheses", incident_id=incident_id, timeline=inv.timeline)
    r.step("tool_result", ", ".join(f"{h.id} {h.title}" for h in inv.hypotheses), tool="seed_hypotheses")

    r.stage("evidence")
    r.think("evidence")
    seen: dict[str, Any] = {}
    for h in inv.hypotheses:
        items = r.tool("gather_evidence", incident_id=incident_id, hypothesis=h)
        for e in items:
            seen.setdefault(e.id, e)
        inv.evidence = list(seen.values())
        r.step("tool_result", f"{h.id}: {len(items)} evidence items", tool="gather_evidence")

    r.stage("testing")
    r.think("testing")
    tested = []
    for h in inv.hypotheses:
        relevant = [e for e in inv.evidence if h.id in e.stance]
        result = r.tool("test_hypothesis", hypothesis=h, evidence=relevant)
        tested.append(result)
        verdict = f"rejected: {result.rejection_reason}" if result.status == "rejected" else result.status
        r.step("tool_result", f"{h.id} {verdict} (confidence {result.confidence})", tool="test_hypothesis")
    inv.hypotheses = tested

    r.stage("root_cause")
    r.think("root_cause")
    inv.root_cause = r.tool("determine_root_cause", hypotheses=inv.hypotheses, evidence=inv.evidence,
                            timeline=inv.timeline)
    inv.hypotheses = [h.model_copy(update={"status": "confirmed"}) if h.id == inv.root_cause.hypothesis_id else h
                      for h in inv.hypotheses]
    r.step("decision", f"Root cause {inv.root_cause.hypothesis_id}: {inv.root_cause.statement}",
           tool="determine_root_cause")

    r.stage("counterfactual")
    r.think("counterfactual")
    model = r.tool("load_system_model", incident_id=incident_id)
    inv.interventions = r.tool("generate_interventions", root_cause=inv.root_cause, model=model)
    inv.simulations = [r.tool("simulate", model=model, interventions=[], seed=0)]
    for intervention in inv.interventions:
        inv.simulations.append(r.tool("simulate", model=model, interventions=[intervention], seed=0))
    r.step("tool_result", f"Baseline: {inv.simulations[0].breach_minutes} breach minutes; "
           f"{sum(s.prevented for s in inv.simulations[1:])}/{len(inv.interventions)} interventions prevent it",
           tool="simulate")
    inv.ranking = r.tool("rank", results=inv.simulations, interventions=inv.interventions)
    _recommend(r)


def _recommend(r: _Run) -> None:
    inv = r.inv
    inv.recommendation = inv.ranking[0] if inv.ranking else None
    r.think("recommendation")
    if inv.recommendation:
        r.step("decision", f"Recommend {inv.recommendation.intervention_id} (rank 1, score {inv.recommendation.score})")
    else:
        r.step("decision", "No interventions left to recommend")
    r.stage("awaiting_approval")


def resume_after_approval(investigation_id: str, approval: Approval, store: Store, mode: str | None = None) -> None:
    # `mode` is kept only for signature compatibility; Investigation.mode is the source of truth.
    r = _Run(investigation_id, store)
    try:
        _act_on_approval(r, approval)
    except Exception as error:
        r.fail(error)


def _act_on_approval(r: _Run, approval: Approval) -> None:
    inv = r.inv
    inv.approval = approval
    inv.attempts += 1
    model = r.tool("load_system_model", incident_id=inv.incident.id)

    if approval.decision == "rejected":
        r.stage("replanning")
        r.step("decision", f"{approval.approver} rejected {approval.intervention_id}: {approval.note or 'no note'}")
        rejected = VerificationResult(
            intervention_id=approval.intervention_id, passed=False, stress_test_passed=False,
            checks=[VerificationCheck(name="human approval", expected="approved", observed="rejected", passed=False)],
        )
        inv.ranking = r.tool("replan", failed=rejected, ranking=inv.ranking, model=model)
        _recommend(r)
        return

    r.stage("executing")
    intervention = r.tool("get_intervention", intervention_id=approval.intervention_id)
    inv.execution = r.tool("execute", intervention=intervention, model=model)
    r.step("tool_result", f"{intervention.id} {inv.execution.status} in the simulated environment", tool="execute")

    r.stage("verifying")
    inv.verification = r.tool("verify", execution=inv.execution, model=model, seed=0)
    r.step("tool_result", f"Verification {'passed' if inv.verification.passed else 'failed'}", tool="verify")

    if inv.verification.passed:
        r.stage("resolved")
        return
    r.stage("replanning")
    inv.ranking = r.tool("replan", failed=inv.verification, ranking=inv.ranking, model=model)
    _recommend(r)
