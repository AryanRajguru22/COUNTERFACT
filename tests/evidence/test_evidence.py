"""Evidence is derived from the raw data, anchored to the timeline and scored per hypothesis."""

from contracts.models import Evidence
from evidence import build_timeline, gather_evidence, seed_hypotheses
from evidence.evidence import catalogue, prediction_for

INCIDENT = "INC-2041"


def _setup():
    timeline = build_timeline(INCIDENT)
    return timeline, seed_hypotheses(INCIDENT, timeline), catalogue(INCIDENT)


def _by(evidence, hypothesis_id, stance):
    return [e for e in evidence if e.stance.get(hypothesis_id) == stance]


def test_evidence_ids_are_unique_and_sorted():
    _, _, evidence = _setup()
    assert [e.id for e in evidence] == [f"EV-{n:02d}" for n in range(1, 18)]


def test_evidence_ids_keep_the_playbook_meanings():
    _, _, evidence = _setup()
    ev = {e.id: e for e in evidence}
    assert "pool.acquire accounts for" in ev["EV-01"].description
    assert "pinned at the 10-connection cap" in ev["EV-02"].description
    assert ev["EV-03"].kind == "config_diff"
    assert "after settlement-reconcile starts" in ev["EV-04"].description
    assert ev["EV-05"].stance == {"H2": "refutes"} and "Rollback" in ev["EV-05"].description
    assert ev["EV-06"].stance == {"H2": "refutes"} and "by version" in ev["EV-06"].description
    assert ev["EV-07"].stance == {"H3": "refutes"} and "gateway.authorize p99" in ev["EV-07"].description
    assert ev["EV-08"].stance == {"H3": "refutes"} and "regions" in ev["EV-08"].description
    assert ev["EV-09"].stance["H4"] == "refutes" and "CPU" in ev["EV-09"].description
    for eid, hid in (("EV-10", "H2"), ("EV-11", "H3"), ("EV-12", "H4")):
        assert ev[eid].stance[hid] == "supports" and ev[eid].weight <= 0.4


def test_an_analysis_that_finds_nothing_does_not_shift_later_ids(monkeypatch):
    from evidence import evidence as engine

    before = {e.id: e for e in catalogue(INCIDENT)}
    first_id, _ = engine.ANALYSES[0]
    monkeypatch.setattr(engine, "ANALYSES", ((first_id, lambda d: None),) + engine.ANALYSES[1:])
    engine._catalogue.cache_clear()
    try:
        after = {e.id: e for e in catalogue(INCIDENT)}
    finally:
        monkeypatch.undo()
        engine._catalogue.cache_clear()
    assert first_id not in after
    assert after == {k: v for k, v in before.items() if k != first_id}


def test_evidence_is_anchored_to_timeline_events_and_known_hypotheses():
    timeline, hypotheses, evidence = _setup()
    event_ids, hypothesis_ids = {e.id for e in timeline}, {h.id for h in hypotheses}
    for e in evidence:
        assert set(e.source_event_ids) <= event_ids
        assert e.stance and set(e.stance) <= hypothesis_ids
        assert e.description


def test_every_hypothesis_has_evidence_and_a_prediction_for_each_item():
    _, hypotheses, _ = _setup()
    for h in hypotheses:
        items = gather_evidence(INCIDENT, h)
        assert items and all(h.id in e.stance for e in items)
        assert all(prediction_for(e, h.id) for e in items)


def test_h1_is_supported_and_never_refuted():
    _, _, evidence = _setup()
    assert len(_by(evidence, "H1", "supports")) >= 5
    assert not _by(evidence, "H1", "refutes")


def test_alternatives_are_plausible_but_strongly_refuted():
    _, _, evidence = _setup()
    for hid in ("H2", "H3", "H4"):
        supports, refutes = _by(evidence, hid, "supports"), _by(evidence, hid, "refutes")
        assert supports and max(e.weight for e in supports) <= 0.4  # a weak reason to suspect it
        assert len(refutes) >= 2 and max(e.weight for e in refutes) >= 0.85  # and a decisive one against it


def test_evidence_quotes_measured_numbers():
    _, _, evidence = _setup()
    text = " ".join(e.description for e in evidence)
    for fact in ("50 to 10", "18 of 200", "v2.4.0 33%", "v2.4.1 32%", "EU has 23%", "0 of 57 failed requests"):
        assert fact in text


def test_unknown_hypothesis_gets_no_evidence():
    _, hypotheses, _ = _setup()
    assert gather_evidence(INCIDENT, hypotheses[0].model_copy(update={"id": "H9"})) == []


def test_evidence_validates_against_the_contract():
    for e in catalogue(INCIDENT):
        assert Evidence.model_validate(e.model_dump(by_alias=True)) == e
        assert 0 <= e.weight <= 1


def test_evidence_is_deterministic_and_callers_cannot_corrupt_the_cache():
    first = catalogue(INCIDENT)
    first[0].stance["H1"] = "refutes"
    assert catalogue(INCIDENT) == catalogue(INCIDENT)
    assert catalogue(INCIDENT)[0].stance["H1"] == "supports"
