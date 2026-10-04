# tests/

Run `pytest -q` from the repo root. `pytest.ini` sets `pythonpath = .` and `--import-mode=importlib`, so `tests/simulation/` cannot shadow the real `simulation` package.

| Folder | Owner | Covers |
| --- | --- | --- |
| `contract/` | Rohit | Contract parsing, golden fixture loading and consistency |
| `evidence/` | Vinayak | Evidence engine against the ground truth |
| `simulation/` | Goyal | Simulator determinism, preventing set, ranking, execute/verify/replan |
| `agent/` | Rohit | LLM client (replay default) |
| `backend/` | Rohit | API health, incidents, simulate |
| `e2e/` | Aryan | Golden flow: Investigate, then awaiting_approval, then approve or reject |

`conftest.py` forces `STEP_DELAY_MS=0` and `LLM_MODE=replay`.
