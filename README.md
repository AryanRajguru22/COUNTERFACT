# COUNTERFACT

> An AI agent that doesn't just find why something failed — it discovers what would have prevented it.

COUNTERFACT is an AI agent for **evidence-based incident investigation and counterfactual intervention analysis**. It reconstructs an incident, weighs competing hypotheses against evidence, identifies the root cause, then replays the incident in a deterministic simulator with each candidate fix applied. A human approves the recommended intervention, the system executes and verifies it in a simulated environment, and if verification fails it replans.

```
INCIDENT → TIMELINE → HYPOTHESES → EVIDENCE → ROOT CAUSE → COUNTERFACTUALS → RANK → APPROVE → EXECUTE → VERIFY → REPLAN
```

Traditional incident analysis asks *"What happened, and why?"*
COUNTERFACT asks *"What happened, why did it happen, and **what would have prevented it?**"*

Everything described below is implemented and runs locally in replay mode with no API key and no network. The demo uses one deterministic golden incident (`INC-2041`); nothing here touches real infrastructure.

---

## The idea in 30 seconds

- **Reconstruct** the incident as a timeline of state-changing events.
- **Investigate** four competing explanations and test each against gathered evidence.
- **Conclude** with a root cause and a causal chain, not a list of suspects.
- **Simulate** five candidate interventions on the same incident, one at a time or combined.
- **Rank** them by measured outcome (breach minutes, peak error rate) and risk/effort.
- **Ask a human** to approve. Nothing executes without sign-off.
- **Verify** the change in the simulated environment, including a +20% demand stress test.
- **Replan** if verification fails or the human rejects: the failed option is dropped and the rest are re-ranked.

---

## The problem

During an incident, engineers reconstruct a timeline, inspect evidence, compare possible causes, settle on a root cause and pick a mitigation. Most analysis ends once the cause is named.

Naming the cause does not answer the next question: **which intervention would actually have prevented the failure?**

In INC-2041 the cause is connection-pool exhaustion. That explanation alone does not say whether restoring the pool, moving a batch job, adding retry jitter, adding a capacity guardrail or rolling back the last deploy would have averted the outage, or by how much. COUNTERFACT answers that by testing each alternative against a replay of the incident.

## How COUNTERFACT changes incident response

| Traditional incident analysis | COUNTERFACT |
| --- | --- |
| Reconstruct what happened | Reconstruct the timeline |
| Diagnose a cause | Test competing hypotheses against evidence and conclude with a causal chain |
| Recommend a mitigation | **Simulate every candidate mitigation on the same incident** |
| | Quantify outcomes and rank alternatives |
| | Require human approval before anything executes |
| | Execute in the simulated environment and verify |
| | Replan when verification fails or the proposal is rejected |

Existing tools do some of these steps. COUNTERFACT's defining feature is the explicit **counterfactual loop** that connects diagnosis to a tested, verified decision.

---

## End-to-end workflow

```
┌──────────────────────────┐
│         INCIDENT         │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│  Timeline reconstruction │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ Hypotheses + evidence    │   4 hypotheses, 17 evidence items
│ + hypothesis testing     │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ Root cause + causal chain│   H1 confirmed (95%), 10-link chain
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│    Counterfactual Lab    │   I1–I5 simulated on the same incident
│    Simulate + rank       │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│   Human approval gate    │   reject needs a written note
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│     Execute + verify     │   SLO checks + stress test
└────────────┬─────────────┘
             ↓
      ┌──────┴───────┐
    PASS           FAIL / REJECTED
      │               │
      ↓               ↓
  RESOLVED         REPLAN ──→ re-rank the remaining options ──→ back to the gate
                   (stops after 3 approval attempts)
```

Each box is a real stage of the backend state machine: `created → timeline → hypotheses → evidence → testing → root_cause → counterfactual → awaiting_approval → executing → verifying → resolved`, with `replanning` and `failed` as the feedback and terminal-failure states.

## The counterfactual loop

The important question is not only *"Why did the system fail?"* but *"What would have prevented the failure?"*

