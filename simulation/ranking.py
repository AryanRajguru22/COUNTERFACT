"""Intervention ranking and replanning. Owner: Goyal.

Scoring: `prevented` is a hard gate, then score = breach minutes avoided - risk penalty - effort penalty,
with ties broken by intervention id. `replan` re-simulates the remaining candidates and ranks them again.
"""

from __future__ import annotations

from contracts.models import Intervention, RankedIntervention, SimulationResult, SystemModel, VerificationResult
from simulation.interventions import get_intervention
from simulation.simulator import simulate

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
    """Re-simulate and re-rank what is left after `failed`, against `model`.

    The candidates are the interventions still in `ranking`: the root cause already filtered them, and earlier
    replans already dropped earlier failures. The failed one is excluded. Each candidate is simulated again
    from the catalogue against `model`, next to a fresh baseline, and ranked with `rank`, so stale scores are
    never reused. A failed verification ran on an in-memory copy, so `model` is still the incident's state
    and the failed change is not applied underneath the candidates.
    """
    remaining = dict.fromkeys(r.intervention_id for r in ranking if r.intervention_id != failed.intervention_id)
    candidates = [get_intervention(intervention_id) for intervention_id in remaining]
    if not candidates:
        return []
    results = [simulate(model, [])] + [simulate(model, [candidate]) for candidate in candidates]
    return rank(results, candidates)
