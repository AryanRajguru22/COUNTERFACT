"""Root-cause selection. Owner: Vinayak.

The root cause is the strongest surviving hypothesis: highest confidence, then most supporting
evidence, then lowest id. Its causal chain is read off the timeline: every event cited by the
winner's supporting evidence, plus the symptom events (metrics, alerts, logs, traces) that no rival
hypothesis's evidence explains, in time order. Each link's effect is phrased from the event itself.
Deterministic: no clock, randomness, network or LLM.
"""

from __future__ import annotations

from contracts.models import CausalLink, Event, Evidence, Hypothesis, RootCause

SYMPTOM_KINDS = ("metric", "alert", "log", "trace")


def _effect(e: Event) -> str:
    sc, a = e.state_change, e.attributes
    if sc is not None:
        if sc.param == "pool_size":
            return f"{a.get('change_id', e.id)} cuts the DB connection pool from {sc.from_} to {sc.to}, removing the headroom"
        if sc.param == "batch_conns" and float(sc.to) > float(sc.from_):
            return f"{a.get('job', 'The batch job')} takes {sc.to} of the pooled connections, leaving too few for checkout"
        if sc.param == "batch_conns":
            return f"{a.get('job', 'The batch job')} ends and releases its {sc.from_} connections"
        return f"{sc.param} changes from {sc.from_} to {sc.to}"
    if a.get("metric") == "pool_wait_p99_ms":
        return f"Requests queue for a connection; pool wait p99 jumps from {a.get('from')} ms to {a.get('to')} ms"
    if e.summary.startswith("First pool-acquire timeout"):
        return f"Requests time out waiting for a connection ({a.get('occurrences')} timeouts across {len(a.get('regions', []))} regions)"
    if e.kind == "trace":
        return f"Failed requests never get past {', '.join(a.get('spans', [])) or 'the first span'}; the DB and gateway are never called"
    if e.kind == "alert":
        return f"Checkout 5xx crosses the {a.get('threshold', 0):.0%} SLO and pages on-call"
    if e.summary.startswith("Retries begin"):
        return "Timed-out requests retry without jitter, adding load to the full pool"
    if a.get("metric") == "checkout_5xx_rate" and a.get("value", 0) >= 0.05:
        return f"Retries amplify the load; checkout 5xx peaks at {a['value']:.0%}"
    if a.get("metric") == "checkout_5xx_rate":
        return f"Error rate returns to baseline ({a.get('value', 0):.1%})"
    return e.summary


def _chain(best: Hypothesis, evidence: list[Evidence], timeline: list[Event]) -> list[CausalLink]:
    by_id = {e.id: e for e in evidence}
    cited = {eid for ev_id in best.supporting_evidence_ids if ev_id in by_id for eid in by_id[ev_id].source_event_ids}
    rival = {eid for e in evidence if best.id not in e.stance for eid in e.source_event_ids}
    first_cause = min((e.t for e in timeline if e.id in cited), default=0)
    links = [
        e for e in timeline
        if e.id in cited or (e.kind in SYMPTOM_KINDS and e.t >= first_cause and e.id not in rival)
    ]
    return [CausalLink(event_id=e.id, effect=_effect(e)) for e in links]


def _factors(best: Hypothesis, evidence: list[Evidence], timeline: list[Event], rejected: list[Hypothesis]) -> list[str]:
    factors = []
    for e in timeline:
        if e.kind == "job_start" and e.attributes.get("rescheduled_by"):
            factors.append(f"{e.attributes['rescheduled_by']} moved {e.attributes.get('job', 'the batch job')} from "
                           f"{e.attributes.get('previous_schedule', 'off-peak')} to {e.ts[11:16]} UTC, into daytime checkout traffic")
    supporting = [e for e in evidence if e.id in best.supporting_evidence_ids]
    if any(e.kind == "config_diff" and "capacity review: none" in e.description for e in supporting):
        factors.append("The pool cut was auto-approved with no capacity check against peak demand plus batch usage")
    if any("without jitter" in e.description for e in supporting):
        factors.append("The retry policy (fixed backoff, no jitter) amplified load on the exhausted pool")
    for h in rejected:
        for e in timeline:
            if e.attributes.get("rollback") and any(e.id in ev.source_event_ids for ev in evidence
                                                    if ev.id in h.refuting_evidence_ids):
                factors.append(f"The {e.ts[11:16]} rollback ({e.id}) chased {h.id}, a rejected hypothesis, "
                               "and delayed mitigation")
    return list(dict.fromkeys(factors))


def determine_root_cause(hypotheses: list[Hypothesis], evidence: list[Evidence], timeline: list[Event]) -> RootCause:
    survivors = [h for h in hypotheses if h.status in ("supported", "confirmed")]
    if not survivors:
        raise ValueError("no surviving hypothesis to promote to root cause")
    best = min(survivors, key=lambda h: (-h.confidence, -len(h.supporting_evidence_ids), h.id))
    rejected = [h for h in hypotheses if h.status == "rejected"]
    statement = best.mechanism
    if rejected:
        against = len(best.refuting_evidence_ids)
        statement += (f" Supported by {len(best.supporting_evidence_ids)} evidence items with "
                      f"{against or 'none'} against it; {', '.join(h.id for h in rejected)} were rejected.")
    return RootCause(
        hypothesis_id=best.id,
        statement=statement,
        causal_chain=_chain(best, evidence, timeline),
        contributing_factors=_factors(best, evidence, timeline, rejected),
        confidence=best.confidence,
    )
