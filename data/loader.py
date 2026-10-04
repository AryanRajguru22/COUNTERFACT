"""Load incident fixtures from data/incidents/<folder>/ into contract models. Owner: Vinayak."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from contracts.models import Event, Incident, MetricSeries, SystemModel

INCIDENTS_DIR = Path(__file__).parent / "incidents"


@lru_cache(maxsize=None)
def _incident_dirs() -> dict[str, Path]:
    dirs = {}
    for path in sorted(INCIDENTS_DIR.glob("*/incident.json")):
        dirs[json.loads(path.read_text(encoding="utf-8"))["id"]] = path.parent
    return dirs


def incident_ids() -> list[str]:
    return list(_incident_dirs())


def load_json(incident_id: str, name: str) -> Any:
    try:
        folder = _incident_dirs()[incident_id]
    except KeyError:
        raise KeyError(f"unknown incident: {incident_id}") from None
    return json.loads((folder / name).read_text(encoding="utf-8"))


def load_incident(incident_id: str) -> Incident:
    return Incident.model_validate(load_json(incident_id, "incident.json"))


def load_events(incident_id: str) -> list[Event]:
    return [Event.model_validate(e) for e in load_json(incident_id, "events.json")]


def load_metrics(incident_id: str) -> list[MetricSeries]:
    return [MetricSeries.model_validate(m) for m in load_json(incident_id, "metrics.json")]


def load_system_model_json(incident_id: str) -> SystemModel:
    return SystemModel.model_validate(load_json(incident_id, "system_model.json"))


def load_ground_truth(incident_id: str) -> dict[str, Any]:
    """Tests only. The agent must never read ground truth."""
    return load_json(incident_id, "ground_truth.json")
