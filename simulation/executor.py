"""Controlled execution. Owner: Goyal.

Applies an intervention to an in-memory copy of the SystemModel, never to real infrastructure. The changed
model is equivalent to replaying the original with the actions: replay(apply_changes(m, a)) == replay(m, a).
- `set_param` writes the param and drops the incident's later changes to it, so the pin holds.
- `cap_param` caps the param and every incident change to it.
- `block_event` and `shift_event` remove or move that event's param changes. A shifted job keeps its end (see
  replay.py). An event without a param change has nothing to remove or move.
Validation is replay's: an unknown param or a malformed value fails the execution, and the input model is
never touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.models import ExecutionResult, Intervention, InterventionAction, SystemModel
from simulation.replay import _shift, _validate


def execute(intervention: Intervention, model: SystemModel) -> ExecutionResult:
    action = intervention.action.model_copy()
    try:
        apply_changes(model, [action])
    except (KeyError, ValueError):
        return ExecutionResult(intervention_id=intervention.id, applied_changes=[], status="failed")
    return ExecutionResult(intervention_id=intervention.id, applied_changes=[action], status="applied")


def apply_changes(model: SystemModel, actions: Sequence[InterventionAction]) -> SystemModel:
    """A changed deep copy of `model` with `actions` applied in order."""
    _validate(model, actions)
    changed = model.model_copy(deep=True)
    params, changes = changed.params, changed.param_changes
    for action in actions:
        if action.op == "set_param":
            params[action.target] = action.value
            changes = [c for c in changes if c.param != action.target]
        elif action.op == "cap_param":
            params[action.target] = min(params[action.target], action.value)
            changes = [c.model_copy(update={"value": min(c.value, action.value)}) if c.param == action.target else c
                       for c in changes]
        elif action.op == "block_event":
            changes = [c for c in changes if c.event_id != action.target]
        else:
            changes = _shift(params, changes, action.target, int(action.value))
    changed.params, changed.param_changes = params, changes
    return changed
