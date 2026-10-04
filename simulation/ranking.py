"""Intervention ranking and replanning. Owner: Goyal.

FOUNDATION STUB scoring: `prevented` is a hard gate, then
score = breach minutes avoided - risk penalty - effort penalty.
"""

from __future__ import annotations

from contracts.models import Intervention, RankedIntervention, SimulationResult, SystemModel, VerificationResult

RISK_PENALTY = {"low": 0.0, "med": 3.0, "high": 8.0}
EFFORT_PENALTY_PER_HOUR = 0.5


def rank(results: list[SimulationResult], interventions: list[Intervention]) -> list[RankedIntervention]:
    by_id = {i.id: i for i in interventions}
    baseline = next((r for r in results if not r.intervention_ids), None)
    baseline_breach = baseline.breach_minutes if baseline else max((r.breach_minutes for r in results), default=0)

    scored = []
    for result in results:
        if len(result.intervention_ids) != 1 or result.intervention_ids[0] not in by_id:
            continue
        intervention = by_id[result.intervention_ids[0]]
        avoided = baseline_breach - result.breach_minutes
        score = avoided - RISK_PENALTY[intervention.risk] - EFFORT_PENALTY_PER_HOUR * intervention.effort_hours
        reasons = [
            "prevents the SLO breach" if result.prevented else f"{result.breach_minutes} breach minutes remain",
            f"avoids {avoided} of {baseline_breach} breach minutes",
            f"risk {intervention.risk}, effort {intervention.effort_hours} h",
        ]
        scored.append((result.prevented, round(score, 2), intervention.id, avoided, reasons))

    scored.sort(key=lambda s: (not s[0], -s[1], s[2]))
    return [
        RankedIntervention(intervention_id=iid, rank=n, score=score, prevented=prevented,
                           breach_minutes_avoided=avoided, reasons=reasons)
        for n, (prevented, score, iid, avoided, reasons) in enumerate(scored, start=1)
    ]


def replan(failed: VerificationResult, ranking: list[RankedIntervention], model: SystemModel) -> list[RankedIntervention]:
    remaining = [r for r in ranking if r.intervention_id != failed.intervention_id]
    return [r.model_copy(update={"rank": n}) for n, r in enumerate(remaining, start=1)]
