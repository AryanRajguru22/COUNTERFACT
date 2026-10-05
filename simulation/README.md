# simulation/ (owner: Goyal)

This folder holds the counterfactual engine: the system model, interventions, the deterministic simulator, ranking, controlled execution, verification and replanning. The signatures are frozen; see `contracts/CONTRACTS.md`.

**Status:** `replay.py` (H6), `simulator.py` (H9), `interventions.py`, `ranking.py` (H12), `executor.py` and `verify.py` (H15) are real; `replan` is still a stub (H18).

- `interventions.py` (H12): `generate_interventions` keeps the catalogue entries that address the root cause's causal chain. An event op addresses it when its target is in the chain. A param op addresses it when the chain runs through modelled state. Rollbacks are controls, simulated next to any real fix. A root cause that no entry addresses gets `[]`. INC-2041 (H1) gets I1-I5.
- `ranking.py` (H12): preventing interventions come first; then `score = breach minutes avoided - risk penalty (low 0, med 3, high 8) - 0.5 x effort hours`; ties break by id. The INC-2041 order is I1, I2, I4, I5, I3. I3 halves the peak but saves only 2 minutes, which does not pay for its med risk and 2 h effort. The formula has no peak-error term.
- `simulator.py` (H9): a deterministic minute-step model of the connection pool. It is an M/M/c queue whose waiters give up after `timeout_ms`. Retries feed the next minute's load, and `retry_max` counts retries after the first attempt. One calibration constant, `BATCH_CONN_DUTY = 0.26`, can be overridden by a `batch_conn_duty` param. For INC-2041: baseline 22 breach minutes (t=32-53) with a peak of 0.387. I1, I2 and I4 prevent the breach. I3 cuts it to 20 minutes with a peak of 0.189, which does not prevent it. I5 equals the baseline. The module docstring has the full model. `seed` is recorded on the result, but the model has no noise.
- `executor.py` (H15): `execute` applies the action to an in-memory deep copy of the model; nothing real is touched. `applied_changes` lists exactly the actions applied. Invalid actions return `status="failed"` and an empty list. `apply_changes(model, actions)` builds the changed model, and replaying it gives the same timeline as replaying the original with the actions.
- `verify.py` (H15): the source of truth is `execution.applied_changes`; it never looks up the catalogue. The changed model is simulated as recorded (breach minutes and peak error rate must meet the SLO). It is then simulated a second time with every minute's demand x1.2 (`STRESS_DEMAND_FACTOR`), and its breach minutes must also meet the SLO. `passed` requires every check, the stress check included, as the agent's replan context already assumes. INC-2041: I1, I2 and I4 pass both. I3 (20 / 27 min) and I5 (22 / 30) fail. The baseline at +20% breaches t=30-59.
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
