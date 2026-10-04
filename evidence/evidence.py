"""Evidence gathering. Owner: Vinayak.

Each analysis below reads raw incident data (metrics, traces, logs, change records, config) and
returns one evidence item: what was measured, which timeline events it is anchored to, which
hypothesis families it supports or refutes, and how much it should weigh.

Weights follow a fixed rubric, scaled by the measured effect where one exists:
  0.85-0.95  decisive: a natural experiment or a direct measurement of the mechanism
  0.6-0.8    strong: a measurement that fits one mechanism much better than the others
  0.3-0.4    weak: temporal coincidence or a symptom several mechanisms share

The catalogue is built once per incident and is fully deterministic (no clock, randomness, network or LLM).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from statistics import mean
from typing import Any, Callable

from contracts.models import Event, Evidence, EvidenceKind, Hypothesis
from data import loader
from evidence.hypotheses import candidates, family_of
from evidence.timeline import build_timeline

# (evidence id, description) -> {hypothesis id: prediction}; read by test_hypothesis
PREDICTIONS: dict[tuple[str, str], dict[str, str]] = {}


@dataclass
class _Finding:
    kind: EvidenceKind
    description: str
    events: list[str]
    weight: float
    stance: dict[str, str]  # family -> stance
    predictions: dict[str, str] = field(default_factory=dict)  # family -> what that hypothesis predicts


class _Data:
    """Everything an analysis may look at, loaded once."""

    def __init__(self, incident_id: str):
        self.timeline = build_timeline(incident_id)
        self.start = datetime.fromisoformat(loader.load_incident(incident_id).window.start.replace("Z", "+00:00"))
        self.metrics = {s.name: {p.t: p.value for p in s.points} for s in loader.load_metrics(incident_id)}
        self.model = loader.load_system_model_json(incident_id)
        self.traces = loader.load_traces(incident_id)
        self.logs = loader.load_logs(incident_id)
        self.changes = {d["id"]: d for d in loader.load_deploys(incident_id)}
        self.config = loader.load_config(incident_id)
        slo = self.model.slo.max_error_rate
        self.errors = self.metrics.get("checkout_5xx_rate", {})
        self.breach = [t for t, v in sorted(self.errors.items()) if v > slo]

    def clock(self, t: int) -> str:
        """Wall-clock HH:MM (UTC) of minute t of the incident window."""
        return (self.start + timedelta(minutes=t)).strftime("%H:%M")

    def change(self, kind: str) -> dict[str, Any] | None:
        """The first change record of a type (deploy, rollback, config_change, ...)."""
        return next((c for c in self.changes.values() if c["type"] == kind), None)

    def event(self, match: Callable[[Event], bool]) -> Event | None:
        return next((e for e in self.timeline if match(e)), None)

    def ids(self, *events: Event | None) -> list[str]:
        return [e.id for e in events if e is not None]

    def breach_traces(self) -> list[dict[str, Any]]:
        window = set(self.breach)
        return [x for x in self.traces if x["t"] in window]

    def baseline_traces(self) -> list[dict[str, Any]]:
        start = self.breach[0] if self.breach else 0
        return [x for x in self.traces if x["t"] < start - 1 and x["status"] == "ok"]


def _span(trace: dict[str, Any], name: str) -> int | None:
    return next((s["duration_ms"] for s in trace["spans"] if s["name"] == name), None)


def _p99(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, -(-len(ordered) * 99 // 100) - 1)] if ordered else 0.0


def _w(x: float) -> float:
    return round(min(0.95, max(0.05, x)), 2)


# ---------------------------------------------------------------- analyses supporting pool exhaustion


def _pool_wait_dominates(d: _Data) -> _Finding | None:
    traces = d.breach_traces()
    if not traces:
        return None
    share = sum(_span(x, "pool.acquire") or 0 for x in traces) / sum(x["duration_ms"] for x in traces)
    failed = [x for x in traces if x["status"] == "error"]
    pool_only = [x for x in failed if [s["name"] for s in x["spans"]] == ["pool.acquire"]]
    return _Finding(
        "trace",
        f"Across {len(traces)} sampled checkout traces in the breach window, pool.acquire accounts for "
        f"{share:.0%} of request time, and {len(pool_only)} of {len(failed)} failed traces timed out in "
        f"pool.acquire without ever reaching db.query or gateway.authorize.",
        d.ids(d.event(lambda e: e.kind == "trace")),
        _w(share + 0.1 * len(pool_only) / max(1, len(failed))),
        {"pool": "supports", "gateway": "refutes", "database": "refutes"},
        {"pool": "Failing requests spend their time waiting for a pool connection",
         "gateway": "Failing requests spend their time inside gateway.authorize",
         "database": "Failing requests spend their time inside db.query"},
    )


def _pool_saturated(d: _Data) -> _Finding | None:
    active, cap = d.metrics.get("pool_active_connections"), d.metrics.get("pool_max_connections")
    wait = d.metrics.get("pool_wait_p99_ms", {})
    if not (active and cap and d.breach):
        return None
    pinned = [t for t in d.breach if active[t] >= cap[t]]
    base_wait = wait.get(0, 0.0)
    return _Finding(
        "metric",
        f"Active pool connections pinned at the {cap[d.breach[0]]:.0f}-connection cap for {len(pinned)} of "
        f"{len(d.breach)} breach minutes; pool wait p99 rose from {base_wait:.0f} ms to "
        f"{max(wait.get(t, 0) for t in d.breach):.0f} ms.",
        d.ids(d.event(lambda e: e.kind == "job_start"), d.event(lambda e: e.attributes.get("metric") == "pool_wait_p99_ms")),
        _w(0.95 * len(pinned) / len(d.breach)),
        {"pool": "supports"},
        {"pool": "The pool sits at its cap for the whole breach and pool wait spikes"},
    )


def _capacity_shortfall(d: _Data) -> _Finding | None:
    cut = next((c for c in d.changes.values() if "pool" in c["change"]["key"]
                and float(c["change"]["to"]) < float(c["change"]["from"])), None)
    if not cut:
        return None
    params = d.model.params
    demand_conns = max(d.model.exogenous.demand_rps) * float(params["conn_hold_ms"]) / 1000
    batch = max((int(e.attributes.get("connections", 0)) for e in d.timeline if e.kind == "job_start"), default=0)
    need, before, after = demand_conns + batch, cut["change"]["from"], cut["change"]["to"]
    short = need > after
    return _Finding(
        "config_diff",
        f"{cut['id']} cut {cut['change']['key']} from {before} to {after} (approval: {cut['approval']}; "
        f"capacity review: {'yes' if cut.get('capacity_review') else 'none'}). "
        f"Checkout alone needs ~{demand_conns:.1f} connections (peak {max(d.model.exogenous.demand_rps):.0f} rps x "
        f"{params['conn_hold_ms']} ms hold) and the batch job holds {batch}, so peak demand is "
        f"{need:.1f} against {after}: {'over' if short else 'under'} capacity after the cut, well under the old {before}.",
        d.ids(d.event(lambda e: e.kind == "config_change"), d.event(lambda e: e.kind == "job_start")),
        0.85 if short and need <= before else 0.3,
        {"pool": "supports" if short else "refutes"},
        {"pool": "Demand for connections exceeds the new pool size only while the batch job runs"},
    )


def _onset_tracks_batch(d: _Data) -> _Finding | None:
    start = d.event(lambda e: e.kind == "job_start")
    end = d.event(lambda e: e.kind == "job_end")
    cut = d.event(lambda e: e.kind == "config_change")
    if not (start and end and d.breach):
        return None
    lag_on, lag_off = d.breach[0] - start.t, d.breach[-1] + 1 - end.t
    quiet = sum(1 for t in range(cut.t, start.t) if d.errors.get(t, 0) <= d.model.slo.max_error_rate) if cut else 0
    tight = 0 <= lag_on <= 3 and 0 <= lag_off <= 3
    job = start.attributes.get("job", "the batch job")
    verdict = (f"The pool cut alone ran for {quiet} minutes with no breach, so the cut and the batch job together "
               "are needed." if tight and quiet else "The breach does not track the batch job closely.")
    return _Finding(
        "metric",
        f"The breach starts {lag_on} min after {job} starts ({d.clock(start.t)}) and ends "
        f"{lag_off} min after it releases its connections ({d.clock(end.t)}). {verdict}",
        d.ids(cut, start, end, d.event(lambda e: e.kind == "alert")),
        0.8 if tight else 0.3,
        {"pool": "supports" if tight else "neutral"},
        {"pool": "Errors start when the batch job takes its connections and stop when it releases them"},
    )


def _batch_takes_connections(d: _Data) -> _Finding | None:
    start = d.event(lambda e: e.kind == "job_start")
    job = start.attributes.get("job") if start else None
    row = next((r for r in d.logs if job and r["service"] == job and r.get("connections")), None)
    if not row:
        return None
    return _Finding(
        "log",
        f"{job} log at {row['ts'][11:19]}: \"{row['message']}\", leaving "
        f"{d.config.get('payment-svc', {}).get('db.pool.max', 0) - row['connections']} connections for checkout traffic.",
        d.ids(d.event(lambda e: e.kind == "job_start")),
        0.85,
        {"pool": "supports"},
        {"pool": "The batch job draws its connections from the same payment-svc pool"},
    )


def _retry_amplification(d: _Data) -> _Finding | None:
    retries = [r for r in d.logs if r["message"].startswith("Retrying")]
    cfg = d.config.get("payment-svc", {})
    if not retries:
        return None
    return _Finding(
        "log",
        f"{len(retries)} retry logs during the breach: payments.authorize retries up to "
        f"{cfg.get('payments.authorize.retry_max', '?')} times with a fixed "
        f"{cfg.get('payments.authorize.retry_backoff_ms', '?')} ms backoff "
        f"({'with' if cfg.get('payments.authorize.retry_jitter') else 'without'} jitter), adding load to an already full pool.",
        d.ids(d.event(lambda e: e.summary.startswith("Retries begin")), d.event(lambda e: "Retry storm" in e.summary)),
        0.6,
        {"pool": "supports"},
        {"pool": "Timed-out requests retry immediately and deepen the queue for connections"},
    )


# ---------------------------------------------------------------- analyses against a code regression


def _rollback_no_effect(d: _Data) -> _Finding | None:
    rb = d.change("rollback")
    if not rb:
        return None
    before = mean(d.errors[t] for t in range(rb["t"] - 5, rb["t"]))
    after = mean(d.errors[t] for t in range(rb["completed_t"] + 1, rb["completed_t"] + 6))
    change = (after - before) / before if before else 0.0
    unchanged = abs(change) < 0.15
    bad, good = rb["change"]["from"], rb["change"]["to"]
    return _Finding(
        "deploy_record",
        f"Rollback {rb['id']} to {good} completed at {d.clock(rb['completed_t'])}; checkout 5xx "
        f"averaged {before:.1%} in the 5 minutes before and {after:.1%} in the 5 minutes after "
        f"({change:+.0%}). Removing {bad} {'did not reduce errors' if unchanged else 'reduced errors'}.",
        d.ids(d.event(lambda e: e.attributes.get("rollback"))),
        _w(0.95 - abs(change)) if unchanged else 0.2,
        {"regression": "refutes" if unchanged else "supports"},
        {"regression": f"Rolling back to {good} brings the error rate down"},
    )


def _errors_on_both_versions(d: _Data) -> _Finding | None:
    traces = d.breach_traces()
    rates = {}
    for version in sorted({x["version"] for x in traces}):
        mine = [x for x in traces if x["version"] == version]
        rates[version] = sum(x["status"] == "error" for x in mine) / len(mine)
    if len(rates) < 2:
        return None
    gap = max(rates.values()) - min(rates.values())
    dep = d.change("deploy")
    new, old = (dep["change"]["to"], dep["change"]["from"]) if dep else ("the new version", "the old version")
    return _Finding(
        "trace",
        "Breach-window failure rate by version in sampled traces: "
        + ", ".join(f"{v} {r:.0%}" for v, r in rates.items())
        + (". Both versions fail at a similar rate, and the old version fails as much as the new one." if gap < 0.15
           else ". The versions fail at clearly different rates."),
        d.ids(d.event(lambda e: e.kind == "deploy" and not e.attributes.get("rollback")),
              d.event(lambda e: e.attributes.get("rollback"))),
        _w(0.85 - gap),
        {"regression": "refutes" if gap < 0.15 else "supports"},
        {"regression": f"Requests served by {new} fail far more often than those served by {old}"},
    )


def _new_version_was_healthy(d: _Data) -> _Finding | None:
    dep = d.change("deploy")
    start = d.event(lambda e: e.kind == "job_start")
    if not (dep and start):
        return None
    window = [x for x in d.traces if dep["completed_t"] <= x["t"] < start.t and x["version"] == dep["change"]["to"]]
    failed = sum(x["status"] == "error" for x in window)
    peak = max(d.errors[t] for t in range(dep["completed_t"], start.t))
    healthy = failed == 0 and peak <= d.model.slo.max_error_rate
    return _Finding(
        "metric",
        f"{dep['change']['to']} served all traffic from {d.clock(dep['completed_t'])} to {d.clock(start.t)} "
        f"with checkout 5xx at most {peak:.1%} and {failed} failures in {len(window)} sampled traces. "
        + ("The errors started only when the batch job did." if healthy else "It was already failing before the batch job."),
        d.ids(d.event(lambda e: e.kind == "deploy" and not e.attributes.get("rollback")), start),
        0.8 if healthy else 0.2,
        {"regression": "refutes" if failed == 0 else "supports"},
        {"regression": f"Errors begin as soon as {dep['change']['to']} takes traffic"},
    )


def _diff_off_the_failing_path(d: _Data) -> _Finding | None:
    dep = d.change("deploy")
    if not dep:
        return None
    hot = ("pool", "db", "datasource", "payment", "authorize", "gateway", "retry")
    touched = [f for f in dep["files_changed"] if any(k in f.lower() for k in hot)]
    return _Finding(
        "deploy_record",
        f"{dep['id']} ({dep['change']['to']}) changed {len(dep['files_changed'])} files "
        f"({', '.join(dep['files_changed'])}); none of them is on the pool, database or gateway call path."
        if not touched else f"{dep['id']} touched files on the failing path: {', '.join(touched)}.",
        d.ids(d.event(lambda e: e.kind == "deploy" and not e.attributes.get("rollback"))),
        0.6,
        {"regression": "refutes" if not touched else "supports"},
        {"regression": f"The {dep['change']['to']} diff changes code on the checkout payment path"},
    )


# ---------------------------------------------------------------- analyses against gateway degradation


def _gateway_spans_normal(d: _Data) -> _Finding | None:
    base = [_span(x, "gateway.authorize") for x in d.baseline_traces()]
    during = [v for v in (_span(x, "gateway.authorize") for x in d.breach_traces()) if v is not None]
    failed = [x for x in d.breach_traces() if x["status"] == "error"]
    reached = sum(_span(x, "gateway.authorize") is not None for x in failed)
    if not (base and during):
        return None
    ratio = _p99(during) / _p99(base)
    return _Finding(
        "trace",
        f"gateway.authorize p99 is {_p99(during):.0f} ms during the breach vs {_p99(base):.0f} ms before it "
        f"(x{ratio:.2f}), and {reached} of {len(failed)} failed requests ever reached the gateway call.",
        d.ids(d.event(lambda e: e.kind == "external"), d.event(lambda e: e.kind == "trace")),
        _w(0.95 - (ratio - 1)) if ratio < 1.5 and reached == 0 else 0.2,
        {"gateway": "refutes" if ratio < 1.5 and reached == 0 else "supports"},
        {"gateway": "gateway.authorize latency rises and failing requests time out inside it"},
    )


def _errors_are_global(d: _Data) -> _Finding | None:
    notice = d.event(lambda e: e.kind == "external")
    failed = [x for x in d.breach_traces() if x["status"] == "error"]
    if not (notice and failed):
        return None
    region = notice.attributes.get("region", "")
    by_region: dict[str, int] = {}
    for x in failed:
        by_region[x["region"]] = by_region.get(x["region"], 0) + 1
    local = sum(n for r, n in by_region.items() if r.lower().startswith(region.lower()[:2]))
    share = local / len(failed)
    return _Finding(
        "external",
        f"The gateway notice covers {region} only, but failed checkouts are spread across "
        f"{len(by_region)} regions (" + ", ".join(f"{r} {n}" for r, n in sorted(by_region.items()))
        + f"); {region} has {share:.0%} of failures.",
        d.ids(notice, d.event(lambda e: e.summary.startswith("First pool-acquire timeout"))),
        _w(0.85 - share) if share < 0.5 else 0.2,
        {"gateway": "refutes" if share < 0.5 else "supports"},
        {"gateway": f"Failures concentrate in {region}, the region in the provider notice"},
    )


# ---------------------------------------------------------------- analyses against database overload


def _database_idle(d: _Data) -> _Finding | None:
    cpu, conns = d.metrics.get("db_cpu_pct"), d.metrics.get("db_server_connections")
    limit = d.config.get("payments-db", {}).get("max_connections")
    base = [v for v in (_span(x, "db.query") for x in d.baseline_traces()) if v is not None]
    during = [v for v in (_span(x, "db.query") for x in d.breach_traces()) if v is not None]
    if not (cpu and conns and limit and d.breach):
        return None
    peak_cpu = max(cpu[t] for t in d.breach)
    peak_conns = max(conns[t] for t in d.breach)
    idle = peak_cpu < 70 and peak_conns < 0.5 * limit
    return _Finding(
        "metric",
        f"payments-db CPU peaks at {peak_cpu:.0f}% and holds {peak_conns:.0f} of {limit} server connections "
        f"during the breach; db.query p99 is {_p99(during):.0f} ms vs {_p99(base):.0f} ms before. "
        + ("The database has spare capacity, so the client is starved for connections, not the server." if idle
           else "The database is under heavy load."),
        [],
        0.9 if idle else 0.2,
        {"database": "refutes" if idle else "supports", "pool": "supports" if idle else "neutral"},
        {"database": "Database CPU, connections and query latency are saturated",
         "pool": "The database has spare capacity while the client pool is exhausted"},
    )


def _errors_are_client_side(d: _Data) -> _Finding | None:
    db_errors = [r for r in d.logs if r["service"] == "payments-db" and r["level"] in ("WARN", "ERROR")]
    pool_errors = [r for r in d.logs if "Connection is not available" in r["message"]]
    if not pool_errors:
        return None
    return _Finding(
        "log",
        f"All {len(pool_errors)} connection errors come from the {pool_errors[0]['service']} client pool "
        f"(\"{pool_errors[0]['message']}\", {pool_errors[0].get('exception', 'pool timeout')}); payments-db logged "
        f"{len(db_errors)} warnings or errors during the incident.",
        d.ids(d.event(lambda e: e.summary.startswith("First pool-acquire timeout"))),
        0.75 if not db_errors else 0.2,
        {"database": "refutes" if not db_errors else "supports", "pool": "supports"},
        {"database": "payments-db logs slow queries, lock waits or refused connections",
         "pool": "Errors are raised by the client pool when no connection is free"},
    )


# ---------------------------------------------------------------- weak signals that make H2-H4 plausible


def _deploy_before_onset(d: _Data) -> _Finding | None:
    dep = d.event(lambda e: e.kind == "deploy" and not e.attributes.get("rollback"))
    if not (dep and d.breach):
        return None
    return _Finding(
        "deploy_record",
        f"{dep.attributes.get('version')} was deployed at {d.clock(dep.t)}, {d.breach[0] - dep.t} minutes "
        "before the breach began.",
        [dep.id], 0.3, {"regression": "supports"},
        {"regression": "A deploy lands shortly before the errors start"},
    )


def _gateway_notice(d: _Data) -> _Finding | None:
    notice = d.event(lambda e: e.kind == "external")
    if not (notice and d.breach):
        return None
    return _Finding(
        "external",
        f"The payment gateway provider posted a latency notice at {d.clock(notice.t)}, "
        f"{d.breach[0] - notice.t} minutes before the breach began.",
        [notice.id], 0.3, {"gateway": "supports"},
        {"gateway": "The provider reports degradation around the time errors start"},
    )


def _database_flavoured_errors(d: _Data) -> _Finding | None:
    rows = [r for r in d.logs if r.get("exception", "").startswith("SQL")]
    if not rows:
        return None
    return _Finding(
        "log",
        f"{len(rows)} error logs carry {rows[0]['exception']}, a database-related timeout.",
        d.ids(d.event(lambda e: e.summary.startswith("First pool-acquire timeout"))),
        0.35, {"database": "supports", "pool": "supports"},
        {"database": "Error logs show database timeouts",
         "pool": "Error logs show timeouts acquiring a database connection"},
    )


# Each analysis owns a fixed evidence id, so ids never shift when an analysis finds nothing.
# EV-01..EV-12 keep the meanings in the playbook (section 7.3); EV-13..EV-17 were added after it.
ANALYSES: tuple[tuple[str, Callable[[_Data], _Finding | None]], ...] = (
    ("EV-01", _pool_wait_dominates),
    ("EV-02", _pool_saturated),
    ("EV-03", _capacity_shortfall),
    ("EV-04", _onset_tracks_batch),
    ("EV-05", _rollback_no_effect),
    ("EV-06", _errors_on_both_versions),
    ("EV-07", _gateway_spans_normal),
    ("EV-08", _errors_are_global),
    ("EV-09", _database_idle),
    ("EV-10", _deploy_before_onset),
    ("EV-11", _gateway_notice),
    ("EV-12", _database_flavoured_errors),
    ("EV-13", _batch_takes_connections),
    ("EV-14", _retry_amplification),
    ("EV-15", _new_version_was_healthy),
    ("EV-16", _diff_off_the_failing_path),
    ("EV-17", _errors_are_client_side),
)


@lru_cache(maxsize=None)
def _catalogue(incident_id: str) -> tuple[Evidence, ...]:
    d = _Data(incident_id)
    ids = {family: h.id for family, h in candidates(incident_id, d.timeline)}
    items = []
    for evidence_id, analysis in ANALYSES:
        found = analysis(d)
        if found is None:
            continue
        stance = {ids[f]: s for f, s in found.stance.items() if f in ids}
        if not stance:
            continue
        ev = Evidence(id=evidence_id, kind=found.kind, description=found.description,
                      source_event_ids=found.events, stance=stance, weight=found.weight)
        PREDICTIONS[(ev.id, ev.description)] = {ids[f]: p for f, p in found.predictions.items() if f in ids}
        items.append(ev)
    return tuple(sorted(items, key=lambda e: e.id))


def catalogue(incident_id: str) -> list[Evidence]:
    """Every evidence item for an incident, across all hypotheses."""
    return [e.model_copy(deep=True) for e in _catalogue(incident_id)]


def prediction_for(evidence: Evidence, hypothesis_id: str) -> str | None:
    return PREDICTIONS.get((evidence.id, evidence.description), {}).get(hypothesis_id)


def gather_evidence(incident_id: str, hypothesis: Hypothesis) -> list[Evidence]:
    """Evidence bearing on one hypothesis.

    A seeded hypothesis gets the catalogue items that carry its id. An LLM-proposed one is placed in a
    signal family by family_of and takes that family's seeded stances and predictions under its own id,
    so test_hypothesis scores it like any other. One that matches no family gets no evidence.
    """
    items = catalogue(incident_id)
    if hypothesis.origin != "llm" or any(hypothesis.id in e.stance for e in items):
        return [e for e in items if hypothesis.id in e.stance]
    seeds = dict(candidates(incident_id, build_timeline(incident_id)))
    seed = seeds.get(family_of(hypothesis))
    if seed is None:
        return []
    mine = []
    for e in items:  # catalogue() hands out copies, so the shared cache keeps its stances
        if seed.id in e.stance:
            e.stance[hypothesis.id] = e.stance[seed.id]
            predictions = PREDICTIONS.setdefault((e.id, e.description), {})
            if seed.id in predictions:
                predictions[hypothesis.id] = predictions[seed.id]
            mine.append(e)
    return mine
