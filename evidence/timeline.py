"""Timeline reconstruction. Owner: Vinayak.

The timeline is the fixture events (events.json) plus the first sightings that only show up in raw
telemetry: the first pool-acquire timeout log, the first retry log and the first failed request trace.
Derived events get ids after the last fixture id, never carry a state_change, and the whole timeline
is ordered by (t, ts, id). Deterministic: no clock, no randomness, no network.
"""

from __future__ import annotations

from typing import Any

from contracts.models import Event
from data.loader import load_events, load_logs, load_traces

POOL_TIMEOUT_MARKER = "Connection is not available"
RETRY_MARKER = "Retrying"


def _first(rows: list[dict[str, Any]], match) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    hits = [r for r in rows if match(r)]
    return (min(hits, key=lambda r: (r["t"], r["ts"])) if hits else None), hits


def _derived(incident_id: str) -> list[dict[str, Any]]:
    logs, traces = load_logs(incident_id), load_traces(incident_id)
    found = []

    first, hits = _first(logs, lambda r: r["level"] == "ERROR" and POOL_TIMEOUT_MARKER in r["message"])
    if first:
        found.append(dict(ts=first["ts"], t=first["t"], source=first["service"], kind="log",
                          summary=f"First pool-acquire timeout: {first['message']}",
                          attributes={"log_id": first["id"], "occurrences": len(hits),
                                      "regions": sorted({r["region"] for r in hits if "region" in r}),
                                      "versions": sorted({r["version"] for r in hits if "version" in r})}))

    first, hits = _first(logs, lambda r: RETRY_MARKER in r["message"])
    if first:
        found.append(dict(ts=first["ts"], t=first["t"], source=first["service"], kind="log",
                          summary=f"Retries begin: {first['message']}",
                          attributes={"log_id": first["id"], "occurrences": len(hits)}))

    first, hits = _first(traces, lambda r: r["status"] == "error")
    if first:
        span = first["spans"][-1]
        reached = [s["name"] for s in first["spans"]]
        found.append(dict(ts=first["ts"], t=first["t"], source="checkout", kind="trace",
                          summary=f"First failed checkout trace: {span['name']} failed after {span['duration_ms']} ms "
                                  f"({span.get('error', 'error')}); spans reached: {', '.join(reached)}",
                          attributes={"trace_id": first["trace_id"], "failed_traces": len(hits),
                                      "spans": reached, "region": first["region"], "version": first["version"]}))
    return found


def build_timeline(incident_id: str) -> list[Event]:
    base = load_events(incident_id)
    next_n = max((int(e.id.split("-")[1]) for e in base), default=0) + 1
    derived = []
    for n, row in enumerate(sorted(_derived(incident_id), key=lambda r: (r["t"], r["ts"], r["kind"])), next_n):
        derived.append(Event(id=f"E-{n:03d}", **row))
    return sorted(base + derived, key=lambda e: (e.t, e.ts, e.id))
