"""Competing hypotheses + testing. Owner: Vinayak.

FOUNDATION STUB: seed hypotheses are hard-coded for INC-2041, and testing is a
plain weighted vote of evidence stances. Real reasoning replaces the bodies;
the signatures are frozen.
"""

from __future__ import annotations

from contracts.models import Event, Evidence, Hypothesis, HypothesisTest

_SEEDS: dict[str, list[tuple[str, str, str]]] = {
    "INC-2041": [
        ("H1", "Connection-pool exhaustion: CHG-881 plus batch-job contention",
         "CHG-881 cut the pool to 10; the batch job took 8 of them, so checkout requests queued for a "
         "connection, timed out and retried."),
        ("H2", "Code regression in v2.4.1",
         "The v2.4.1 deploy at 14:20 introduced a bug that fails payment requests."),
        ("H3", "Payment gateway degradation",
         "The external payment gateway slowed down, so checkout calls to it timed out."),
        ("H4", "Database server overload",
         "The payments database was saturated and could not serve queries in time."),
    ],
}


def seed_hypotheses(incident_id: str, timeline: list[Event]) -> list[Hypothesis]:
    return [
        Hypothesis(id=hid, title=title, mechanism=mechanism, origin="seed", status="proposed", confidence=0.25)
        for hid, title, mechanism in _SEEDS.get(incident_id, [])
    ]


def test_hypothesis(hypothesis: Hypothesis, evidence: list[Evidence]) -> Hypothesis:
    supporting = [e for e in evidence if e.stance.get(hypothesis.id) == "supports"]
    refuting = [e for e in evidence if e.stance.get(hypothesis.id) == "refutes"]
    support = sum(e.weight for e in supporting)
    refute = sum(e.weight for e in refuting)
    rejected = refute > support
    confidence = 0.0 if support + refute == 0 else min(0.95, support / (support + refute))
    strongest_refutation = max(refuting, key=lambda e: e.weight, default=None)
    return hypothesis.model_copy(update={
        "status": "rejected" if rejected else "supported",
        "confidence": round(confidence, 2),
        "supporting_evidence_ids": [e.id for e in supporting],
        "refuting_evidence_ids": [e.id for e in refuting],
        "tests": [
            HypothesisTest(
                prediction=f"If {hypothesis.id} is true, {e.id} should support it",
                observed=e.description,
                passed=e.stance[hypothesis.id] == "supports",
            )
            for e in supporting + refuting
        ],
        "rejection_reason": strongest_refutation.description if rejected and strongest_refutation else None,
    })


# pytest would otherwise collect this engine function as a test (its name starts with "test_").
test_hypothesis.__test__ = False
