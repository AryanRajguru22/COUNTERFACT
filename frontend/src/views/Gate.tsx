import { useState } from "react";
import { ApiError } from "../api";
import { Badge, Button, Icon, Label, Notice, Panel, Pending, TONE_TEXT, cx, type Tone } from "../components/ui";
import { baselineOf, describeAction, droppedInterventionIds, interventionRows, interventionTitle } from "../lib/derive";
import { effort } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { Approval, Decision, Investigation } from "../types";

const RISK_TONE: Record<string, Tone> = { low: "secondary", med: "tertiary", high: "error" };
const MAX_ATTEMPTS = 3;

export default function Gate({
  inv,
  nav,
  approver,
  onApprover,
  onDecide,
}: {
  inv: Investigation;
  nav: Nav;
  approver: string;
  onApprover: (name: string) => void;
  onDecide: (approval: Approval) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  const rows = interventionRows(inv).filter((r) => r.ranked);
  const dropped = droppedInterventionIds(inv);
  const waiting = inv.stage === "awaiting_approval";
  const recommendation = inv.recommendation;
  const baseline = baselineOf(inv.simulations);

  if (rows.length === 0) {
    return <Pending title="Preparing the recommendation" hint="The simulator ranks every candidate before anything is put in front of you." rows={3} />;
  }

  const selectedId = (picked && rows.some((r) => r.intervention.id === picked) ? picked : recommendation?.intervention_id) ?? rows[0].intervention.id;
  const selected = rows.find((r) => r.intervention.id === selectedId) ?? rows[0];
  const top = recommendation ? rows.find((r) => r.intervention.id === recommendation.intervention_id) : undefined;
  const isRecommended = selected.intervention.id === recommendation?.intervention_id;
  const lastVerification = inv.verification && !inv.verification.passed ? inv.verification : null;
  const noteMissing = note.trim() === "";

  const decide = async (decision: Decision) => {
    setError(null);
    if (!approver.trim()) {
      setError("Enter the approver's name first. It is recorded with the decision.");
      return;
    }
    if (decision === "rejected" && noteMissing) {
      setError("A rejection needs a note explaining why. It is recorded and used when the options are re-ranked.");
      return;
    }
    setSubmitting(decision);
    try {
      await onDecide({ intervention_id: selected.intervention.id, decision, approver: approver.trim(), note: note.trim() });
      setNote("");
      setPicked(null);
    } catch (e) {
      // 409: someone else already decided, or the choice was dropped by a replan; 422: missing note; 400: unknown id.
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      {inv.attempts > 0 && (
        <Notice
          tone={inv.stage === "failed" ? "error" : "tertiary"}
          icon="refresh"
          title={`Attempt ${inv.attempts} of ${MAX_ATTEMPTS}: ${lastVerification ? `${lastVerification.intervention_id} failed verification` : inv.approval ? `${inv.approval.intervention_id} was ${inv.approval.decision}` : "options re-ranked"}`}
        >
          {lastVerification ? (
            <>
              Failing checks: {lastVerification.checks.filter((c) => !c.passed).map((c) => `${c.name} (expected ${c.expected}, observed ${c.observed})`).join("; ") || "stress test"}.{" "}
            </>
          ) : inv.approval?.note ? (
            <>
              Note: “{inv.approval.note}”.{" "}
            </>
          ) : null}
          {rows.length} option{rows.length === 1 ? "" : "s"} remain
          {dropped.length > 0 && <> ({dropped.map((id) => `${id} ${interventionTitle(inv, id)}`).join(", ")} removed)</>}.
          {inv.stage === "replanning" && " Re-ranking now…"}
        </Notice>
      )}

      {top && recommendation && (
        <Panel glow="primary" className="flex flex-col justify-between gap-space-xl !p-space-xl lg:flex-row">
          <div className="flex max-w-2xl flex-col gap-space-md">
            <div className="flex flex-wrap items-center gap-space-lg">
              <Badge tone="primary" className="!bg-primary !text-on-primary font-bold shadow-[0_0_10px_rgba(76,215,246,0.4)]">Top ranked (#{recommendation.rank})</Badge>
              <span className="font-mono-data font-bold text-primary">{top.intervention.id}: {top.intervention.title}</span>
            </div>
            <h2 className="font-headline-xl text-on-surface">
              {recommendation.prevented ? "Approval recommended" : "Best available option does not fully prevent the breach"}
            </h2>
            <p className="font-body-md text-on-surface-variant">
              Composite score <strong className="font-mono-data text-primary">{recommendation.score}</strong>. {recommendation.reasons.join("; ")}. {top.intervention.rationale}
            </p>
          </div>
          <dl className="inset-well flex min-w-[240px] flex-col justify-center gap-space-md p-space-xl font-mono-data text-on-surface">
            <div className="flex justify-between"><dt>Risk rating:</dt><dd className={cx("font-semibold uppercase", TONE_TEXT[RISK_TONE[top.intervention.risk] ?? "muted"])}>{top.intervention.risk}</dd></div>
            <div className="flex justify-between"><dt>Effort:</dt><dd className="font-semibold">{effort(top.intervention.effort_hours)}</dd></div>
            <div className="flex justify-between">
              <dt>Avoided breach:</dt>
              <dd className={cx("font-semibold", recommendation.prevented ? "text-secondary" : "text-tertiary")}>
                {recommendation.breach_minutes_avoided}{baseline ? ` of ${baseline.breach_minutes}` : ""} min
              </dd>
            </div>
          </dl>
        </Panel>
      )}

      <div className="glass overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
        <div className="flex items-center justify-between border-b border-white/10 p-space-lg">
          <Label className="!text-on-surface">Intervention decision matrix</Label>
          <span className="font-mono-data-compact text-outline">Sorted by rank · pick any row to decide on it</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left font-mono-data">
            <thead>
              <tr className="border-b border-white/10 bg-[#12151c]/80 font-mono-label-caps uppercase text-outline">
                <th className="px-space-xl py-space-lg">Rank</th>
                <th className="px-space-xl py-space-lg">Intervention</th>
                <th className="px-space-xl py-space-lg">Category</th>
                <th className="px-space-xl py-space-lg">Risk</th>
                <th className="px-space-xl py-space-lg">Effort</th>
                <th className="px-space-xl py-space-lg">Breach avoided</th>
                <th className="px-space-xl py-space-lg">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map(({ intervention, ranked }) => {
                const r = ranked!;
                const isSelected = intervention.id === selected.intervention.id;
                const noEffect = r.breach_minutes_avoided === 0;
                return (
                  <tr
                    key={intervention.id}
                    onClick={() => setPicked(intervention.id)}
                    aria-selected={isSelected}
                    className={cx("cursor-pointer transition-colors", isSelected ? "bg-primary/10 hover:bg-primary/15" : "hover:bg-white/5", noEffect && !isSelected && "opacity-60")}
                  >
                    <td className={cx("px-space-xl py-space-lg font-bold", isSelected ? "text-primary" : "text-on-surface")}>
                      <button type="button" className="outline-offset-4" onClick={() => setPicked(intervention.id)} aria-label={`Select ${intervention.id}`}>{r.rank}</button>
                    </td>
                    <td className="px-space-xl py-space-lg font-body-sm">
                      <div className={cx("font-semibold", noEffect ? "text-on-surface-variant line-through" : "text-on-surface")}>{intervention.id}: {intervention.title}</div>
                      <div className="mt-0.5 max-w-md text-outline">{r.reasons.join(" · ")}</div>
                    </td>
                    <td className="px-space-xl py-space-lg text-outline">{intervention.category}</td>
                    <td className="px-space-xl py-space-lg"><Badge tone={RISK_TONE[intervention.risk] ?? "muted"}>{intervention.risk}</Badge></td>
                    <td className="px-space-xl py-space-lg tabular-nums">{effort(intervention.effort_hours)}</td>
                    <td className={cx("px-space-xl py-space-lg tabular-nums", r.prevented ? "text-secondary" : noEffect ? "text-error" : "text-tertiary")}>
                      {r.breach_minutes_avoided}{baseline ? ` of ${baseline.breach_minutes}` : ""} min
                    </td>
                    <td className={cx("px-space-xl py-space-lg font-mono-metric-lg !text-[16px] tabular-nums", isSelected ? "text-primary" : noEffect ? "text-error" : "text-on-surface")}>{r.score}</td>
                  </tr>
                );
              })}
              {dropped.map((id) => (
                <tr key={id} className="opacity-40">
                  <td className="px-space-xl py-space-lg text-outline">—</td>
                  <td className="px-space-xl py-space-lg font-body-sm line-through">{id}: {interventionTitle(inv, id)}</td>
                  <td colSpan={5} className="px-space-xl py-space-lg text-outline">removed by replan</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Panel className="flex flex-col gap-space-xl !p-space-xl">
        <div className="flex items-center gap-space-xl">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/20 shadow-[0_0_12px_rgba(76,215,246,0.3)]">
            <Icon name="verified_user" className="text-[24px] text-primary" />
          </div>
          <div className="min-w-0">
            <Label>Human-in-the-loop sign-off</Label>
            <div className="font-headline-sm text-on-surface">
              {waiting ? (
                <>Decide on <span className="text-primary">{selected.intervention.id}: {selected.intervention.title}</span></>
              ) : inv.approval ? (
                <>
                  {inv.approval.approver} {inv.approval.decision} {inv.approval.intervention_id}
                  {inv.stage === "replanning" ? "; replanning…" : ""}
                </>
              ) : (
                "Waiting for the investigation to reach the gate"
              )}
            </div>
          </div>
        </div>

        {waiting && (
          <>
            {!isRecommended && (
              <Notice tone="tertiary" icon="warning" title={`${selected.intervention.id} is not the recommendation`}>
                {selected.ranked?.prevented
                  ? "It still prevents the breach, but another option scored higher."
                  : "It does not prevent the breach in simulation, so verification is expected to fail and the options will be re-ranked."}
              </Notice>
            )}
            <div className="inset-well flex flex-wrap items-center gap-space-md p-space-lg font-mono-data-compact">
              <Icon name="terminal" className="text-[16px] text-outline" />
              <span className="text-outline">Will apply (simulated environment only):</span>
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-on-surface">{describeAction(selected.intervention.action)}</code>
            </div>
            <div className="grid grid-cols-1 gap-space-xl md:grid-cols-3">
              <label className="flex flex-col gap-1 md:col-span-1">
                <Label>Approver</Label>
                <input
                  value={approver}
                  onChange={(e) => onApprover(e.target.value)}
                  autoComplete="name"
                  className="rounded border border-white/15 bg-[#08090c] px-space-lg py-2 font-mono-data text-on-surface outline-none transition-colors focus:border-primary"
                  placeholder="your name"
                />
              </label>
              <label className="flex flex-col gap-1 md:col-span-2">
                <Label>Note {noteMissing ? "(required to reject)" : ""}</Label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  className="resize-y rounded border border-white/15 bg-[#08090c] px-space-lg py-2 font-body-sm text-on-surface outline-none transition-colors focus:border-primary"
                  placeholder="Why this decision? A rejection note is recorded and shown to the next reviewer."
                />
              </label>
            </div>
            {error && (
              <p role="alert" className="flex items-start gap-space-md font-body-sm text-error">
                <Icon name="error" className="mt-0.5 text-[16px]" />
                {error}
              </p>
            )}
            <div className="flex flex-wrap items-center justify-end gap-space-lg">
              <Button variant="danger" icon="close" onClick={() => decide("rejected")} disabled={submitting !== null} className="uppercase">
                {submitting === "rejected" ? "Rejecting…" : "Reject"}
              </Button>
              <Button variant="primary" icon="check" onClick={() => decide("approved")} disabled={submitting !== null} className="!px-space-xl !py-2 uppercase">
                {submitting === "approved" ? "Approving…" : "Approve & execute verification"}
              </Button>
            </div>
          </>
        )}

        {!waiting && inv.stage !== "failed" && inv.approval && (
          <div className="flex flex-wrap items-center justify-between gap-space-md font-mono-data-compact text-outline">
            <span>
              Recorded {inv.approval.at ?? ""}
              {inv.approval.note ? ` · “${inv.approval.note}”` : ""}
            </span>
            {(inv.stage === "executing" || inv.stage === "verifying" || inv.stage === "resolved") && (
              <Button icon="arrow_forward" className="flex-row-reverse" onClick={() => nav.go("verification")}>View execution & verification</Button>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
