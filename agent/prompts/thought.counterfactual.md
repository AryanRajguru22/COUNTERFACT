Incident {incident_id} "{incident_title}" on {service}.

Root cause {root_cause_id} {root_cause_title} (confidence {root_cause_confidence}):
{root_cause_statement}

Causal chain ({causal_chain_length} links):
{causal_chain}

Stage: counterfactual. You are about to replay the incident in the simulator, once as it happened and once per candidate intervention, to see which would have prevented the SLO breach.
Explain which link in this causal chain a useful intervention has to break.
