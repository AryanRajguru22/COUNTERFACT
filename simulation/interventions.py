"""Intervention catalogue. Owner: Goyal.

Interventions come from this fixed catalogue and are never invented by the LLM. The signature is frozen.

`generate_interventions` keeps the entries that address the root cause's causal chain:
- `block_event` and `shift_event` address it when their target event is in the chain.
- `set_param` and `cap_param` address it when the chain runs through modelled state, i.e. some chain event is
  a `param_change` in the system model. Every param of the pool model can then change the outcome.
- `rollback` entries are controls. They are simulated next to any real fix, because rolling back the latest
  change is the usual first response and the lab has to show whether it would have helped (docs/DEMO.md step 5).
A root cause that no entry addresses gets an empty list. Catalogue order is kept.
"""

from __future__ import annotations

from contracts.models import Intervention, InterventionAction, RootCause, SystemModel

CONTROL_CATEGORIES = frozenset({"rollback"})

CATALOGUE: list[Intervention] = [
    Intervention(id="I1", title="Revert pool size to 50", category="config",
                 action=InterventionAction(op="set_param", target="pool_size", value=50),
                 risk="low", effort_hours=0.25,
                 rationale="Restores the connection headroom that CHG-881 removed."),
    Intervention(id="I2", title="Move settlement-reconcile off-peak", category="schedule",
                 action=InterventionAction(op="shift_event", target="E-004", value=-720),
                 risk="low", effort_hours=0.5,
                 rationale="Removes batch-job contention for the checkout pool during peak hours."),
    Intervention(id="I3", title="Retry budget with jitter", category="resilience",
                 action=InterventionAction(op="cap_param", target="retry_max", value=1),
                 risk="med", effort_hours=2.0,
                 rationale="Limits retry amplification once requests start timing out."),
    Intervention(id="I4", title="Capacity-check guardrail for pool-reducing config changes", category="guardrail",
                 action=InterventionAction(op="block_event", target="E-001"),
                 risk="low", effort_hours=4.0,
                 rationale="Blocks CHG-881 and every future config change that cuts capacity below demand."),
    Intervention(id="I5", title="Roll back v2.4.1", category="rollback",
                 action=InterventionAction(op="block_event", target="E-002"),
                 risk="low", effort_hours=0.25,
                 rationale="Removes the v2.4.1 deploy (tests the rejected H2)."),
]


def generate_interventions(root_cause: RootCause, model: SystemModel) -> list[Intervention]:
    chain = {link.event_id for link in root_cause.causal_chain}
    through_state = any(change.event_id in chain for change in model.param_changes)
    fixes = {i.id for i in CATALOGUE if _addresses(i, chain, through_state)}
    if not fixes:
        return []
    return [i.model_copy(deep=True) for i in CATALOGUE if i.id in fixes or i.category in CONTROL_CATEGORIES]


def _addresses(intervention: Intervention, chain: set[str], through_state: bool) -> bool:
    if intervention.action.op in ("block_event", "shift_event"):
        return intervention.action.target in chain
    return through_state


def get_intervention(intervention_id: str) -> Intervention:
    for intervention in CATALOGUE:
        if intervention.id == intervention_id:
            return intervention.model_copy(deep=True)
    raise KeyError(f"unknown intervention: {intervention_id}")