COUNTERFACT turns each candidate mitigation into a testable counterfactual: replay the same incident with exactly that change and compare the outcome against the simulated baseline. Candidates are compared on measurable results:

- **breach minutes** (minutes above the 5% error-rate SLO)
- **peak error rate**
- **ranking score** (breach minutes avoided, minus a risk penalty, minus an effort cost)
- **verification result** (SLO checks plus a +20% demand stress test)

A human then decides whether to proceed. This loop is the project's core idea.

---

## Golden incident: INC-2041, checkout payments failing

A **deterministic golden-incident simulation**. The data is a purpose-built fixture in `data/incidents/checkout-pool-001/`, not a real production incident.

| Signal | Value |
| --- | ---: |
| Initial DB connection pool (`payment-svc`) | 50 |
| Pool after change CHG-881 (14:05) | 10 |
| Settlement-reconcile batch job starts | 14:30 |
| Connections held by the batch job | 8 |
| SLO breach window | 14:32–14:54 |
| Baseline breach duration | 22 min |
| Observed peak 5xx rate | ~38.0% |
| Simulated baseline peak error rate | ~38.7% |
| SLO | error rate ≤ 5% |

Requests queue for a connection, time out and retry without jitter, which amplifies the load until the batch job ends.

## Root-cause investigation

The agent does not just list possible causes. Four competing hypotheses are tested against the evidence before a root cause is selected.

| Hypothesis | Result | Confidence |
| --- | --- | ---: |
| **H1** Connection-pool exhaustion: CHG-881 plus settlement-reconcile contention | **Confirmed** | 95% |
| **H2** Code regression in deploy v2.4.1 | Rejected | 9% |
| **H3** Payment gateway degradation | Rejected | 11% |
| **H4** Database server overload | Rejected | 12% |

- **17 evidence items**, each linked to the events it comes from and to the hypotheses it supports or refutes.
- **10-link causal chain** from the pool cut to recovery, for example: pool cut 50 → 10; batch takes 8 connections; requests queue (pool-wait p99 2 ms → 900 ms); timeouts; 5xx crosses the SLO; retries without jitter amplify load; peak 38%; batch ends and releases its connections; error rate falls back under the SLO.
- Hypotheses are rejected with stated reasons. For example, H4 is refuted because database CPU stayed low and query latency stayed flat while the client was starved for connections.

## Counterfactual Lab

Each intervention is applied to the incident and simulated against the same demand. These are **deterministic simulation results for the project's golden incident, not claims about a real production system.**

| Intervention | Outcome | Breach | Peak error | Score |
| --- | --- | ---: | ---: | ---: |
| **I1** Revert pool size to 50 | Prevents the outage | 0 min | 0.0% | 21.88 |
| **I2** Move settlement-reconcile off-peak | Prevents the outage | 0 min | 0.0% | 21.75 |
| **I4** Capacity-check guardrail for pool-reducing config changes | Prevents the outage | 0 min | 0.0% | 20.00 |
| **I5** Roll back v2.4.1 | **No effect** | 22 min | ~38.7% | −0.12 |
| **I3** Retry budget with jitter | Reduces severity only | 20 min | ~18.9% | −2.00 |

Baseline (no change): 22 breach minutes, ~38.7% peak.

- **I1 ranks first**: it prevents the outage with the lowest risk and effort (15 minutes).
- **I5 is the instructive negative result.** The obvious first response, rolling back the latest deploy, changes nothing: the simulation reproduces the outage exactly.
- **I3** trims the peak roughly in half but still breaches the SLO for 20 minutes.
- Interventions can also be combined in the Lab (`POST /api/simulate`); only single interventions are ranked and approvable.

The Lab draws the observed telemetry, the simulated baseline and the counterfactual on one chart, with each series labelled.

## Human approval and execution

COUNTERFACT does **not** execute a recommendation on its own.

```
INVESTIGATE → SIMULATE → RANK → RECOMMEND → HUMAN APPROVAL → EXECUTE → VERIFY
```

