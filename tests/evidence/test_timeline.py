"""Timeline reconstruction is ordered, complete and consistent with the incident window."""

from datetime import datetime, timedelta

from contracts.models import Event
from data.loader import load_events, load_incident
from evidence import build_timeline

INCIDENT = "INC-2041"


def _ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_timeline_is_ordered_by_time():
    timeline = build_timeline(INCIDENT)
    assert [(e.t, _ts(e.ts)) for e in timeline] == sorted((e.t, _ts(e.ts)) for e in timeline)


def test_timeline_contains_every_fixture_event_unchanged():
    timeline = {e.id: e for e in build_timeline(INCIDENT)}
    for event in load_events(INCIDENT):
        assert timeline[event.id] == event


def test_timeline_adds_first_sightings_from_raw_telemetry():
    derived = [e for e in build_timeline(INCIDENT) if e.id not in {f.id for f in load_events(INCIDENT)}]
    assert [e.id for e in sorted(derived, key=lambda e: e.id)] == ["E-011", "E-012", "E-013"]
    by_kind = {e.kind: e for e in derived}
    assert by_kind["trace"].attributes["spans"] == ["pool.acquire"]
    assert all(e.state_change is None for e in derived)
    assert any("pool-acquire timeout" in e.summary for e in derived)
    assert any(e.summary.startswith("Retries begin") for e in derived)


def test_timeline_ids_are_unique_and_inside_the_window():
    incident = load_incident(INCIDENT)
    start = _ts(incident.window.start)
    timeline = build_timeline(INCIDENT)
    assert len({e.id for e in timeline}) == len(timeline)
    for e in timeline:
        assert 0 <= e.t < incident.window.minutes
        assert start + timedelta(minutes=e.t) <= _ts(e.ts) < start + timedelta(minutes=e.t + 1)


def test_only_the_fixture_state_changes_carry_state_change():
    assert {e.id for e in build_timeline(INCIDENT) if e.state_change} == {"E-001", "E-004", "E-009"}


def test_timeline_validates_against_the_contract():
    for e in build_timeline(INCIDENT):
        assert Event.model_validate(e.model_dump(by_alias=True)) == e


def test_timeline_is_deterministic():
    assert build_timeline(INCIDENT) == build_timeline(INCIDENT)
