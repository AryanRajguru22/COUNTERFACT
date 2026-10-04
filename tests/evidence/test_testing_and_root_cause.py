"""Hypothesis testing rejects H2-H4 for specific reasons and confirms H1 with a causal chain."""

import pytest

from contracts.models import Evidence, Hypothesis, Investigation, RootCause
from data.loader import load_ground_truth, load_incident
from evidence import build_timeline, determine_root_cause, gather_evidence, seed_hypotheses, test_hypothesis

INCIDENT = "INC-2041"


def _pipeline():
    timeline = build_timeline(INCIDENT)
    hypotheses = seed_hypotheses(INCIDENT, timeline)
    evidence = list({e.id: e for h in hypotheses for e in gather_evidence(INCIDENT, h)}.values())
    tested = [test_hypothesis(h, [e for e in evidence if h.id in e.stance]) for h in hypotheses]
    return timeline, tested, evidence, determine_root_cause(tested, evidence, timeline)


def _tested():
    return {h.id: h for h in _pipeline()[1]}


def test_h2_h3_h4_are_rejected_with_specific_reasons():
    tested = _tested()
    assert sorted(h for h, v in tested.items() if v.status == "rejected") == ["H2", "H3", "H4"]
    for hid, must_mention in {"H2": "Rollback", "H3": "gateway.authorize p99", "H4": "payments-db CPU"}.items():
        h = tested[hid]
        assert h.rejection_reason and must_mention in h.rejection_reason
        assert h.refuting_evidence_ids and h.refuting_evidence_ids[0] in h.rejection_reason
        assert h.confidence < 0.2


def test_rejection_reasons_differ_per_hypothesis():
    reasons = [h.rejection_reason for h in _tested().values() if h.rejection_reason]
    assert len(set(reasons)) == 3


def test_every_test_records_a_prediction_and_observation():
    for h in _tested().values():
        assert len(h.tests) == len(h.supporting_evidence_ids) + len(h.refuting_evidence_ids)
        assert all(t.prediction and t.observed for t in h.tests)
        assert sum(t.passed for t in h.tests) == len(h.supporting_evidence_ids)


def test_h1_survives_with_high_confidence():
    h1 = _tested()["H1"]
    assert h1.status == "supported" and h1.rejection_reason is None
    assert not h1.refuting_evidence_ids and h1.confidence >= 0.9


def test_h1_is_the_root_cause_and_matches_ground_truth():
    truth = load_ground_truth(INCIDENT)
    _, tested, _, root_cause = _pipeline()
    assert root_cause.hypothesis_id == truth["root_cause_hypothesis_id"] == "H1"
    assert sorted(h.id for h in tested if h.status == "rejected") == sorted(truth["rejected_hypothesis_ids"])
    assert root_cause.confidence == next(h.confidence for h in tested if h.id == "H1")
    assert "CHG-881" in root_cause.statement and "H2, H3, H4 were rejected" in root_cause.statement


def test_causal_chain_runs_from_pool_cut_through_batch_contention_to_recovery():
    timeline, _, _, root_cause = _pipeline()
    order = {e.id: i for i, e in enumerate(timeline)}
    chain = [link.event_id for link in root_cause.causal_chain]
    assert chain == sorted(chain, key=order.get)
    assert chain[:2] == ["E-001", "E-004"] and chain[-2:] == ["E-009", "E-010"]
    assert {"E-005", "E-006", "E-007", "E-011", "E-012", "E-013"} <= set(chain)
    assert not {"E-002", "E-003", "E-008"} & set(chain)  # deploy, gateway notice, rollback belong to rejected rivals
    assert all(link.effect for link in root_cause.causal_chain)


def test_contributing_factors_name_the_reschedule_retry_policy_and_rollback():
    factors = " ".join(_pipeline()[3].contributing_factors)
    for fact in ("CHG-870", "no capacity check", "no jitter", "rollback"):
        assert fact in factors


def test_no_surviving_hypothesis_raises():
    _, tested, evidence, _ = _pipeline()
    rejected = [h.model_copy(update={"status": "rejected"}) for h in tested]
    with pytest.raises(ValueError):
        determine_root_cause(rejected, evidence, [])


def test_hypothesis_without_evidence_stays_under_test():
    h = seed_hypotheses(INCIDENT, build_timeline(INCIDENT))[0]
    assert test_hypothesis(h, []).status == "testing"


def test_every_output_validates_against_its_contract():
    timeline, tested, evidence, root_cause = _pipeline()
    assert all(Hypothesis.model_validate(h.model_dump(by_alias=True)) == h for h in tested)
    assert all(Evidence.model_validate(e.model_dump(by_alias=True)) == e for e in evidence)
    assert RootCause.model_validate(root_cause.model_dump(by_alias=True)) == root_cause
    investigation = Investigation(id="t", incident=load_incident(INCIDENT), stage="root_cause", timeline=timeline,
                                  hypotheses=tested, evidence=evidence, root_cause=root_cause)
    assert Investigation.model_validate_json(investigation.model_dump_json()) == investigation


def test_agent_tools_reach_the_same_result():
    from agent import tools

    timeline = tools.call("build_timeline", INCIDENT)
    hypotheses = tools.call("seed_hypotheses", INCIDENT, timeline)
    evidence = list({e.id: e for h in hypotheses for e in tools.call("gather_evidence", INCIDENT, h)}.values())
    tested = [tools.call("test_hypothesis", h, [e for e in evidence if h.id in e.stance]) for h in hypotheses]
    assert tools.call("determine_root_cause", tested, evidence, timeline) == _pipeline()[3]


def test_pipeline_is_deterministic():
    assert _pipeline() == _pipeline()