- The Approval Gate shows the ranked options, risk, effort, avoided breach minutes and the exact change that will be applied (for I1: `set_param pool_size = 50`).
- The approver can pick any ranked option, not only the recommended one, and is warned when it is not the recommendation.
- **Approve** applies the change to an in-memory copy of the system model and verifies it.
- **Reject** requires a written note, which is recorded and shown with the replan.
- The server rejects stale or duplicate decisions (409), unknown interventions (400) and rejections without a note (422).

This puts an explicit decision boundary between AI-assisted investigation and recommendation, and execution. Execution is simulated only.

## Failure → replan → success

```
Approve I3 (a weaker option)
  → execute in the simulated environment
  → verification FAILS: 20 breach minutes, peak 18.9% against a 5.0% SLO, 27 minutes at +20% demand
  → the agent replans: I3 is dropped, the remaining options are re-ranked
  → I1 becomes the recommendation
  → human approves I1
  → execute → verification PASSES: 0 breach minutes, 0.0% peak, 0 minutes at +20% demand
  → RESOLVED after 2 approval attempts
```

A rejection with a note follows the same path: the rejected option is removed and the next candidate is recommended. After 3 approval attempts without a verified fix the investigation stops in `failed` and says why.

This is a closed loop with feedback, not "model gives an answer, UI displays it".

---

## System architecture

```
 React + TypeScript frontend (Vite)
            │  REST, polled every second
            ▼
 FastAPI backend ───────────────  in-memory investigation store (no database)
            │
            ▼
 Agent orchestrator  (deterministic state machine)
      │         │          │
      │         │          └──► LLM client: replay recordings (default) | OpenAI-compatible endpoint
      ▼         ▼
 evidence/     simulation/            data/ (INC-2041 fixture)
 timeline      deterministic model    events, metrics, logs, traces,
 hypotheses    interventions I1–I5    deploys, config, system model
 evidence      ranking
 root cause    execute + verify
               replan
```

**Deterministic:** the evidence engine, the simulator, ranking, execution, verification, replanning and the state machine. The simulator has no I/O, no LLM and no randomness. **Not deterministic:** only the optional live LLM narration.

The backend reaches the engines only through `agent/tools.py`; the shared data contract is `contracts/models.py` (mirrored in `frontend/src/types.ts`).

## AI and agent architecture

COUNTERFACT is not a chatbot. It is a structured, state-driven investigation workflow.

1. An incident enters the orchestrator, which advances the investigation stage by stage and logs every thought and tool call as an agent step (visible in the **Agent Trace** drawer).
2. The timeline, hypotheses and evidence are produced by the evidence tools.
3. Hypotheses are tested; one is confirmed and a causal chain is built.
4. Counterfactual tools simulate each intervention; ranking produces the recommendation.
5. The run pauses at the approval gate until a human decides.
6. Approved changes are executed and verified; a failed verification or a rejection triggers a replan.

**Where is the AI?** The agent narrates its reasoning at each stage using the LLM client, and can optionally propose up to two additional hypotheses (`LLM_HYPOTHESES=1`, off by default), which the evidence engine then tests and can reject like any other. The engines decide; the LLM narrates and proposes. This keeps every verdict reproducible and auditable.

It is a single orchestrated agent, not a multi-agent system, and it does not use LangChain, LangGraph or CrewAI.

## Deterministic replay

The demo should not fail because an external LLM is unavailable.

- **Replay mode (default):** narration comes from recorded responses in `agent/recordings/INC-2041.json`. No network, no API key.
- **Live mode:** narration comes from any OpenAI-compatible chat-completions endpoint. If it is not configured, or a call fails, the run **falls back to replay** and the agent trace records why. The investigation continues normally.
- `RECORD=1` merges successful live responses into the recording, so a later replay reproduces that run.

Replay is a recording, not a live model; it makes the core demo path reproducible and independent of external services.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 3 (charts are hand-written SVG) |
| Backend | Python 3.11, FastAPI, Pydantic 2, Uvicorn, httpx |
| Agent | Structured state machine, OpenAI-compatible LLM interface, deterministic replay |
| Simulation | Deterministic minute-step connection-pool model (M/M/c queue with timeouts and retry feedback) |
| Tests | pytest (backend), Vitest (frontend), TypeScript typecheck |

