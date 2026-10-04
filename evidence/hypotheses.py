"""Competing hypotheses + testing. Owner: Vinayak.

seed_hypotheses reads the timeline and proposes one hypothesis per suspicious signal family:

- pool:       a state change that shrinks a connection pool, plus a job that takes connections from it
- regression: a code deploy shortly before onset
- gateway:    an external dependency notice shortly before onset
- database:   database-flavoured errors (SQL/connection exceptions) in the logs

Ids follow that fixed family order (H1..H4), so replay runs always produce the same ids.
Deterministic: no clock, no randomness, no network, no LLM.
"""

from __future__ import annotations

from contracts.models import Event, Evidence, Hypothesis, HypothesisTest

FAMILIES = ("pool", "regression", "gateway", "database")
PRIOR = 0.25


def _clock(e: Event) -> str:
    return e.ts[11:16]


def _onset(timeline: list[Event]) -> Event | None:
    alerts = [e for e in timeline if e.kind == "alert"]
    return min(alerts, key=lambda e: (e.t, e.ts)) if alerts else None


def _pool(timeline: list[Event]) -> tuple[str, str] | None:
    cut = next((e for e in timeline if e.state_change and "pool" in e.state_change.param
                and float(e.state_change.to) < float(e.state_change.from_)), None)
    job = next((e for e in timeline if e.kind == "job_start" and e.attributes.get("connections")), None)
    if not cut:
        return None
    change = cut.attributes.get("change_id", cut.id)
    sc = cut.state_change
    title = f"Connection-pool exhaustion: {change}" + (f" plus {job.attributes['job']} contention" if job else "")
    mechanism = f"{change} cut the {cut.source} DB connection pool from {sc.from_} to {sc.to} at {_clock(cut)}"
    if job:
        mechanism += (f"; when {job.attributes['job']} started at {_clock(job)} it took "
                      f"{job.attributes['connections']} of them")
    mechanism += ", so checkout requests queued for a connection, timed out and retried."
    return title, mechanism


def _regression(timeline: list[Event]) -> tuple[str, str] | None:
    onset = _onset(timeline)
    deploy = next((e for e in timeline if e.kind == "deploy" and not e.attributes.get("rollback")
                   and (onset is None or e.t <= onset.t)), None)
    if not deploy:
        return None
    version = deploy.attributes.get("version", "the new build")
    lead = f" ({onset.t - deploy.t} minutes before the first alert)" if onset else ""
    return (f"Code regression in {version}",
            f"The {version} deploy at {_clock(deploy)}{lead} introduced a bug that fails payment requests.")


def _gateway(timeline: list[Event]) -> tuple[str, str] | None:
    onset = _onset(timeline)
    notice = next((e for e in timeline if e.kind == "external" and (onset is None or e.t <= onset.t)), None)
    if not notice:
        return None
    region = notice.attributes.get("region")
    return ("Payment gateway degradation",
            f"The external {notice.source} slowed down (provider notice at {_clock(notice)}"
            + (f", {region} latency" if region else "") + "), so checkout calls to it timed out.")


def _database(timeline: list[Event]) -> tuple[str, str] | None:
    hit = next((e for e in timeline if e.kind == "log" and ("SQL" in e.summary or "Connection" in e.summary)), None)
    if not hit:
        return None
    return ("Database server overload",
            "The payments database was saturated and could not serve queries in time; the "
            f"connection errors first logged at {_clock(hit)} are the database refusing work.")


_DETECTORS = {"pool": _pool, "regression": _regression, "gateway": _gateway, "database": _database}


def candidates(incident_id: str, timeline: list[Event]) -> list[tuple[str, Hypothesis]]:
    """(family, hypothesis) pairs in id order. Shared with the evidence engine, which needs the family."""
    found = [(family, _DETECTORS[family](timeline)) for family in FAMILIES]
    return [
        (family, Hypothesis(id=f"H{n}", title=title, mechanism=mechanism, origin="seed",
                            status="proposed", confidence=PRIOR))
        for n, (family, (title, mechanism)) in enumerate(((f, d) for f, d in found if d), 1)
    ]


def seed_hypotheses(incident_id: str, timeline: list[Event]) -> list[Hypothesis]:
    return [h for _, h in candidates(incident_id, timeline)]


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
