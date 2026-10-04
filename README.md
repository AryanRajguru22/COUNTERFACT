# COUNTERFACT

> The goal is not to explain yesterday's failure. The goal is to prevent the next one.

COUNTERFACT investigates an operational incident, tests competing root-cause hypotheses against evidence, then replays the incident in a deterministic simulator to find the intervention that would have prevented it. A human approves the fix, and the system executes and verifies it in the simulated environment.

```
INCIDENT → TIMELINE → HYPOTHESES → EVIDENCE → TESTING → ROOT CAUSE
        → COUNTERFACTUAL LAB (simulate, rank) → HUMAN APPROVAL → EXECUTE → VERIFY
```

## Run it (zero cost, no API key)

Run these from the repo root:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload     # http://127.0.0.1:8000/api/health

cd frontend
npm install
npm run dev                           # http://localhost:5173 (proxies /api to :8000)
```

To run the tests, use `pytest -q` from the repo root and `npm run typecheck` from `frontend/`.

Configuration lives in `.env` (copy `.env.example`). `LLM_MODE=replay` is the default and needs no network or key.

## Ownership

| Directory | Owner |
| --- | --- |
| `frontend/`, `docs/`, `tests/e2e/` | Aryan |
| `backend/`, `agent/`, `contracts/`, `tests/agent/`, `tests/backend/`, `tests/contract/` | Rohit |
| `data/`, `evidence/`, `tests/evidence/` | Vinayak |
| `simulation/`, `tests/simulation/` | Goyal |

## Rules

- **Edit only directories you own.** If you need a change elsewhere, ask the owner.
- **Contracts are frozen** (`contracts/models.py`). Changes are additive only: never rename or remove a field. Announce every change in chat, and Aryan mirrors it in `frontend/src/types.ts`.
- **Engine signatures are frozen** (`contracts/CONTRACTS.md`). Replace stub bodies, never signatures.
- **`agent/tools.py` is the only file** that wires the engines into the agent and backend.
- **Each lockfile has one writer.** Rohit owns `requirements.txt` (append one pinned line). Aryan owns `frontend/package.json` and its lockfile.
- **Never format files you don't own.** `.gitattributes` forces LF line endings.
- **Before merging to `main`,** run `git pull --rebase origin main`, then `pytest -q` and `npm run typecheck`.
- **Branches** are `aryan/<topic>`, `rohit/<topic>`, `vinayak/<topic>`, `goyal/<topic>`, and `contracts/<topic>`. Merge to `main` at least every 3 hours.
- **Never commit `.env`.**

## Status: foundation

Every engine function is a deterministic **stub** that returns valid contract objects for the golden incident `INC-2041`. Each owner replaces their stubs with real logic behind the same signatures.
