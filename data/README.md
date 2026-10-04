# data/ (owner: Vinayak)

This folder holds the synthetic incident fixtures and `loader.py`, which turns them into contract models.

`incidents/checkout-pool-001/` is the golden incident **INC-2041 "Checkout payments failing"**, frozen as v1. A change to it needs a PR that Goyal reviews.

**Story:** CHG-881 cut payment-svc's DB connection pool from 50 to 10 at 14:05. At 14:30 the rescheduled settlement-reconcile batch job took 8 of those connections. Requests then queued, timed out and retried. The 5xx rate peaked near 38% and stayed above the 5% SLO for 22 minutes.

**Calibration rule:** `metrics.json` is hand-written for v1. Once Goyal's baseline simulation matches its shape, Goyal regenerates it from the baseline with seeded noise and Vinayak reviews.

**Regenerating the fixture:** `python data/generate_inc2041.py` (from the repo root) rewrites the five JSON files. Edit the script rather than the 60-point series by hand.

## Raw telemetry (v1.1, additive)

These files are the raw evidence the evidence engine reads. They do not change any v1 file, and the agent reaches them only through `evidence/`.

| File | Contents | Loader |
| --- | --- | --- |
| `deploys.json` | Change records: CHG-870 (batch reschedule, 3 days earlier), CHG-881 (pool cut), DEP-7101 (v2.4.1, with commits and files changed), DEP-7102 (rollback) | `load_deploys` |
| `config.json` | Config snapshot per service: pool max and timeout, retry policy, DB `max_connections`, batch schedule | `load_config` |
| `logs.json` | Application logs from payment-svc, checkout, settlement-reconcile, payments-db, payment-gateway and the deployer | `load_logs` |
| `traces.json` | 8 sampled `POST /checkout/pay` traces per minute with `pool.acquire`, `db.query` and `gateway.authorize` spans | `load_traces` |

The traces follow the v1 story. Failing requests time out in `pool.acquire` after 2000 ms and never reach the DB or gateway. Errors are spread across all four regions and both versions. Gateway and DB spans stay normal throughout.
