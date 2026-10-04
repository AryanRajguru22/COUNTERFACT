"""Timeline reconstruction. Owner: Vinayak. FOUNDATION STUB: returns the fixture events in time order."""

from __future__ import annotations

from contracts.models import Event
from data.loader import load_events


def build_timeline(incident_id: str) -> list[Event]:
    return sorted(load_events(incident_id), key=lambda e: (e.t, e.id))