## API

All routes are under `/api`. Full schemas are in `contracts/CONTRACTS.md`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness and LLM mode (`replay` or `live`) |
| `GET` | `/api/incidents` | List incidents |
| `GET` | `/api/incidents/{id}/system-model` | System model and SLO |
| `GET` | `/api/incidents/{id}/metrics` | Observed telemetry |
| `POST` | `/api/investigations` | Start an investigation (`incident_id`, `mode`) |
| `GET` | `/api/investigations/{id}` | Current state, steps, results (polled by the UI) |
| `POST` | `/api/investigations/{id}/approval` | Approve or reject an intervention |
| `POST` | `/api/simulate` | Simulate one or more interventions on demand |

## Project structure

```
backend/      FastAPI app, REST routes, in-memory store
agent/        Orchestrator state machine, tool wiring, LLM client, prompts, replay recordings
evidence/     Timeline, hypotheses, evidence, hypothesis testing, root cause
simulation/   Simulator, interventions, ranking, execution, verification, replan
data/         INC-2041 fixture (events, metrics, logs, traces, deploys, config, system model)
contracts/    Shared data models and API contract
frontend/     React investigation workspace (8 views + agent trace drawer)
tests/        agent, backend, contract, evidence, simulation and end-to-end tests
docs/         DEMO.md, the presenter script and click path
```

---

## Quick start

Requires Python 3.11+ and a current Node.js LTS. Run from the repo root.

```bash
# Backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --port 8000          # http://127.0.0.1:8000/api/health

# Frontend (second terminal)
cd frontend
npm ci
npm run dev                                   # http://localhost:5173
```

The dev server proxies `/api` to `127.0.0.1:8000`, so no configuration is needed. Open http://localhost:5173, keep **Replay** selected and press **Investigate**. With the default pacing the agent reaches the approval gate in about 27 seconds.

## Environment configuration

Everything is optional. **An LLM API key is not required for the deterministic replay demo.** Copy `.env.example` to `.env` to change anything; never commit `.env`.

| Variable | Where | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | frontend build | API base URL; defaults to the relative `/api` (same origin). |
| `CORS_ORIGINS` | backend | Comma-separated extra browser origins allowed to call the API; `localhost:5173` is always allowed. |
| `LLM_MODE`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | backend | Live narration; without them the run falls back to replay. |
| `STEP_DELAY_MS` | backend | Pacing of the agent for the UI, default 700. |

## Testing and validation

```bash
pytest -q                                   # repo root
cd frontend && npm test && npm run typecheck && npm run build
```

| Validation | Status |
| --- | --- |
| Backend tests | 398 passing |
| Frontend tests | 15 passing |
| TypeScript typecheck | Passing |
| Production build | Passing |
| Browser end-to-end (desktop, production build) | Walked through manually: happy path, I5 no-effect, I3 failure → replan → I1, rejection with and without a note |
| Mobile (390 px wide) | Checked manually across all 8 views; no horizontal overflow |
| Live mode without an LLM key | Falls back to replay and reaches the gate |
| Approval API edge cases | Stale, duplicate, unknown-intervention and missing-note requests return 409 / 409 / 400 / 422; the 3-attempt cap ends in `failed` |
| Network and console | No failed API calls and no console errors on a fresh load |

The backend suite covers the contract, evidence engine, simulator (including calibration), ranking, verification, replanning, the orchestrator, the LLM client and fallback, the API, and a full golden-flow test. Coverage was not measured.

## Deployment

