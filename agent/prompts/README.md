# agent/prompts/ (owner: Rohit)

Prompt templates for live LLM mode go here, one file per prompt key (e.g. `thought.timeline.md`).

- `system.md` is sent as the system message with every prompt.
- `thought.<stage>.md` is named after its **replay key** in `agent/recordings/<incident_id>.json`. Renaming a file means renaming the recording key too, so don't.
- `{placeholders}` are filled by `orchestrator._facts()` from the real investigation state (event counts, hypothesis titles, test results, root cause, simulation outcomes, ranking, recommendation, replanning context). Only what earlier stages produced is available. A placeholder with no value renders as `unknown` instead of failing the run.
- Replay mode ignores the prompt text and looks up only the key, so editing a template never changes the replay demo.
