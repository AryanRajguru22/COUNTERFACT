"""Intervention catalogue. Owner: Goyal.

FOUNDATION STUB: returns the fixed INC-2041 catalogue (I1-I5) for an H1 root
cause. The signature is frozen; interventions come from a catalogue, never
invented by the LLM.
"""

from __future__ import annotations

from contracts.models import Intervention, InterventionAction, RootCause, SystemModel

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
    return [i.model_copy(deep=True) for i in CATALOGUE]


def get_intervention(intervention_id: str) -> Intervention:
    for intervention in CATALOGUE:
        if intervention.id == intervention_id:
            return intervention.model_copy(deep=True)
    raise KeyError(f"unknown intervention: {intervention_id}")
