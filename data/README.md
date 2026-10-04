# data/ (owner: Vinayak)

This folder holds the synthetic incident fixtures and `loader.py`, which turns them into contract models.

`incidents/checkout-pool-001/` is the golden incident **INC-2041 "Checkout payments failing"**, frozen as v1. A change to it needs a PR that Goyal reviews.

**Story:** CHG-881 cut payment-svc's DB connection pool from 50 to 10 at 14:05. At 14:30 the rescheduled settlement-reconcile batch job took 8 of those connections. Requests then queued, timed out and retried. The 5xx rate peaked near 38% and stayed above the 5% SLO for 22 minutes.

**Calibration rule:** `metrics.json` is hand-written for v1. Once Goyal's baseline simulation matches its shape, Goyal regenerates it from the baseline with seeded noise and Vinayak reviews.

**Regenerating the fixture:** `python data/generate_inc2041.py` (from the repo root) rewrites the five JSON files. Edit the script rather than the 60-point series by hand.
