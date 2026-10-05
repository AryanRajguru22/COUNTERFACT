"""THE single wiring point between the agent/backend and the engines. Owner: Rohit.

Nothing else in agent/ or backend/ imports evidence/, simulation/ or data/.
Each tool is a plain function returning contract models; DESCRIPTIONS is what an
LLM will see when tool-calling is added.
"""

from __future__ import annotations

from typing import Callable

import evidence
import simulation
from contracts.models import Incident, MetricSeries
from data import loader


def list_incidents() -> list[Incident]:
    return [loader.load_incident(i) for i in loader.incident_ids()]


def get_incident(incident_id: str) -> Incident:
    return loader.load_incident(incident_id)


def get_metrics(incident_id: str) -> list[MetricSeries]:
    """Observed telemetry for an incident, as the fixture records it (read-only; the UI charts it)."""
    return loader.load_metrics(incident_id)


class FixtureError(Exception):
    """An incident fixture the engines read is missing, unreadable or the wrong shape."""


# Every fixture file the engines read, with its loader. The first four are the frozen data contract and must
# exist. The raw telemetry is optional by design (the loader returns empty data without it) but must have the
# right top-level shape when present. ground_truth.json is deliberately absent: only tests may read it.
_FIXTURES: tuple[tuple[str, Callable, type | None], ...] = (
    ("incident.json", loader.load_incident, None),
    ("events.json", loader.load_events, None),
    ("metrics.json", loader.load_metrics, None),
    ("system_model.json", loader.load_system_model_json, None),
    ("deploys.json", loader.load_deploys, list),
    ("config.json", loader.load_config, dict),
    ("logs.json", loader.load_logs, list),
    ("traces.json", loader.load_traces, list),
)


def check_fixtures(incident_id: str) -> None:
    """Load every fixture the engines read, so a broken file fails /api/health instead of an investigation."""
    for name, load, shape in _FIXTURES:
        try:
            data = load(incident_id)
        except Exception as error:
            raise FixtureError(f"{incident_id} {name}: {type(error).__name__}: {error}") from error
        if shape is not None and not isinstance(data, shape):
            raise FixtureError(f"{incident_id} {name}: expected a JSON {shape.__name__}, got {type(data).__name__}")


TOOLS: dict[str, Callable] = {
    # evidence engine (Vinayak)
    "build_timeline": evidence.build_timeline,
    "seed_hypotheses": evidence.seed_hypotheses,
    "gather_evidence": evidence.gather_evidence,
    "test_hypothesis": evidence.test_hypothesis,
    "determine_root_cause": evidence.determine_root_cause,
    # counterfactual engine (Goyal)
    "load_system_model": simulation.load_system_model,
    "generate_interventions": simulation.generate_interventions,
    "get_intervention": simulation.get_intervention,
    "simulate": simulation.simulate,
    "rank": simulation.rank,
    "execute": simulation.execute,
    "verify": simulation.verify,
    "replan": simulation.replan,
}

DESCRIPTIONS: dict[str, str] = {
    "build_timeline": "Reconstruct the ordered event timeline for an incident.",
    "seed_hypotheses": "Propose competing root-cause hypotheses from the timeline.",
    "gather_evidence": "Collect evidence items that bear on one hypothesis.",
    "test_hypothesis": "Score a hypothesis against its evidence; support or reject it.",
    "determine_root_cause": "Promote the strongest surviving hypothesis to root cause with a causal chain.",
    "load_system_model": "Load the replayable system model (params, demand, state changes, SLO).",
    "generate_interventions": "List candidate interventions for the root cause.",
    "get_intervention": "Look up one intervention by id.",
    "simulate": "Replay the incident with interventions applied; deterministic for a given seed.",
    "rank": "Rank interventions by whether they prevent the breach, then score.",
    "execute": "Apply an approved intervention to the simulated environment.",
    "verify": "Replay the incident on the changed environment and check the SLO.",
    "replan": "Re-rank after a failed or rejected intervention.",
}


def call(name: str, *args, **kwargs):
    return TOOLS[name](*args, **kwargs)
