# simulation/ (owner: Goyal)

This folder holds the counterfactual engine: the system model, interventions, the deterministic simulator, ranking, controlled execution, verification and replanning. The signatures are frozen; see `contracts/CONTRACTS.md`.

**Status:** `replay.py` (H6) and `simulator.py` (H9) are real; the other modules are still foundation stubs.

- `simulator.py` (H9): a deterministic minute-step model of the connection pool. It is an M/M/c queue whose waiters give up after `timeout_ms`. Retries feed the next minute's load, and `retry_max` counts retries after the first attempt. One calibration constant, `BATCH_CONN_DUTY = 0.26`, can be overridden by a `batch_conn_duty` param. For INC-2041: baseline 22 breach minutes (t=32-53) with a peak of 0.387. I1, I2 and I4 prevent the breach. I3 cuts it to 20 minutes with a peak of 0.189, which does not prevent it. I5 equals the baseline. The module docstring has the full model. `seed` is recorded on the result, but the model has no noise.
- `verify.py` replays through `simulate` without a real stress variant yet.
- `replay.py` (H6, real): `replay(model, actions)` returns the effective params for every minute. It replays `param_changes` and applies the four action ops. A shifted job moves together with its end, and `set_param` wins over `param_changes`. The module docstring has the exact rules.

## Calibration (H11)

`BATCH_CONN_DUTY = 0.26` in `simulator.py` is the INC-2041 calibration parameter. It is the share of time the batch job's 8 connections are checked out. With every connection busy, the fixture's literal numbers leave 2 connections for ~8.2 erlangs of demand, which gives errors of at least 75%, not the observed ~38%.

| duty | breach minutes | peak error |
| --- | --- | --- |
| 0.25 | 20 | 0.307 |
| **0.26** | **22 (t=32-53)** | **0.387** |
| 0.27 | 23 | 0.437 |

The acceptance envelope is 22 ± 3 breach minutes and a 0.38 ± 0.05 peak. It holds only for duty ~0.252-0.268, because the cut pool sits at the edge of demand, so the value is pinned. The simulated breach window matches the observed t=32-53. The ramp differs: the simulation climbs steadily to its peak at t=49, while `metrics.json` peaks at t=36. The mean absolute error against the observed series is 0.029. `tests/simulation/test_calibration.py` enforces all of this. A `batch_conn_duty` model param overrides the constant.

`metrics.json` has not been regenerated. `data/README.md` says Goyal regenerates it once the baseline matches the observed shape, and Vinayak reviews the change. The window and peak match, but the shape of the ramp does not yet. Regenerating also means changing Vinayak's `data/generate_inc2041.py`. That step is pending agreement with the data owner.

`simulate` must stay pure: no I/O, no LLM, and the same seed must give the same result.

`execute` must only ever touch the in-memory simulated environment.
