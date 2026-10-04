"""Root-cause selection. Owner: Vinayak.

FOUNDATION STUB: picks the highest-confidence surviving hypothesis and returns a
hard-coded causal chain for it. The signature is frozen.
"""

from __future__ import annotations

from contracts.models import CausalLink, Event, Evidence, Hypothesis, RootCause

_CHAINS: dict[str, tuple[str, list[tuple[str, str]], list[str]]] = {
    "H1": (
        "CHG-881 cut payment-svc's DB connection pool from 50 to 10; when settlement-reconcile took 8 of "
        "those connections, checkout requests queued for a connection, timed out and retried.",
        [
            ("E-001", "Pool max cut from 50 to 10"),
            ("E-004", "Batch job takes 8 of the 10 connections"),
            ("E-005", "Requests queue for a connection; pool wait p99 reaches 900 ms"),
            ("E-006", "Requests time out; checkout 5xx exceeds 5%"),
            ("E-007", "Retries amplify load; 5xx peaks near 38%"),
            ("E-009", "Batch job ends and frees its connections"),
            ("E-010", "Error rate returns to baseline"),
        ],
        [
            "CHG-870 moved settlement-reconcile from 02:00 to 14:30 three days earlier",
            "Retry policy (3 retries, no jitter) amplified load",
            "No capacity check on config changes that reduce pool size",
        ],
    ),
}


def determine_root_cause(hypotheses: list[Hypothesis], evidence: list[Evidence], timeline: list[Event]) -> RootCause:
    survivors = [h for h in hypotheses if h.status in ("supported", "confirmed")]
    if not survivors:
        raise ValueError("no surviving hypothesis to promote to root cause")
    best = max(survivors, key=lambda h: (h.confidence, len(h.supporting_evidence_ids)))
    statement, chain, factors = _CHAINS.get(best.id, (best.mechanism, [], []))
    return RootCause(
        hypothesis_id=best.id,
        statement=statement,
        causal_chain=[CausalLink(event_id=eid, effect=effect) for eid, effect in chain],
        contributing_factors=factors,
        confidence=best.confidence,
    )
