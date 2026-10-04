"""Verification. Owner: Goyal.

FOUNDATION STUB: replays the incident with the executed intervention through
`simulate` and checks the SLO. The stress variant (demand +20%) is a TODO and
currently reuses the same run.
"""

from __future__ import annotations

from contracts.models import ExecutionResult, SystemModel, VerificationCheck, VerificationResult
from simulation.interventions import get_intervention
from simulation.simulator import simulate


def verify(execution: ExecutionResult, model: SystemModel, seed: int) -> VerificationResult:
    if execution.status != "applied":
        return VerificationResult(
            intervention_id=execution.intervention_id, passed=False, stress_test_passed=False,
            checks=[VerificationCheck(name="execution applied", expected="applied",
                                      observed=execution.status, passed=False)],
        )
    result = simulate(model, [get_intervention(execution.intervention_id)], seed=seed)
    checks = [
        VerificationCheck(name="breach minutes", expected=f"<= {model.slo.max_breach_minutes}",
                          observed=str(result.breach_minutes),
                          passed=result.breach_minutes <= model.slo.max_breach_minutes),
        VerificationCheck(name="peak error rate", expected=f"<= {model.slo.max_error_rate}",
                          observed=str(result.peak_error_rate),
                          passed=result.peak_error_rate <= model.slo.max_error_rate),
    ]
    passed = all(c.passed for c in checks)
    return VerificationResult(intervention_id=execution.intervention_id, passed=passed, checks=checks,
                              stress_test_passed=passed)
