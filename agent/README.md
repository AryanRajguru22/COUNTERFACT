# agent/ (owner: Rohit)

- `orchestrator.py` is a deterministic state machine. It advances `Investigation.stage`, logs an `AgentStep` for every thought and tool call, and publishes snapshots to the store.
- `tools.py` is the **single wiring point** to `evidence/`, `simulation/` and `data/`.
- `llm.py` holds `LLMClient`. `replay` (the default) reads `recordings/<incident_id>.json`. `live` calls any OpenAI-compatible endpoint set by `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. If that configuration is missing or a live call fails, the client falls back to replay for the rest of the run, and the orchestrator logs one `decision` step saying why. `Investigation.mode` stays `live`.
- `prompts/` holds prompt templates (empty at foundation).

The LLM narrates and proposes, while the engines decide. Set `STEP_DELAY_MS` (default 600) to pace the UI. Tests set it to 0.
