"""Evidence engine stubs honour the frozen signatures and reach the ground truth deterministically."""

from data.loader import load_ground_truth
from evidence import build_timeline, determine_root_cause, gather_evidence, seed_hypotheses, test_hypothesis

INCIDENT = "INC-2041"


def _pipeline():
    timeline = build_timeline(INCIDENT)
    hypotheses = seed_hypotheses(INCIDENT, timeline)
    evidence = list({e.id: e for h in hypotheses for e in gather_evidence(INCIDENT, h)}.values())
    tested = [test_hypothesis(h, [e for e in evidence if h.id in e.stance]) for h in hypotheses]
    return timeline, tested, evidence, determine_root_cause(tested, evidence, timeline)


def test_timeline_is_ordered():
    timeline = build_timeline(INCIDENT)
    assert [e.t for e in timeline] == sorted(e.t for e in timeline)
    assert {e.id for e in timeline if e.state_change} == {"E-001", "E-004", "E-009"}


def test_seed_hypotheses_are_h1_to_h4():
    hypotheses = seed_hypotheses(INCIDENT, build_timeline(INCIDENT))
    assert [h.id for h in hypotheses] == ["H1", "H2", "H3", "H4"]
    assert all(h.status == "proposed" for h in hypotheses)


def test_pipeline_matches_ground_truth():
    truth = load_ground_truth(INCIDENT)
    _, tested, _, root_cause = _pipeline()
    assert root_cause.hypothesis_id == truth["root_cause_hypothesis_id"]
    rejected = {h.id: h for h in tested if h.status == "rejected"}
    assert sorted(rejected) == sorted(truth["rejected_hypothesis_ids"])
    for h in rejected.values():
        assert h.rejection_reason and h.refuting_evidence_ids


def test_root_cause_chain_references_timeline_events():
    timeline, _, _, root_cause = _pipeline()
    ids = {e.id for e in timeline}
    assert root_cause.causal_chain and all(link.event_id in ids for link in root_cause.causal_chain)


def test_pipeline_is_deterministic():
    assert _pipeline() == _pipeline()
