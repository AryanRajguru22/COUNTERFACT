"""Evidence follows the data: change the raw telemetry and the stances and wording change with it.

Each test edits one loader's output for INC-2041 and rebuilds the evidence catalogue from it.
"""

import pytest

from data import loader
from evidence import evidence as engine
from evidence.evidence import catalogue, prediction_for

INCIDENT = "INC-2041"


@pytest.fixture
def perturbed(monkeypatch):
    def build(**loaders):
        for name, fake in loaders.items():
            original = getattr(loader, name)
            monkeypatch.setattr(loader, name, lambda incident_id, f=fake, o=original: f(o(incident_id)))
        engine._catalogue.cache_clear()
        return {e.id: e for e in catalogue(INCIDENT)}

    yield build
    monkeypatch.undo()
    engine._catalogue.cache_clear()


def _edit_series(name, edit):
    def fake(series):
        out = []
        for s in series:
            if s.name == name:
                s = s.model_copy(update={"points": [p.model_copy(update={"value": edit(p.t, p.value)})
                                                    for p in s.points]})
            out.append(s)
        return out
    return fake


def test_a_rollback_that_fixes_errors_supports_the_regression(perturbed):
    ev = perturbed(load_metrics=_edit_series("checkout_5xx_rate", lambda t, v: 0.004 if t >= 43 else v))
    assert ev["EV-05"].stance == {"H2": "supports"}
    assert "did not reduce" not in ev["EV-05"].description
    assert "reduced errors" in ev["EV-05"].description


def test_a_saturated_database_supports_the_overload_hypothesis(perturbed):
    ev = perturbed(load_metrics=lambda series: _edit_series("db_server_connections", lambda t, v: 190)(
        _edit_series("db_cpu_pct", lambda t, v: 95)(series)))
    assert ev["EV-09"].stance["H4"] == "supports"
    assert "spare capacity" not in ev["EV-09"].description


def test_clock_times_come_from_the_incident_window(perturbed):
    def shift(incident):
        return incident.model_copy(update={"window": incident.window.model_copy(update={"start": "2026-09-28T09:00:00Z"})})
    ev = perturbed(load_incident=shift)
    assert "09:20" in ev["EV-10"].description and "14:20" not in ev["EV-10"].description


def test_version_names_come_from_the_change_records(perturbed):
    rename = {"v2.4.0": "v3.0.0", "v2.4.1": "v3.0.1"}

    def fake(deploys):
        out = []
        for c in deploys:
            change = {k: rename.get(v, v) if isinstance(v, str) else v for k, v in c["change"].items()}
            out.append({**c, "change": change})
        return out
    ev = perturbed(load_deploys=fake)
    for eid in ("EV-05", "EV-15", "EV-16"):
        text = ev[eid].description + " " + (prediction_for(ev[eid], "H2") or "")
        assert "v3.0" in text and "v2.4" not in text, eid
    assert "v3.0.1" in prediction_for(ev["EV-06"], "H2")


def test_pool_error_quote_comes_from_the_log():
    ev = {e.id: e for e in catalogue(INCIDENT)}
    assert "total=10, active=10, idle=0, waiting=40" in ev["EV-17"].description
