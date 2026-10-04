# agent/ (owner: Rohit)

- `orchestrator.py` is a deterministic state machine. It advances `Investigation.stage`, logs an `AgentStep` for every thought and tool call, and publishes snapshots to the store.
- `tools.py` is the **single wiring point** to `evidence/`, `simulation/` and `data/`.
- `llm.py` holds `LLMClient`. `replay` (the default) reads `recordings/<incident_id>.json`. `live` calls any OpenAI-compatible endpoint set by `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. If that configuration is missing or a live call fails, the client falls back to replay for the rest of the run, and the orchestrator logs one `decision` step saying why. `Investigation.mode` stays `live`. With `RECORD=1` (exactly `1`), each successful live response of an investigation run is merged into `recordings/<incident_id>.json` under its key, so replay reproduces that run. Resume and replan runs are never recorded.
- With `LLM_HYPOTHESES=1` (exactly `1`, off by default), the orchestrator asks the LLM (key `hypotheses.propose`) for up to 2 extra hypotheses after the seeds. They get `origin="llm"`, ids after the last seed, and one `decision` step each. The evidence engine gathers, tests and rejects them like seeds; malformed output, an unavailable LLM or a replay without a recorded proposal adds nothing.
- `prompts/` holds the stage-specific prompt templates (`system.md` plus one `thought.<stage>.md` per replay key), filled with real investigation state. See `prompts/README.md`.

The LLM narrates and proposes, while the engines decide.

`STEP_DELAY_MS` (default 700) paces the UI. The orchestrator pauses once after each stage change and each step, except tool calls and the resting stages (`awaiting_approval`, `resolved`, `failed`), which are already on screen. In replay, the INC-2041 demo reaches `awaiting_approval` in about 27 s (39 pauses) and goes from approval to `resolved` in about 4 s (6 pauses). Live mode adds the LLM's own latency. A blank, non-numeric or non-finite value falls back to 700, and 0 or a negative value means no pause. Tests set it to 0.