There is no database and no backend build step. Investigations live in the memory of the backend process, so **run exactly one persistent backend process**; restarting it forgets existing investigations. No hosting provider is prescribed.

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm ci
npm run build                      # static files in frontend/dist
```

Serve `frontend/dist/` from any static host (it uses hash routing, so no rewrite rules are needed), then choose one:

- **Option A, same origin:** have the host or reverse proxy forward `/api/*` to the backend.
- **Option B, separate origins:** build with `VITE_API_BASE_URL=https://<backend>/api` and start the backend with `CORS_ORIGINS=https://<frontend>`.

Health check: `GET /api/health` returns `{"ok": true, "llm_mode": "replay"}`.

**Docker:** `docker compose up -d --build` runs Option A in two containers: nginx serves the build and proxies `/api` to a single uvicorn process. It listens on `127.0.0.1:8100` (override with `COUNTERFACT_PORT`), so put a reverse proxy or tunnel in front of it.

---

## Judge demo: from failure to prevention

The full presenter script with talking points is in [`docs/DEMO.md`](docs/DEMO.md). The click path:

1. Open **INC-2041** on the start screen (Replay mode) and press **Investigate**.
2. **Timeline:** see the three state-changing events (CHG-881, batch start, batch end).
3. **Hypotheses:** four competing explanations.
4. **Evidence:** the 17 items behind each verdict.
5. **Root Cause:** H1 confirmed, with the 10-link causal chain.
6. Open the **Counterfactual Lab** and compare the interventions.
7. Select **I5**: it shows **NO EFFECT**, the same 22-minute outage as the baseline.
8. Select **I1**, **I2** and **I4**: each stays under the SLO for the whole window. I1 is ranked first.
9. At the **Approval Gate**, approve **I1**.
10. **Execution & Verification:** executes, passes every check and the stress test, and the investigation is **Resolved**.
11. *Optional replan beat, on a fresh run:* approve **I3** instead.
12. Verification fails, the agent replans, and **I1** becomes the recommendation.
13. Approve **I1** and watch it verify and resolve.

> COUNTERFACT doesn't stop at explaining why the incident happened. It tests what would have prevented it.

## Limitations and scope

- One deterministic golden incident (INC-2041); the evidence and simulation are built for it.
- Deterministic counterfactual simulation with a fixed intervention catalogue (I1–I5).
- The simulated baseline matches the observed breach window and peak error rate but not the exact shape of the ramp: the simulation climbs steadily while the observed telemetry peaks earlier. The Lab labels both curves. See `simulation/README.md`.
- Investigation state is in memory; there is no database.
- Execution changes an in-memory model of the system. There is no real infrastructure access, authentication or cloud orchestration, and no real production integrations.
- A hackathon prototype, not a production incident-management platform.

## Team

| | Role | Owned |
| --- | --- | --- |
| **Aryan Rajguru** | Frontend, product integration and demo | The investigation workspace (React/TypeScript): Timeline, Hypotheses, Evidence, Root Cause, Counterfactual Lab, Approval Gate and Verification views; UI/UX and responsive layout; frontend/backend integration; approval, rejection and replan interactions; replay/live fallback presentation; demo workflow and documentation; final integration, end-to-end validation and deployment preparation |
| **Aryan Goyal** | Backend, agent and orchestration | FastAPI backend and investigation APIs; agent state-machine orchestration and investigation lifecycle; contracts; backend integration; LLM and replay architecture; approval and investigation state handling |
| **Rohit Kumar Yadav** | Counterfactual simulation and verification | Counterfactual simulation engine; intervention modelling and ranking; simulation results; verification logic; replanning support; deterministic simulation behaviour |
| **Vinayak Tyagi** | Evidence, RCA data and deployment | Golden incident data; evidence engine and investigation evidence; RCA support and evidence validation; data presentation and polish; deployment and final hosting |

<details>
<summary>Repository conventions</summary>

- Contracts (`contracts/models.py`) and engine signatures (`contracts/CONTRACTS.md`) are frozen: changes are additive only, and the frontend mirror in `frontend/src/types.ts` is updated with them.
- `agent/tools.py` is the only file that wires the engines into the agent and backend.
- Each lockfile has one writer. `.gitattributes` forces LF line endings.
- Before merging to `main`, run `pytest -q` and `npm run typecheck`.

</details>

## Why COUNTERFACT?

Most incident systems help answer *"Why did it fail?"*

COUNTERFACT adds a second question: *"What would have prevented it?"* It combines evidence-based investigation, counterfactual simulation, human approval, verification and replanning in one workflow.

That is the project's central idea.
