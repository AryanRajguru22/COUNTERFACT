"""The INC-2041 golden fixture loads into contract models and is internally consistent."""

from data import loader

INCIDENT = "INC-2041"


def test_all_fixture_files_parse():
    assert INCIDENT in loader.incident_ids()
    assert loader.load_incident(INCIDENT).title == "Checkout payments failing"
    assert len(loader.load_events(INCIDENT)) == 10
    assert loader.load_metrics(INCIDENT)
    assert loader.load_system_model_json(INCIDENT).slo.max_error_rate == 0.05


def test_param_changes_match_state_changing_events():
    events = {e.id: e for e in loader.load_events(INCIDENT)}
    for change in loader.load_system_model_json(INCIDENT).param_changes:
        event = events[change.event_id]
        assert event.t == change.t
        assert event.state_change.param == change.param
        assert event.state_change.to == change.value


def test_series_cover_the_window():
    minutes = loader.load_incident(INCIDENT).window.minutes
    assert len(loader.load_system_model_json(INCIDENT).exogenous.demand_rps) == minutes
    for series in loader.load_metrics(INCIDENT):
        assert [p.t for p in series.points] == list(range(minutes))


def test_observed_breach_is_22_minutes():
    errors = next(s for s in loader.load_metrics(INCIDENT) if s.name == "checkout_5xx_rate")
    assert sum(1 for p in errors.points if p.value > 0.05) == 22
    assert max(p.value for p in errors.points) == 0.38


def test_ground_truth_shape():
    truth = loader.load_ground_truth(INCIDENT)
    assert truth["root_cause_hypothesis_id"] == "H1"
    assert sorted(truth["rejected_hypothesis_ids"]) == ["H2", "H3", "H4"]
    assert sorted(truth["preventing_intervention_ids"]) == ["I1", "I2", "I4"]
