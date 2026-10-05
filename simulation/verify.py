"""Verification. Owner: Goyal.

The source of truth is `execution.applied_changes`; the catalogue is never consulted. They are applied to an
in-memory copy of the model, and that changed model is simulated twice:
- as recorded: breach minutes and peak error rate must meet the SLO;
- stressed, with every minute's demand x STRESS_DEMAND_FACTOR: breach minutes must meet the SLO.
`passed` means every check passed, the stress check included. `stress_test_passed` is the stress check alone.
"""

from __future__ import annotations

from contracts.models import ExecutionResult, Exogenous, SystemModel, VerificationCheck, VerificationResult
from simulation.executor import apply_changes
from simulation.simulator import simulate

STRESS_DEMAND_FACTOR = 1.2  # +20% demand


def verify(execution: ExecutionResult, model: SystemModel, seed: int) -> VerificationResult:
    if execution.status != "applied":
        return _failed(execution.intervention_id, "execution applied", "applied", execution.status)
    try:
        changed = apply_changes(model, execution.applied_changes)
    except (KeyError, ValueError) as error:
        return _failed(execution.intervention_id, "applied changes are valid", "valid", str(error))

    slo = model.slo
    result = simulate(changed, [], seed=seed)
    stressed = simulate(stress_variant(changed), [], seed=seed)
    stress = VerificationCheck(name=f"breach minutes at +{round((STRESS_DEMAND_FACTOR - 1) * 100)}% demand",
                               expected=f"<= {slo.max_breach_minutes}", observed=str(stressed.breach_minutes),
                               passed=stressed.breach_minutes <= slo.max_breach_minutes)
    checks = [
        VerificationCheck(name="breach minutes", expected=f"<= {slo.max_breach_minutes}",
                          observed=str(result.breach_minutes), passed=result.breach_minutes <= slo.max_breach_minutes),
        VerificationCheck(name="peak error rate", expected=f"<= {slo.max_error_rate:.1%}",
                          observed=f"{result.peak_error_rate:.1%}", passed=result.peak_error_rate <= slo.max_error_rate),
        stress,
    ]
    return VerificationResult(intervention_id=execution.intervention_id, passed=all(c.passed for c in checks),
                              checks=checks, stress_test_passed=stress.passed)


def stress_variant(model: SystemModel) -> SystemModel:
    """A copy of `model` with every minute's demand scaled by STRESS_DEMAND_FACTOR."""
    demand = [rps * STRESS_DEMAND_FACTOR for rps in model.exogenous.demand_rps]
    return model.model_copy(update={"exogenous": Exogenous(demand_rps=demand)})


def _failed(intervention_id: str, name: str, expected: str, observed: str) -> VerificationResult:
    return VerificationResult(intervention_id=intervention_id, passed=False, stress_test_passed=False,
                              checks=[VerificationCheck(name=name, expected=expected, observed=observed, passed=False)])
