Incident {incident_id} "{incident_title}" on {service}.
Root cause {root_cause_id}: {root_cause_title}.

Without any change, the incident breaches the SLO for {baseline_breach_minutes} minutes.
{intervention_count} interventions were simulated:
{intervention_outcomes}

Ranking:
{ranking}

Replanning context: {replan_context}.

Recommended: {recommendation_id} {recommendation_title} (rank {recommendation_rank}, score {recommendation_score}).
Prevents the breach: {recommendation_prevents}. Breach minutes avoided: {recommendation_breach_minutes_avoided}.
Engine reasons: {recommendation_reasons}.

Stage: recommendation. A human must approve before anything is executed.
Explain why this intervention is recommended over the others and what the approver should weigh.
