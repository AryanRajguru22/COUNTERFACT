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


def _h(hid, **update):
    h = Hypothesis(id=hid, title=f"{hid} title", mechanism=f"{hid} mechanism", origin="seed",
                   status="proposed", confidence=0.25)
    return h.model_copy(update=update)


def _ev(eid, weight, **stance):
    return Evidence(id=eid, kind="metric", description=f"{eid} observation.", stance=stance, weight=weight)


def test_hypothesis_without_evidence_stays_proposed_at_zero_confidence():
    h = seed_hypotheses(INCIDENT, build_timeline(INCIDENT))[0]
    result = test_hypothesis(h, [])
    assert (result.status, result.confidence, result.tests) == ("proposed", 0.0, [])


def test_unseen_hypothesis_id_is_scored_from_its_stances():
    result = test_hypothesis(_h("H7"), [_ev("EV-90", 0.6, H7="supports"), _ev("EV-91", 0.2, H7="refutes")])
    assert result.status == "supported"
    assert result.confidence == 0.75  # support / (support + refute)
    assert result.supporting_evidence_ids == ["EV-90"] and result.refuting_evidence_ids == ["EV-91"]


def test_rejected_only_when_refuting_weight_exceeds_supporting_weight():
    strong_refutation = _ev("EV-90", 0.9, H7="refutes")
    outweighed = test_hypothesis(_h("H7"), [strong_refutation, _ev("EV-91", 0.95, H7="supports"),
                                            _ev("EV-92", 0.9, H7="supports")])
    assert outweighed.status == "supported" and outweighed.rejection_reason is None
    tied = test_hypothesis(_h("H7"), [_ev("EV-90", 0.5, H7="refutes"), _ev("EV-91", 0.5, H7="supports")])
    assert tied.status == "supported" and tied.confidence == 0.5


def test_confidence_is_capped_at_095():
    assert test_hypothesis(_h("H7"), [_ev("EV-90", 0.9, H7="supports")]).confidence == 0.95


def test_rejection_reason_leads_with_the_strongest_refutation():
    result = test_hypothesis(_h("H7"), [_ev("EV-90", 0.4, H7="refutes"), _ev("EV-91", 0.8, H7="refutes"),
                                        _ev("EV-92", 0.7, H7="supports")])
    assert result.status == "rejected"
    assert result.rejection_reason.startswith("Refuted by EV-91: EV-91 observation.")
    assert "circumstantial" not in result.rejection_reason  # 0.7 is strong support, not weak


def test_tied_confidence_prefers_the_hypothesis_whose_predictions_all_pass():
    mixed = test_hypothesis(_h("H1"), [_ev("EV-90", 0.8, H1="supports"), _ev("EV-91", 0.8, H1="supports"),
                                       _ev("EV-92", 0.4, H1="refutes")])
    clean = test_hypothesis(_h("H2"), [_ev("EV-93", 0.8, H2="supports")])
    mixed = mixed.model_copy(update={"confidence": clean.confidence})  # force a tie
    assert determine_root_cause([mixed, clean], [], []).hypothesis_id == "H2"


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
