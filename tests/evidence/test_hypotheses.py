"""Hypothesis seeding proposes exactly four competing explanations derived from the timeline."""

from contracts.models import Hypothesis
from evidence import build_timeline, seed_hypotheses

INCIDENT = "INC-2041"


def _seeds():
    return seed_hypotheses(INCIDENT, build_timeline(INCIDENT))


def test_exactly_four_hypotheses_h1_to_h4():
    hypotheses = _seeds()
    assert [h.id for h in hypotheses] == ["H1", "H2", "H3", "H4"]
    assert all(h.status == "proposed" and h.origin == "seed" and h.confidence == 0.25 for h in hypotheses)


def test_h1_is_pool_exhaustion_and_the_rest_are_the_plausible_alternatives():
    h1, h2, h3, h4 = _seeds()
    assert "pool exhaustion" in h1.title.lower() and "CHG-881" in h1.title
    assert "50 to 10" in h1.mechanism and "settlement-reconcile" in h1.mechanism
    assert "v2.4.1" in h2.title
    assert "gateway" in h3.title.lower()
    assert "database" in h4.title.lower()


def test_hypotheses_are_grounded_in_the_timeline():
    _, h2, h3, _ = _seeds()
    assert "14:20" in h2.mechanism and "12 minutes" in h2.mechanism
    assert "14:28" in h3.mechanism and "EU" in h3.mechanism


def test_no_signals_means_no_hypotheses():
    assert seed_hypotheses(INCIDENT, []) == []


def test_hypotheses_validate_against_the_contract():
    for h in _seeds():
        assert Hypothesis.model_validate(h.model_dump(by_alias=True)) == h


def test_seeding_is_deterministic():
    assert _seeds() == _seeds()
