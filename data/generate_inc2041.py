"""Generator for the INC-2041 golden fixture. Owner: Vinayak.

Run from the repo root: python data/generate_inc2041.py  (rewrites data/incidents/checkout-pool-001/*.json)
"""
import json, pathlib, random

OUT = pathlib.Path(__file__).parent / "incidents" / "checkout-pool-001"
DAY = "2026-09-28"
def ts(t, s=0): return f"{DAY}T{14 + t // 60:02d}:{t % 60:02d}:{s:02d}Z"
def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")
def dump_lines(name, rows):
    # one record per line keeps the larger raw-telemetry files reviewable in diffs
    body = ",\n".join("  " + json.dumps(r) for r in rows)
    (OUT / name).write_text("[\n" + body + "\n]\n", encoding="utf-8", newline="\n")

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

# ------------------------------------------------------------------ raw telemetry (v1.1, additive)
# The files above are the frozen v1 fixture. The files below are the raw evidence the evidence engine
# reads: change records, a config snapshot, application logs and sampled request traces.

POOL_TIMEOUT_MS = 2000
REGIONS = ["us-east-1", "eu-west-1", "ap-south-1", "us-west-2"]
BREACH = range(31, 52)  # minutes where both batch job and pool cut are in force and requests time out


def version(t):
    # v2.4.1 rolls out 14:20-14:22; the rollback to v2.4.0 rolls out 14:40-14:42
    if t < 20 or t >= 42: return "v2.4.0"
    if t < 22: return "v2.4.0" if t == 20 else "v2.4.1"
    if t < 40: return "v2.4.1"
    return "v2.4.1" if t == 40 else "v2.4.0"


dump("deploys.json", [
    {"id": "CHG-870", "type": "schedule_change", "ts": "2026-09-25T10:12:00Z", "t": None,
     "service": "settlement-reconcile", "author": "finance-ops", "approval": "manual",
     "summary": "Move settlement-reconcile from 02:00 to 14:30 UTC (overnight maintenance window conflict)",
     "change": {"key": "schedule", "from": "0 2 * * *", "to": "30 14 * * *"},
     "capacity_review": False},
    {"id": "CHG-881", "type": "config_change", "ts": ts(5), "t": 5,
     "service": "payment-svc", "author": "platform-bot", "approval": "auto (cost-optimisation policy)",
     "summary": "Reduce payment-svc db.pool.max 50 -> 10 (cost optimisation)",
     "change": {"key": "db.pool.max", "from": 50, "to": 10}, "capacity_review": False},
    {"id": "DEP-7101", "type": "deploy", "ts": ts(20), "t": 20, "completed_t": 22,
     "service": "payment-svc", "author": "ci-pipeline", "approval": "manual",
     "summary": "Deploy payment-svc v2.4.1 (rolling, 3 pods)",
     "change": {"key": "version", "from": "v2.4.0", "to": "v2.4.1"},
     "commits": ["a91f3c2 Render receipt PDFs asynchronously",
                 "4be07d1 Bump jackson-databind 2.17.1 -> 2.17.2",
                 "c22e9a0 Add card_network label to checkout metrics"],
     "files_changed": ["src/receipts/ReceiptRenderer.java", "src/receipts/ReceiptQueue.java",
                       "build.gradle", "src/metrics/CheckoutMetrics.java"]},
    {"id": "DEP-7102", "type": "rollback", "ts": ts(40), "t": 40, "completed_t": 42,
     "service": "payment-svc", "author": "oncall-sre", "approval": "incident commander",
     "summary": "Roll back payment-svc to v2.4.0 during INC-2041",
     "change": {"key": "version", "from": "v2.4.1", "to": "v2.4.0"},
     "commits": [], "files_changed": []},
])

dump("config.json", {
    "payment-svc": {"db.pool.max": 10, "db.pool.connection_timeout_ms": POOL_TIMEOUT_MS,
                    "payments.authorize.retry_max": 3, "payments.authorize.retry_backoff_ms": 50,
                    "payments.authorize.retry_jitter": False, "pods": 3},
    "payments-db": {"engine": "postgres-15", "max_connections": 200, "instance": "db.r6g.2xlarge"},
    "settlement-reconcile": {"schedule": "30 14 * * *", "pool": "payment-svc/HikariPool-1", "connections": 8},
    "payment-gateway": {"regions": ["eu-west-1", "us-east-1", "ap-south-1", "us-west-2"], "timeout_ms": 5000},
})

# ---- logs
rng = random.Random(2041)
logs = []
def log(t, s, service, level, message, **attrs):
    logs.append({"ts": ts(t, s), "t": t, "service": service, "level": level, "message": message, **attrs})

for t in range(0, 60, 15):
    log(t, 0, "payments-db", "INFO", "checkpoint complete; connections 18/200, cpu 30%",
        server_connections=18, max_connections=200)
for t in range(0, 60, 10):
    log(t, 30, "payment-gateway", "INFO", "authorize p99 320ms, error rate 0.0%", p99_ms=320)
