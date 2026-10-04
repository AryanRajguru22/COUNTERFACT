"""Generator for the INC-2041 golden fixture. Owner: Vinayak.

Run from the repo root: python data/generate_inc2041.py  (rewrites data/incidents/checkout-pool-001/*.json)
"""
import json, pathlib

OUT = pathlib.Path(__file__).parent / "incidents" / "checkout-pool-001"
DAY = "2026-09-28"
def ts(t): return f"{DAY}T{14 + t // 60:02d}:{t % 60:02d}:00Z"
def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")

dump("incident.json", {
    "id": "INC-2041",
    "title": "Checkout payments failing",
    "service": "payment-svc",
    "severity": "sev1",
    "started_at": ts(31),
    "detected_at": ts(32),
    "resolved_at": ts(54),
    "summary": "Checkout 5xx rate rose above the 5% SLO at 14:32 UTC, peaked near 38% and recovered at 14:54 (about 22 minutes of breach).",
    "window": {"start": ts(0), "minutes": 60},
})

def ev(i, t, source, kind, summary, attributes=None, sc=None):
    e = {"id": f"E-{i:03d}", "ts": ts(t), "t": t, "source": source, "kind": kind, "summary": summary,
         "attributes": attributes or {}}
    if sc: e["state_change"] = {"param": sc[0], "from": sc[1], "to": sc[2]}
    return e

dump("events.json", [
    ev(1, 5, "payment-svc", "config_change", "CHG-881: payment-svc db.pool.max 50 -> 10 (\"cost optimisation\")",
       {"change_id": "CHG-881", "key": "db.pool.max", "author": "platform-bot"}, ("pool_size", 50, 10)),
    ev(2, 20, "payment-svc", "deploy", "Deploy payment-svc v2.4.1",
       {"version": "v2.4.1", "previous_version": "v2.4.0"}),
    ev(3, 28, "payment-gateway", "external", "Gateway provider notice: \"minor EU latency\"",
       {"provider": "payment-gateway", "region": "EU"}),
    ev(4, 30, "settlement-reconcile", "job_start",
       "Batch job settlement-reconcile starts (moved from 02:00 by CHG-870 three days earlier)",
       {"job": "settlement-reconcile", "rescheduled_by": "CHG-870", "previous_schedule": "02:00 UTC",
        "connections": 8}, ("batch_conns", 0, 8)),
    ev(5, 31, "payment-svc", "metric", "Pool wait p99 rises from 2 ms to 900 ms",
       {"metric": "pool_wait_p99_ms", "from": 2, "to": 900}),
    ev(6, 32, "checkout", "alert", "Alert: checkout 5xx > 5%",
       {"alert": "CheckoutErrorRateHigh", "threshold": 0.05}),
    ev(7, 36, "checkout", "metric", "Retry storm: 5xx peaks near 38%",
       {"metric": "checkout_5xx_rate", "value": 0.38}),
    ev(8, 40, "payment-svc", "deploy", "Rollback to v2.4.0, no improvement",
       {"version": "v2.4.0", "previous_version": "v2.4.1", "rollback": True}),
    ev(9, 52, "settlement-reconcile", "job_end", "Batch job ends",
       {"job": "settlement-reconcile"}, ("batch_conns", 8, 0)),
    ev(10, 54, "checkout", "metric", "Recovered", {"metric": "checkout_5xx_rate", "value": 0.004}),
])

T = range(60)
def err(t):
    ramp = {31: 0.03, 32: 0.12, 33: 0.20, 34: 0.28, 35: 0.34, 36: 0.38, 37: 0.37, 52: 0.15, 53: 0.06}
    if t in ramp: return ramp[t]
    if 38 <= t <= 51: return round(0.36 - 0.002 * (t - 38), 3)
    return 0.002 if t < 31 else 0.004
def wait(t):
    if t < 31 or t >= 54: return 2.0
    if t == 31: return 900.0
    if t <= 51: return 1800.0
    return {52: 600.0, 53: 40.0}[t]
def active(t):
    if t < 5: return 8.0
    if t < 30: return 8.0
    if t < 52: return 10.0
    return 8.0
def series(name, unit, service, f):
    return {"name": name, "unit": unit, "service": service, "points": [{"t": t, "value": f(t)} for t in T]}

dump("metrics.json", [
    series("checkout_5xx_rate", "ratio", "checkout", err),
    series("pool_wait_p99_ms", "ms", "payment-svc", wait),
    series("pool_active_connections", "connections", "payment-svc", active),
    series("pool_max_connections", "connections", "payment-svc", lambda t: 50.0 if t < 5 else 10.0),
    series("request_rps", "rps", "checkout", lambda t: 100.0 + (t % 5)),
    series("gateway_call_p99_ms", "ms", "payment-gateway", lambda t: 320.0 + (t % 3) * 5),
    series("db_cpu_pct", "percent", "payments-db", lambda t: 29.0 + (t % 4)),
    series("db_server_connections", "connections", "payments-db", lambda t: 18.0),
])

dump("system_model.json", {
    "params": {"pool_size": 50, "conn_hold_ms": 80, "timeout_ms": 2000, "retry_max": 3, "batch_conns": 0},
    "exogenous": {"demand_rps": [100.0 + (t % 5) for t in T]},
    "param_changes": [
        {"t": 5, "param": "pool_size", "value": 10, "event_id": "E-001"},
        {"t": 30, "param": "batch_conns", "value": 8, "event_id": "E-004"},
        {"t": 52, "param": "batch_conns", "value": 0, "event_id": "E-009"},
    ],
    "slo": {"max_error_rate": 0.05, "max_breach_minutes": 0},
})

dump("ground_truth.json", {
    "root_cause_hypothesis_id": "H1",
    "rejected_hypothesis_ids": ["H2", "H3", "H4"],
    "preventing_intervention_ids": ["I1", "I2", "I4"],
})
print("ok")
