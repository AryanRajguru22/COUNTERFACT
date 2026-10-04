Incident {incident_id} "{incident_title}" on {service}.
Summary: {incident_summary}

The reconstructed timeline has {event_count} events and {state_change_count} state changes:
{state_changes}

The evidence engine already proposed {hypothesis_count} competing hypotheses:
{hypotheses}

Task: propose at most 2 additional root-cause hypotheses that are not already listed above and that metrics, traces, logs, deploy records or config could confirm or refute. Do not restate or rename an existing hypothesis.

For this request only, ignore the two-sentence narration rule. Answer with JSON only, no prose and no markdown, in exactly this shape:
[{{"title": "short name of the hypothesis", "mechanism": "one sentence on how it would cause this incident"}}]
Answer [] if you have nothing new to add.