log(5, 2, "config-agent", "INFO", "Applied CHG-881: payment-svc db.pool.max 50 -> 10 (hot reload)", change_id="CHG-881")
log(5, 3, "payment-svc", "INFO", "HikariPool-1 - pool resized: maximumPoolSize=10", pool_max=10)
log(20, 5, "deployer", "INFO", "Rolling update payment-svc v2.4.0 -> v2.4.1 started", deploy_id="DEP-7101")
log(22, 40, "deployer", "INFO", "Rolling update payment-svc v2.4.1 complete (3/3 pods ready)", deploy_id="DEP-7101")
log(28, 0, "payment-gateway", "WARN", "Provider status page: minor latency in EU region", region="eu-west-1")
log(30, 0, "settlement-reconcile", "INFO", "Starting settlement-reconcile run (schedule 30 14 * * *, CHG-870)",
    job="settlement-reconcile")
log(30, 4, "settlement-reconcile", "INFO", "Opened 8 connections via payment-svc HikariPool-1 (active=8/10)",
    job="settlement-reconcile", connections=8, pool="HikariPool-1")
for t in BREACH:
    waiting = 40 + (t - 31) * 3 if t < 37 else 58
    for i, region in enumerate(REGIONS):
        pod = f"payment-svc-{version(t).replace('.', '')}-{i % 3}"
        log(t, 5 + i * 13, "payment-svc", "ERROR",
            f"HikariPool-1 - Connection is not available, request timed out after {POOL_TIMEOUT_MS}ms "
            f"(total=10, active=10, idle=0, waiting={waiting})",
            region=region, version=version(t), pod=pod, exception="SQLTransientConnectionException",
            pool_active=10, pool_max=10, pool_waiting=waiting)
    if t >= 32:
        log(t, 20, "payment-svc", "WARN",
            "Retrying payments.authorize attempt 2/3 after SQLTransientConnectionException (backoff 50ms, no jitter)",
            region=REGIONS[t % 4], version=version(t), attempt=2)
        log(t, 50, "checkout", "ERROR", "upstream payment-svc returned 503 for POST /checkout/pay",
            region=REGIONS[(t + 1) % 4], http_status=503)
log(40, 10, "deployer", "INFO", "Rolling back payment-svc v2.4.1 -> v2.4.0 (requested by oncall-sre)",
    deploy_id="DEP-7102")
log(42, 30, "deployer", "INFO", "Rollback complete (3/3 pods on v2.4.0)", deploy_id="DEP-7102")
log(52, 1, "settlement-reconcile", "INFO", "settlement-reconcile completed in 22m; released 8 connections",
    job="settlement-reconcile", connections=0)
log(54, 0, "payment-svc", "INFO", "HikariPool-1 - stats (total=10, active=3, idle=7, waiting=0)",
    pool_active=3, pool_max=10, pool_waiting=0)
logs.sort(key=lambda r: (r["ts"], r["service"]))
for n, row in enumerate(logs, 1):
    row["id"] = f"L-{n:04d}"
dump_lines("logs.json", [{"id": r.pop("id"), **r} for r in logs])

# ---- traces: 8 sampled POST /checkout/pay requests per minute
TRACES_PER_MIN = 8
traces = []
for t in T:
    failures = round(err(t) * TRACES_PER_MIN)
    for i in range(TRACES_PER_MIN):
        region = REGIONS[i % 4]
        failed = (i + t) % TRACES_PER_MIN < failures if t in BREACH or t in (52, 53) else False
        gw = 300 + rng.randint(0, 25) + (15 if region == "eu-west-1" and 28 <= t <= 45 else 0)
        db = 6 + rng.randint(0, 6)
        if failed:
            acquire = POOL_TIMEOUT_MS
            spans = [{"name": "pool.acquire", "service": "payment-svc", "duration_ms": acquire,
                      "error": "SQLTransientConnectionException"}]
        else:
            if t in BREACH:
                acquire = rng.randint(600, 1800)
            elif t in (52, 53):
                acquire = int(wait(t)) - rng.randint(0, 30)
            else:
                acquire = 1 + rng.randint(0, 2)
            spans = [{"name": "pool.acquire", "service": "payment-svc", "duration_ms": acquire},
                     {"name": "db.query", "service": "payments-db", "duration_ms": db},
                     {"name": "gateway.authorize", "service": "payment-gateway", "duration_ms": gw}]
        overhead = 4 + rng.randint(0, 6)
        traces.append({
            "trace_id": f"tr-{t:02d}{i:02d}-{rng.randrange(16**6):06x}", "ts": ts(t, 3 + i * 7), "t": t,
            "endpoint": "POST /checkout/pay", "region": region, "version": version(t),
            "status": "error" if failed else "ok", "http_status": 503 if failed else 200,
            "duration_ms": sum(s["duration_ms"] for s in spans) + overhead, "spans": spans,
        })
dump_lines("traces.json", traces)
print("ok")
