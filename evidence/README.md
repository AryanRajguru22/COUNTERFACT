# evidence/ (owner: Vinayak)

This folder covers timeline reconstruction, competing hypotheses, evidence gathering, hypothesis testing and root-cause selection. The signatures are frozen; see `contracts/CONTRACTS.md`.

Everything here is deterministic. It reads only `data/` and makes no network or LLM calls, so replay mode is reliable.

| Step | File | How it works |
| --- | --- | --- |
| Timeline | `timeline.py` | Takes the events from `events.json` and adds the first sightings found in raw telemetry (first pool timeout log, first failed trace, first retry log) as `E-011` and up. The result is ordered by `(t, ts, id)`. |
| Hypotheses | `hypotheses.py` | One detector per signal family, run over the timeline: pool cut plus batch job (H1), deploy before onset (H2), external notice (H3), database-flavoured errors (H4). |
| Evidence | `evidence.py` | 17 analyses over metrics, traces, logs, change records and config. Each one yields an `Evidence` with a stance per hypothesis, source events, a weight and the prediction each hypothesis makes. |
| Testing | `hypotheses.py` | `test_hypothesis` turns each prediction into a `HypothesisTest`. A hypothesis is rejected on any refutation with weight >= 0.85, or when the refuting weight is greater than the supporting weight. The rejection reason names the decisive evidence. |
| Root cause | `root_cause.py` | Takes the strongest survivor. Its causal chain is built from the timeline events cited by its supporting evidence, plus the symptoms that no rival explains. |

Evidence weights follow a fixed rubric. Decisive evidence (a natural experiment or a direct measurement) scores 0.85 to 0.95. Strong evidence scores 0.6 to 0.8. Coincidence or a symptom that several hypotheses share scores 0.3 to 0.4. Where an effect is measured, the weight is scaled by its size.

For INC-2041, the rollback that changed nothing rejects H2. Normal gateway spans, with no failed request ever reaching the gateway, reject H3. The idle database rejects H4. H1 is confirmed at 0.93 confidence, with a 10-link chain that runs from CHG-881 to recovery.
