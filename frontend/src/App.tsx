// FOUNDATION UI: unstyled placeholders that prove the end-to-end wiring. Owner: Aryan.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { Decision, Incident, Investigation, Stage } from "./types";

const POLL_MS = 1000;
const TERMINAL: Stage[] = ["resolved", "failed"];

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [incidentId, setIncidentId] = useState("");
  const [investigationId, setInvestigationId] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listIncidents()
      .then((list) => {
        setIncidents(list);
        if (list.length) setIncidentId(list[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Poll GET /api/investigations/{id} every second until the investigation is resolved or failed.
  useEffect(() => {
    if (!investigationId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const latest = await api.getInvestigation(investigationId);
        if (stopped) return;
        setInvestigation(latest);
        if (TERMINAL.includes(latest.stage)) stopped = true;
      } catch (e) {
        setError((e as Error).message);
      }
    };
    tick();
    const timer = setInterval(() => !stopped && tick(), POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [investigationId]);

  const investigate = async () => {
    setError(null);
    setInvestigation(null);
    try {
      setInvestigationId((await api.startInvestigation(incidentId)).investigation_id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const decide = async (decision: Decision) => {
    if (!investigation?.recommendation) return;
    try {
      await api.submitApproval(investigation.id, {
        intervention_id: investigation.recommendation.intervention_id,
        decision,
        approver: "operator",
      });
      // restart polling in case it had stopped
      setInvestigationId(null);
      setTimeout(() => setInvestigationId(investigation.id), 0);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const inv = investigation;
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1>COUNTERFACT</h1>

      <section>
        <select value={incidentId} onChange={(e) => setIncidentId(e.target.value)}>
          {incidents.map((i) => (
            <option key={i.id} value={i.id}>
              {i.id}: {i.title}
            </option>
          ))}
        </select>{" "}
        <button onClick={investigate} disabled={!incidentId}>
          Investigate
        </button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </section>

      {inv && (
        <>
          <p>
            <strong>{inv.id}</strong>: stage <code>{inv.stage}</code>
            {inv.error && <span style={{ color: "crimson" }}> {inv.error}</span>}
          </p>

          <section>
            <h2>Timeline</h2>
            <ul>
              {inv.timeline.map((e) => (
                <li key={e.id}>
                  {e.ts.slice(11, 16)} [{e.kind}] {e.summary}
                  {e.state_change && (
                    <strong>
                      {" "}
                      ({e.state_change.param}: {String(e.state_change.from)} → {String(e.state_change.to)})
                    </strong>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2>Hypotheses</h2>
            <ul>
              {inv.hypotheses.map((h) => (
                <li key={h.id}>
                  {h.id} {h.title}: <code>{h.status}</code> ({h.confidence})
                  {h.rejection_reason && <em> rejected: {h.rejection_reason}</em>}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2>Root cause</h2>
            {inv.root_cause ? (
              <>
                <p>
                  {inv.root_cause.hypothesis_id}: {inv.root_cause.statement}
                </p>
                <ol>
                  {inv.root_cause.causal_chain.map((link) => (
                    <li key={link.event_id}>
                      {link.event_id}: {link.effect}
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <p>Pending</p>
            )}
          </section>

          <section>
            <h2>Counterfactual lab</h2>
            <ul>
              {inv.simulations.map((s) => (
                <li key={s.intervention_ids.join("+") || "baseline"}>
                  {s.intervention_ids.join(" + ") || "baseline"}: {s.breach_minutes} breach min, peak{" "}
                  {s.peak_error_rate}, {s.prevented ? "prevented" : "not prevented"}
                </li>
              ))}
            </ul>
            <ol>
              {inv.ranking.map((r) => (
                <li key={r.intervention_id}>
                  {r.intervention_id} (score {r.score}): {r.reasons.join("; ")}
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h2>Approval</h2>
            {inv.recommendation && <p>Recommended: {inv.recommendation.intervention_id}</p>}
            <button onClick={() => decide("approved")} disabled={inv.stage !== "awaiting_approval"}>
              Approve
            </button>{" "}
            <button onClick={() => decide("rejected")} disabled={inv.stage !== "awaiting_approval"}>
              Reject
            </button>
            {inv.verification && (
              <p>
                Verification {inv.verification.passed ? "passed" : "failed"} for {inv.verification.intervention_id}
              </p>
            )}
          </section>

          <section>
            <h2>Agent steps</h2>
            <ol>
              {inv.steps.map((s) => (
                <li key={s.n}>
                  [{s.stage}/{s.kind}
                  {s.tool ? `:${s.tool}` : ""}] {s.output_summary}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </main>
  );
}
