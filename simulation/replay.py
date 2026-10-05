"""Deterministic parameter replay. Owner: Goyal.

`replay(model, actions)` returns the effective `SystemModel.params` for every minute of the demand window,
after replaying `param_changes` and applying intervention actions. It is pure: no I/O, no randomness, and
it never mutates its inputs.

Action semantics:
- `block_event`: changes carrying that `event_id` never happen.
- `shift_event`: changes carrying that `event_id` move by `value` minutes. A shifted change takes its revert
  with it: the next change to the same param that restores the value it overrode (E-004 starts the batch job,
  E-009 ends it), so moving a job moves the whole job. Changes that land before minute 0 are applied, in
  order, before the window opens; changes at or after the window end never happen.
- `set_param`: pins the param for the whole window; it wins over `param_changes`.
- `cap_param`: the param never exceeds `value`.
- `set_param` and `cap_param` on the same param apply in action order.

Only `SystemModel` reaches the simulator, so an event id without a param change (such as a deploy) is a
no-op for `block_event` and `shift_event`. An unknown param raises `KeyError`.
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.models import InterventionAction, ParamChange, Scalar, SystemModel


def replay(model: SystemModel, actions: Sequence[InterventionAction] = ()) -> list[dict[str, Scalar]]:
    _validate(model, actions)
    changes = list(model.param_changes)
    for action in actions:
        if action.op == "block_event":
            changes = [c for c in changes if c.event_id != action.target]
        elif action.op == "shift_event":
            changes = _shift(model.params, changes, action.target, int(action.value))
    changes.sort(key=lambda c: c.t)  # stable: changes in the same minute keep their model order

    params = dict(model.params)
    timeline = []
    applied = 0
    for t in range(len(model.exogenous.demand_rps)):
        while applied < len(changes) and changes[applied].t <= t:
            params[changes[applied].param] = changes[applied].value
            applied += 1
        timeline.append(_override(params, actions))
    return timeline


def _validate(model: SystemModel, actions: Sequence[InterventionAction]) -> None:
    for action in actions:
        if action.op in ("set_param", "cap_param") and action.target not in model.params:
            raise KeyError(f"unknown param: {action.target}")
        if action.op == "block_event":
            continue
        if action.value is None:
            raise ValueError(f"{action.op} {action.target} needs a value")
        if action.op == "cap_param" and not _is_number(action.value):
            raise ValueError(f"cap_param {action.target} needs a numeric value, got {action.value!r}")
        if action.op == "shift_event" and not (_is_number(action.value) and action.value == int(action.value)):
            raise ValueError(f"shift_event {action.target} needs a whole number of minutes, got {action.value!r}")


def _is_number(value: Scalar) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _shift(params: dict[str, Scalar], changes: list[ParamChange], event_id: str, minutes: int) -> list[ParamChange]:
    order = sorted(range(len(changes)), key=lambda i: changes[i].t)
    moved = set()
    for pos, i in enumerate(order):
        change = changes[i]
        if change.event_id != event_id:
            continue
        moved.add(i)
        earlier = [changes[j] for j in order[:pos] if changes[j].param == change.param]
        overridden = earlier[-1].value if earlier else params.get(change.param)
        revert = next((j for j in order[pos + 1:] if changes[j].param == change.param), None)
        if revert is not None and changes[revert].value == overridden:
            moved.add(revert)
    return [c.model_copy(update={"t": c.t + minutes}) if i in moved else c for i, c in enumerate(changes)]


def _override(params: dict[str, Scalar], actions: Sequence[InterventionAction]) -> dict[str, Scalar]:
    effective = dict(params)
    for action in actions:
        if action.op == "set_param":
            effective[action.target] = action.value
        elif action.op == "cap_param":
            effective[action.target] = min(effective[action.target], action.value)
    return effective
