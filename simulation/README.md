# simulation/ (owner: Goyal)

This folder holds the counterfactual engine: the system model, interventions, the deterministic simulator, ranking, controlled execution, verification and replanning. The signatures are frozen; see `contracts/CONTRACTS.md`.

**Status:** `replay.py` (H6) and `simulator.py` (H9) are real; the other modules are still foundation stubs.

- `simulator.py` (H9): a deterministic minute-step model of the connection pool. It is an M/M/c queue whose waiters give up after `timeout_ms`. Retries feed the next minute's load, and `retry_max` counts retries after the first attempt. One calibration constant, `BATCH_CONN_DUTY = 0.26`, can be overridden by a `batch_conn_duty` param. For INC-2041: baseline 22 breach minutes (t=32-53) with a peak of 0.387. I1, I2 and I4 prevent the breach. I3 cuts it to 20 minutes with a peak of 0.189, which does not prevent it. I5 equals the baseline. The module docstring has the full model. `seed` is recorded on the result, but the model has no noise.
- `verify.py` replays through `simulate` without a real stress variant yet.
- `replay.py` (H6, real): `replay(model, actions)` returns the effective params for every minute. It replays `param_changes` and applies the four action ops. A shifted job moves together with its end, and `set_param` wins over `param_changes`. The module docstring has the exact rules.

`simulate` must stay pure: no I/O, no LLM, and the same seed must give the same result.

`execute` must only ever touch the in-memory simulated environment.
