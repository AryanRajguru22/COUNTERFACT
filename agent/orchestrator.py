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

import functools
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from agent import tools
from agent.llm import LLMClient
from contracts.models import (
    AgentStep,
    Approval,
    Hypothesis,
    Investigation,
    RankedIntervention,
    Stage,
    VerificationCheck,
    VerificationResult,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Store(Protocol):
    def get(self, investigation_id: str) -> Investigation | None: ...
    def put(self, investigation: Investigation) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- prompts


@functools.lru_cache(maxsize=None)
def load_template(name: str) -> str:
    """agent/prompts/<name>.md. Thought templates are named after their replay key (thought.<stage>)."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


class _Facts(dict):
    def __missing__(self, key: str) -> str:
        return "unknown"  # a template slip degrades the prompt instead of failing the investigation


def fill_prompt(template: str, facts: dict[str, Any]) -> str:
    return template.format_map(_Facts(facts))


def _lines(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- none"


def _hypothesis_title(inv: Investigation, hypothesis_id: str) -> str:
    return next((h.title for h in inv.hypotheses if h.id == hypothesis_id), "(unlisted hypothesis)")


def _intervention_title(inv: Investigation, intervention_id: str) -> str:
    return next((i.title for i in inv.interventions if i.id == intervention_id), "(unlisted intervention)")


def _verdict(h: Hypothesis) -> str:
    verdict = f"{h.id} {h.title}: {h.status} (confidence {h.confidence})"
    return f"{verdict}. {h.rejection_reason}" if h.status == "rejected" and h.rejection_reason else verdict


def _ranked(inv: Investigation, r: RankedIntervention) -> str:
    outcome = "prevents" if r.prevented else "does not prevent"
    return f"{r.rank}. {r.intervention_id} {_intervention_title(inv, r.intervention_id)} " \
           f"(score {r.score}, {outcome} the breach)"


def _replan_context(inv: Investigation) -> str:
    if inv.stage != "replanning":
        return "none, this is the first recommendation"
    approval = inv.approval
    if approval and approval.decision == "rejected":
        title = _intervention_title(inv, approval.intervention_id)
        return f"{approval.approver} rejected {approval.intervention_id} {title}: {approval.note or 'no note given'}"
    if inv.verification and not inv.verification.passed:
        failed = ", ".join(c.name for c in inv.verification.checks if not c.passed) or "stress test"
        title = _intervention_title(inv, inv.verification.intervention_id)
        return f"{inv.verification.intervention_id} {title} was executed but failed verification ({failed})"
    return "replanning after the previous recommendation"


def _facts(inv: Investigation) -> dict[str, Any]:
    """Real investigation state for the templates. Only what earlier stages produced is present."""
    incident = inv.incident
    facts: dict[str, Any] = {
        "incident_id": incident.id,
        "incident_title": incident.title,
        "service": incident.service,
        "severity": incident.severity,
        "incident_summary": incident.summary,
        "window_minutes": incident.window.minutes,
        "replan_context": _replan_context(inv),
    }
    if inv.timeline:
        changes = [e for e in inv.timeline if e.state_change]
        facts.update(event_count=len(inv.timeline), state_change_count=len(changes), state_changes=_lines(
            f"{e.id} at minute {e.t}: {e.state_change.param} {e.state_change.from_} → {e.state_change.to} "
            f"({e.summary})" for e in changes))
    if inv.hypotheses:
        facts.update(hypothesis_count=len(inv.hypotheses), hypotheses=_lines(f"{h.id} {h.title}" for h in inv.hypotheses))
    if inv.evidence:
        facts.update(evidence_count=len(inv.evidence), evidence_by_hypothesis=_lines(
            f"{h.id}: {sum(e.stance.get(h.id) == 'supports' for e in inv.evidence)} supporting, "
            f"{sum(e.stance.get(h.id) == 'refutes' for e in inv.evidence)} refuting" for h in inv.hypotheses))
    if any(h.status != "proposed" for h in inv.hypotheses):
        facts.update(test_results=_lines(_verdict(h) for h in inv.hypotheses),
                     rejected_hypotheses=", ".join(h.id for h in inv.hypotheses if h.status == "rejected") or "none")
    if rc := inv.root_cause:
        facts.update(root_cause_id=rc.hypothesis_id, root_cause_title=_hypothesis_title(inv, rc.hypothesis_id),
                     root_cause_statement=rc.statement, root_cause_confidence=rc.confidence,
                     causal_chain_length=len(rc.causal_chain),
                     causal_chain=_lines(f"{link.event_id}: {link.effect}" for link in rc.causal_chain))
    if inv.simulations:
        single = {s.intervention_ids[0]: s for s in inv.simulations if len(s.intervention_ids) == 1}
        outcomes = []
        for i in inv.interventions:
            sim = single.get(i.id)
            result = "not simulated" if sim is None else "prevents the breach" if sim.prevented else \
                f"does not prevent the breach ({sim.breach_minutes} breach minutes)"
            outcomes.append(f"{i.id} {i.title} [{i.category}, {i.risk} risk, {i.effort_hours}h effort]: {result}")
        facts.update(baseline_breach_minutes=inv.simulations[0].breach_minutes,
                     intervention_count=len(inv.interventions), intervention_outcomes=_lines(outcomes))
    if inv.ranking:
        facts["ranking"] = _lines(_ranked(inv, r) for r in inv.ranking)
    if rec := inv.recommendation:
        facts.update(recommendation_id=rec.intervention_id,
                     recommendation_title=_intervention_title(inv, rec.intervention_id),
                     recommendation_rank=rec.rank, recommendation_score=rec.score,
                     recommendation_prevents="yes" if rec.prevented else "no",
                     recommendation_breach_minutes_avoided=rec.breach_minutes_avoided,
                     recommendation_reasons="; ".join(rec.reasons) or "none given")
    return facts


class _Run:
    def __init__(self, investigation_id: str, store: Store):
        current = store.get(investigation_id)
        if current is None:
            raise KeyError(f"unknown investigation: {investigation_id}")
        self.inv = current.model_copy(deep=True)
        self.store = store
        # The persisted Investigation.mode is authoritative, so resume runs in the mode the investigation started in.
        self.llm = LLMClient(self.inv.incident.id, self.inv.mode)
        self.fallback_logged = False
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
        # The replay key doubles as the template name, so prompts and recordings cannot drift apart.
        prompt_key = f"thought.{key}"
        messages = [{"role": "system", "content": load_template("system")},
                    {"role": "user", "content": fill_prompt(load_template(prompt_key), _facts(self.inv))}]
        text = self.llm.complete(prompt_key, messages)
        if self.llm.fallback_reason and not self.fallback_logged:
            self.fallback_logged = True
            self.step("decision", f"Live LLM unavailable ({self.llm.fallback_reason}); "
                                  "continuing with replay recordings.")
        if text:
            self.step("thought", text)

    def tool(self, name: str, *args, label: str | None = None, **kwargs):
        # `label` is the readable step text and never reaches the engine.
        # Only scalar arguments are recorded; models and lists would bloat every poll.
        scalars = {k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))}
        self.step("tool_call", label or tools.DESCRIPTIONS.get(name, f"Calling {name}"), tool=name,
                  input=scalars or None)
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
    inv.timeline = r.tool("build_timeline", incident_id=incident_id,
                          label=f"Reconstructing the {inv.incident.window.minutes}-minute timeline for {incident_id}")
    changes = [e for e in inv.timeline if e.state_change]
    summary = f"{len(inv.timeline)} events, {len(changes)} state changes"
    if changes:
        summary += ": " + "; ".join(f"{e.id} {e.state_change.param} {e.state_change.from_} → {e.state_change.to}"
                                    for e in changes)
    r.step("tool_result", summary, tool="build_timeline")

    r.stage("hypotheses")
    r.think("hypotheses")
    inv.hypotheses = r.tool("seed_hypotheses", incident_id=incident_id, timeline=inv.timeline,
                            label=f"Proposing competing hypotheses from {len(inv.timeline)} events")
    r.step("tool_result", f"{len(inv.hypotheses)} competing hypotheses: "
           + "; ".join(f"{h.id} {h.title}" for h in inv.hypotheses), tool="seed_hypotheses")

    r.stage("evidence")
    r.think("evidence")
    seen: dict[str, Any] = {}
    for h in inv.hypotheses:
        items = r.tool("gather_evidence", incident_id=incident_id, hypothesis=h,
                       label=f"Gathering evidence for {h.id} {h.title}")
        for e in items:
            seen.setdefault(e.id, e)
        inv.evidence = list(seen.values())
        supporting = sum(e.stance.get(h.id) == "supports" for e in items)
        refuting = sum(e.stance.get(h.id) == "refutes" for e in items)
        r.step("tool_result", f"{h.id} {h.title}: {len(items)} evidence items "
               f"({supporting} supporting, {refuting} refuting)", tool="gather_evidence")

    r.stage("testing")
    r.think("testing")
    tested = []
    for h in inv.hypotheses:
        relevant = [e for e in inv.evidence if h.id in e.stance]
        result = r.tool("test_hypothesis", hypothesis=h, evidence=relevant,
                        label=f"Testing {h.id} {h.title} against {len(relevant)} evidence items")
        tested.append(result)
        r.step("tool_result", _verdict(result), tool="test_hypothesis")
    inv.hypotheses = tested

    r.stage("root_cause")
    r.think("root_cause")
    surviving = sum(h.status != "rejected" for h in inv.hypotheses)
    inv.root_cause = r.tool("determine_root_cause", hypotheses=inv.hypotheses, evidence=inv.evidence,
                            timeline=inv.timeline,
                            label=f"Determining the root cause from {surviving} surviving "
                                  f"{'hypothesis' if surviving == 1 else 'hypotheses'}")
    inv.hypotheses = [h.model_copy(update={"status": "confirmed"}) if h.id == inv.root_cause.hypothesis_id else h
                      for h in inv.hypotheses]
    rc = inv.root_cause
    r.step("decision", f"Root cause {rc.hypothesis_id} {_hypothesis_title(inv, rc.hypothesis_id)} "
           f"(confidence {rc.confidence}): {rc.statement}", tool="determine_root_cause")

    r.stage("counterfactual")
    r.think("counterfactual")
    model = r.tool("load_system_model", incident_id=incident_id, label=f"Loading the system model for {incident_id}")
    inv.interventions = r.tool("generate_interventions", root_cause=inv.root_cause, model=model,
                               label=f"Generating candidate interventions for root cause {rc.hypothesis_id}")
    inv.simulations = [r.tool("simulate", model=model, interventions=[], seed=0,
                              label="Simulating the baseline (no intervention)")]
    for intervention in inv.interventions:
        inv.simulations.append(r.tool("simulate", model=model, interventions=[intervention], seed=0,
                                      label=f"Simulating {intervention.id} {intervention.title}"))
    prevented = [s.intervention_ids[0] for s in inv.simulations[1:] if s.prevented]
    missed = [s.intervention_ids[0] for s in inv.simulations[1:] if not s.prevented]
    r.step("tool_result", f"Baseline: {inv.simulations[0].breach_minutes} breach minutes; "
           f"{len(prevented)}/{len(inv.interventions)} interventions prevent it "
           f"(prevented by {', '.join(prevented) or 'none'}; not by {', '.join(missed) or 'none'})", tool="simulate")
    inv.ranking = r.tool("rank", results=inv.simulations, interventions=inv.interventions,
                         label=f"Ranking {len(inv.interventions)} interventions")
    r.step("tool_result", "Ranked: " + "; ".join(_ranked(inv, x) for x in inv.ranking), tool="rank")
    _recommend(r)


def _recommend(r: _Run) -> None:
    inv = r.inv
    inv.recommendation = inv.ranking[0] if inv.ranking else None
    r.think("recommendation")
    if rec := inv.recommendation:
        outcome = "prevents the breach" if rec.prevented else "does not prevent the breach"
        r.step("decision", f"Recommend {rec.intervention_id} {_intervention_title(inv, rec.intervention_id)}: "
               f"{outcome}, avoiding {rec.breach_minutes_avoided} breach minutes "
               f"(rank {rec.rank}, score {rec.score})")
    else:
        r.step("decision", "No interventions left to recommend")
    r.stage("awaiting_approval")


def resume_after_approval(investigation_id: str, approval: Approval, store: Store, mode: str | None = None) -> None:
    # `mode` is kept only for signature compatibility; Investigation.mode is the source of truth.
    r = _Run(investigation_id, store)
    r.llm.record = False  # only the investigation run is recorded; a replan must not overwrite its narration
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
