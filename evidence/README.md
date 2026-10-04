# evidence/ (owner: Vinayak)

This folder covers timeline reconstruction, competing hypotheses, evidence gathering, hypothesis testing and root-cause selection. The signatures are frozen; see `contracts/CONTRACTS.md`.

**Status: FOUNDATION STUBS.**

- `hypotheses.py` seeds H1–H4 from a hard-coded list.
- `evidence.py` serves a hard-coded evidence catalogue.
- `test_hypothesis` is a weighted vote of evidence stances.
- `root_cause.py` returns a hard-coded causal chain for H1.

Replace these bodies with real logic derived from `events.json` and `metrics.json`. `tests/evidence/` must keep passing against the ground truth.
