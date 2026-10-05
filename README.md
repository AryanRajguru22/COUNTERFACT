# COUNTERFACT

> The goal is not to explain yesterday's failure. The goal is to prevent the next one.

COUNTERFACT is an agentic incident investigation and counterfactual intervention system. It investigates an operational incident, tests competing root-cause hypotheses against evidence, then replays the incident in a deterministic simulator to find the intervention that would have prevented it. A human approves the fix, and the system executes and verifies it in the simulated environment. Nothing real is ever touched.

```
INCIDENT → TIMELINE → HYPOTHESES → EVIDENCE → TESTING → ROOT CAUSE
        → COUNTERFACTUAL SIMULATION → RANKING → HUMAN APPROVAL → EXECUTE → VERIFY
                                                      ↑                       │
                                                      └──── REPLAN ←──────────┘ (rejected or failed verification)
```

## What is implemented

- **Golden incident `INC-2041`** ("Checkout payments failing", a connection-pool exhaustion), the only incident fixture. Its data lives in `data/incidents/checkout-pool-001/`.
- **Evidence engine** (`evidence/`): timeline reconstruction, competing hypotheses, evidence gathering, hypothesis testing and root-cause determination with a causal chain.
- **Counterfactual engine** (`simulation/`): a deterministic minute-step model of the connection pool, a fixed intervention catalogue (I1-I5), ranking, controlled execution, verification with a +20% demand stress test, and replanning. Simulation is pure: no I/O, no LLM, no randomness.
- **Agent** (`agent/`): a state machine that drives the engines in order and narrates each step. The LLM only narrates; every decision comes from the engines.
- **Human approval gate**: approving executes and verifies the intervention. Rejecting needs a note and triggers a replan. A failed verification also triggers a replan, and an investigation stops after 3 approval attempts without a verified fix.
- **REST API** (`backend/`, FastAPI, in-memory store): see `contracts/CONTRACTS.md`.
- **React investigation workspace** (`frontend/`): Overview, Timeline, Hypotheses, Evidence, Root Cause, Counterfactual Lab, Approval Gate and Execution & Verification, plus an agent trace drawer. The Lab can combine interventions through `POST /api/simulate`.
- **Replay mode** (default): recorded narration from `agent/recordings/`, so the demo needs no network or API key.
- **Live mode**: narration from an OpenAI-compatible endpoint. If it is not configured or a call fails, the run continues on the replay recordings and the agent trace says so.

Execution is simulated only: `execute` changes an in-memory copy of the system model. There is no authentication, database or real infrastructure access.

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

To run the tests, use `pytest -q` from the repo root, and `npm test`, `npm run typecheck` and `npm run build` from `frontend/`.

Configuration lives in `.env` (copy `.env.example`). `LLM_MODE=replay` is the default and needs no network or key. `LLM_MODE=live` needs `LLM_BASE_URL` and `LLM_MODEL`; without them the run falls back to replay. `STEP_DELAY_MS` (default 700) paces the agent so the UI can show progress.

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
- **Engine signatures are frozen** (`contracts/CONTRACTS.md`). Never change a signature.
- **`agent/tools.py` is the only file** that wires the engines into the agent and backend.
- **Each lockfile has one writer.** Rohit owns `requirements.txt` (append one pinned line). Aryan owns `frontend/package.json` and its lockfile.
- **Never format files you don't own.** `.gitattributes` forces LF line endings.
- **Before merging to `main`,** run `git pull --rebase origin main`, then `pytest -q` and `npm run typecheck`.
- **Branches** are `aryan/<topic>`, `rohit/<topic>`, `vinayak/<topic>`, `goyal/<topic>`, and `contracts/<topic>`. Merge to `main` at least every 3 hours.
- **Never commit `.env`.**

## Demo

`docs/DEMO.md` has the presenter script and the click path for INC-2041, including the optional replan beat (approve I3, verification fails, the ranking re-forms, approve I1).

## Known limitations

- The simulated baseline matches the observed breach window (14:32-14:54) and the peak error rate (about 38%), but its ramp differs: the simulation climbs steadily to its peak, while the observed telemetry peaks earlier. The Lab draws both and labels them as observed telemetry and simulated baseline. See `simulation/README.md`.
- Combined interventions can be simulated and viewed in the Lab, but only single interventions are ranked and approvable.
- Investigations live in memory; restarting the backend forgets them.
