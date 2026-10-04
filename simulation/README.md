# simulation/ (owner: Goyal)

This folder holds the counterfactual engine: the system model, interventions, the deterministic simulator, ranking, controlled execution, verification and replanning. The signatures are frozen; see `contracts/CONTRACTS.md`.

**Status: FOUNDATION STUBS.**

- `simulator.py` returns canned outcomes per intervention. These are a baseline of 22 breach minutes, I1, I2 and I4 prevent the breach, I3 reduces it to 9, and I5 has no effect.
- `verify.py` replays through `simulate` without a real stress variant yet.

Replace `simulate` with the real seeded minute-step model. It must stay pure: no I/O, no LLM, and the same seed must give the same result. The model should replay `SystemModel.param_changes` and apply each `InterventionAction`.

`execute` must only ever touch the in-memory simulated environment.
