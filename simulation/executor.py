"""Controlled execution. Owner: Goyal.

Applies an intervention to the in-memory SIMULATED environment only — never to
real infrastructure. FOUNDATION STUB: records the action as applied.
"""

from __future__ import annotations

from contracts.models import ExecutionResult, Intervention, SystemModel


def execute(intervention: Intervention, model: SystemModel) -> ExecutionResult:
    return ExecutionResult(
        intervention_id=intervention.id,
        applied_changes=[intervention.action.model_copy()],
        status="applied",
    )
