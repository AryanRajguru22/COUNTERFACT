"""Counterfactual simulator. Owner: Goyal.

FOUNDATION STUB: outcomes are canned per intervention so the end-to-end flow
works from hour 0. Goyal replaces the body with the real deterministic,
seeded minute-step model. The signature is frozen: pure, no I/O, no LLM.
"""

from __future__ import annotations

from contracts.models import Intervention, SimSeries, SimulationResult, SystemModel

BASELINE_ERROR = 0.002

# intervention_id -> (peak error rate, first breach minute, last breach minute); None = no breach window
_CANNED: dict[str, tuple[float, int | None, int | None]] = {
    "baseline": (0.38, 32, 53),
    "I1": (0.01, None, None),
    "I2": (0.02, None, None),
    "I3": (0.12, 33, 41),
    "I4": (0.01, None, None),
    "I5": (0.38, 32, 53),
}


def simulate(model: SystemModel, interventions: list[Intervention], seed: int = 0) -> SimulationResult:
    outcomes = [_CANNED.get(i.id, _CANNED["baseline"]) for i in interventions] or [_CANNED["baseline"]]
    # A combination does at least as well as its best member.
    peak, start, end = min(outcomes, key=lambda o: (0 if o[1] is None else o[2] - o[1] + 1, o[0]))

    minutes = len(model.exogenous.demand_rps)
    hold_s = float(model.params.get("conn_hold_ms", 80)) / 1000
    in_breach = [start is not None and start <= t <= end for t in range(minutes)]
    error_rate = [peak if b else (peak if start is None and 31 <= t <= 52 else BASELINE_ERROR)
                  for t, b in enumerate(in_breach)]
    series = SimSeries(
        error_rate=error_rate,
        pool_wait_ms=[1800.0 if b else 2.0 for b in in_breach],
        inflight=[round(rps * hold_s, 2) for rps in model.exogenous.demand_rps],
    )
    breach_minutes = sum(1 for e in error_rate if e > model.slo.max_error_rate)
    return SimulationResult(
        intervention_ids=[i.id for i in interventions],
        seed=seed,
        series=series,
        peak_error_rate=max(error_rate, default=0.0),
        breach_minutes=breach_minutes,
        prevented=breach_minutes <= model.slo.max_breach_minutes,
    )
