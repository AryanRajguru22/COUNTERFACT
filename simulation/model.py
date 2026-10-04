"""System model loading. Owner: Goyal."""

from __future__ import annotations

from contracts.models import SystemModel
from data.loader import load_system_model_json


def load_system_model(incident_id: str) -> SystemModel:
    return load_system_model_json(incident_id)
