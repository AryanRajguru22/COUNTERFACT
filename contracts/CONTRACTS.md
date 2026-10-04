# Contracts v1 (frozen at foundation)

Gatekeeper: **Rohit**. The source of truth is `models.py`, and `frontend/src/types.ts` mirrors it by hand.

Change rules: **additive only**. You may add optional fields. Never rename or remove a field. Every change needs a PR on a `contracts/<topic>` branch and a message in team chat, and the TS mirror must be updated within the hour.

The conventions are:

- Event timestamps are ISO-8601 UTC strings.
- `t` is an integer minute index from `Incident.window.start`.
- IDs are short readable strings (`E-001`, `H2`, `EV-05`, `I3`).
- `StateChange.from` is spelled `from_` in Python and `from` in JSON.

## REST API (prefix `/api`)

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/health` | | `HealthResponse {ok, llm_mode}` |
| GET | `/incidents` | | `Incident[]` |
| POST | `/investigations` | `{incident_id, mode: "replay" \| "live"}` | `{investigation_id}`; runs in the background |
| GET | `/investigations/{id}` | | `Investigation` (frontend polls every 1 s) |
| POST | `/investigations/{id}/approval` | `Approval` | `Investigation`. Approve leads to execute and verify; reject leads to replan. Returns 409 unless `awaiting_approval`. |
| POST | `/simulate` | `{incident_id, intervention_ids[]}` | `SimulationResult` |

## Stages

`created → timeline → hypotheses → evidence → testing → root_cause → counterfactual → awaiting_approval → executing → verifying → resolved`, plus `replanning` and `failed`.

## Engine entry points (frozen signatures)

Evidence engine (Vinayak, `evidence/`):

```python
build_timeline(incident_id) -> list[Event]
seed_hypotheses(incident_id, timeline) -> list[Hypothesis]
gather_evidence(incident_id, hypothesis) -> list[Evidence]
test_hypothesis(hypothesis, evidence) -> Hypothesis
determine_root_cause(hypotheses, evidence, timeline) -> RootCause
```

Counterfactual engine (Goyal, `simulation/`):

```python
load_system_model(incident_id) -> SystemModel
generate_interventions(root_cause, model) -> list[Intervention]
simulate(model, interventions, seed=0) -> SimulationResult    # pure, no I/O, no LLM; [] = baseline
rank(results, interventions) -> list[RankedIntervention]
execute(intervention, model) -> ExecutionResult              # simulated environment only
verify(execution, model, seed) -> VerificationResult
replan(failed, ranking, model) -> list[RankedIntervention]
get_intervention(intervention_id) -> Intervention           # helper used by the backend
```

Agent (Rohit, `agent/`):

```python
orchestrator.run(investigation_id, store, mode=None)
orchestrator.resume_after_approval(investigation_id, approval, store, mode=None)
```

## Data contract

Every incident folder `data/incidents/<slug>/` contains these files:

- `incident.json`
- `events.json`
- `metrics.json`
- `system_model.json`
- `ground_truth.json`, which holds `{root_cause_hypothesis_id, rejected_hypothesis_ids, preventing_intervention_ids}`. **Only tests read it. The agent never does.**

Events that change system state carry `state_change`. `SystemModel.param_changes` mirrors them, which is what lets the simulator replay the incident with an event removed or a parameter changed.
