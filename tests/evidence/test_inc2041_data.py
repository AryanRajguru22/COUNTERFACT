"""INC-2041 raw telemetry is present, aligned with the v1 fixture and tells a consistent story."""

from data import loader

INCIDENT = "INC-2041"


def _in_window(t):
    return 0 <= t < loader.load_incident(INCIDENT).window.minutes


def test_raw_telemetry_files_load():
    assert loader.load_deploys(INCIDENT)
    assert loader.load_config(INCIDENT)["payment-svc"]["db.pool.max"] == 10
    assert loader.load_logs(INCIDENT)
    assert loader.load_traces(INCIDENT)


def test_logs_and_traces_sit_inside_the_window_in_order():
    for rows in (loader.load_logs(INCIDENT), loader.load_traces(INCIDENT)):
        assert all(_in_window(r["t"]) for r in rows)
        assert [r["ts"] for r in rows] == sorted(r["ts"] for r in rows)


def test_change_records_match_timeline_events():
    events = {e.attributes.get("change_id") or e.attributes.get("version"): e for e in loader.load_events(INCIDENT)}
    by_id = {d["id"]: d for d in loader.load_deploys(INCIDENT)}
    assert by_id["CHG-881"]["t"] == events["CHG-881"].t
    assert by_id["DEP-7101"]["t"] == events["v2.4.1"].t
    assert by_id["DEP-7102"]["t"] == events["v2.4.0"].t


def test_failed_traces_match_observed_error_rate():
    errors = {p.t: p.value for p in next(s for s in loader.load_metrics(INCIDENT) if s.name == "checkout_5xx_rate").points}
    traces = loader.load_traces(INCIDENT)
    for t in range(60):
        minute = [x for x in traces if x["t"] == t]
        failed = sum(x["status"] == "error" for x in minute)
        assert abs(failed / len(minute) - errors[t]) <= 1 / len(minute)


def test_missing_optional_files_default_to_empty():
    assert loader._optional(INCIDENT, "does-not-exist.json", []) == []
