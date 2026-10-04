import { useState } from "react";
import { Badge, Button, Icon, Label, Notice, Panel, Pending, cx } from "../components/ui";
import { baselineOf, describeAction, interventionTitle, simulationFor } from "../lib/derive";
import { downloadText } from "../lib/download";
import { humanize, pct } from "../lib/format";
import type { Nav } from "../lib/nav";
import { buildReport } from "../lib/report";
import type { Investigation } from "../types";

const PHASES = [
  { id: "executing", label: "Apply to simulated environment", icon: "terminal" },
  { id: "verifying", label: "Replay incident & check SLO", icon: "rule" },
  { id: "done", label: "Stress test", icon: "speed" },
] as const;

export default function Verification({ inv, nav }: { inv: Investigation; nav: Nav }) {
  const [copied, setCopied] = useState(false);
  const { execution, verification } = inv;
  const running = inv.stage === "executing" || inv.stage === "verifying";

  if (!execution && !running) {
    if (inv.stage === "failed") {
      return (
        <Notice tone="error" icon="report" title="The investigation stopped before anything was executed">
          {inv.error ?? "No reason was recorded."}
        </Notice>
      );
    }
    return (
      <Pending
        title="Nothing has been executed yet"
        hint={inv.stage === "awaiting_approval" ? "Approve an intervention at the gate; it is applied to the simulated environment and verified here." : "Execution starts after you approve an intervention."}
        rows={2}
      />
    );
  }

  const intervention = inv.interventions.find((i) => i.id === (execution?.intervention_id ?? inv.approval?.intervention_id));
  const baseline = baselineOf(inv.simulations);
  const sim = intervention ? simulationFor(inv.simulations, [intervention.id]) : undefined;
  const passed = verification?.passed === true;
  const failed = verification !== null && !verification.passed;
  const phase = inv.stage === "executing" ? 0 : inv.stage === "verifying" ? 1 : 3;

  const copySummary = async () => {
    const text = `${inv.incident.id}: ${intervention ? `${intervention.id} ${intervention.title}` : "intervention"} ${passed ? "verified" : "not verified"} in the simulated environment.`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <Panel glow={passed ? "secondary" : failed ? "error" : "primary"} className="flex flex-col justify-between gap-space-xl !p-space-xl md:flex-row md:items-center">
        <div className="flex flex-col gap-space-md">
          <div className="flex flex-wrap items-center gap-space-lg">
            <Badge tone={running ? "tertiary" : execution?.status === "applied" ? "secondary" : "error"} className="font-bold">
              {running ? "Executing" : execution?.status === "applied" ? "Execution completed" : "Execution failed"}
            </Badge>
            <span className="font-mono-data text-outline">Target: simulated environment (nothing in production is touched)</span>
          </div>
          <h2 className="font-headline-xl text-on-surface">
            {running
              ? `Applying ${intervention?.id ?? "the fix"} and replaying the incident…`
              : passed
                ? `Verified: all ${verification.checks.length} checks and the stress test passed`
                : failed
                  ? `Verification failed for ${verification.intervention_id}`
                  : "Execution recorded"}
          </h2>
          {intervention && (
            <p className="font-body-md text-on-surface-variant">
              {intervention.id} · {intervention.title}: <code className="rounded bg-white/5 px-1 text-on-surface">{describeAction(intervention.action)}</code>
            </p>
          )}
        </div>
        <div
          className={cx(
            "flex shrink-0 items-center gap-space-lg rounded border px-space-xl py-2",
            running ? "border-primary/40 bg-primary/10" : passed ? "border-secondary/60 bg-secondary-container/30 shadow-[0_0_20px_rgba(78,222,163,0.25)]" : "border-error/60 bg-error-container/30",
          )}
        >
          <Icon name={running ? "autorenew" : passed ? "check_circle" : "cancel"} className={cx("text-[24px]", running ? "animate-spin text-primary" : passed ? "text-secondary" : "text-error")} />
          <div className="flex flex-col">
            <Label className={running ? "!text-primary" : passed ? "!text-secondary" : "!text-error"}>Status</Label>
            <span className={cx("font-mono-metric-lg !text-[15px]", running ? "text-primary" : passed ? "text-secondary" : "text-error")}>
              {running ? "IN PROGRESS" : passed ? "VERIFIED • PASSED" : "FAILED"}
            </span>
          </div>
        </div>
      </Panel>

      {running && (
        <Panel className="flex flex-col gap-space-xl !p-space-xl">
          <ol className="grid grid-cols-1 gap-space-md md:grid-cols-3">
            {PHASES.map((p, i) => {
              const done = phase > i;
              const active = phase === i;
              return (
                <li key={p.id} className={cx("flex items-center gap-space-lg rounded border p-space-lg transition-all", active ? "border-primary/50 bg-primary/10" : done ? "border-secondary/40 bg-secondary-container/10" : "border-white/10 opacity-60")}>
                  <Icon name={done ? "check_circle" : p.icon} className={cx("text-[20px]", done ? "text-secondary" : active ? "animate-pulse text-primary" : "text-outline")} />
                  <span className="font-mono-data text-on-surface">{p.label}</span>
                </li>
              );
            })}
          </ol>
          <div className="h-1 overflow-hidden rounded bg-white/10"><div className="h-full w-1/3 animate-shimmer rounded bg-primary" style={{ backgroundSize: "200% 100%" }} /></div>
        </Panel>
      )}

      {verification && (
        <div className="grid grid-cols-1 gap-space-md md:grid-cols-3">
          {verification.checks.map((check, i) => (
            <div key={check.name} className="glass animate-fade-up flex flex-col justify-between gap-space-md p-space-lg" style={{ animationDelay: `${i * 80}ms` }}>
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <Label>Invariant check #{i + 1}</Label>
                  <Badge tone={check.passed ? "secondary" : "error"} className="font-bold">{check.passed ? "Pass" : "Fail"}</Badge>
                </div>
                <span className="font-headline-sm font-semibold capitalize text-on-surface">{humanize(check.name)}</span>
                <p className="font-body-sm text-on-surface-variant">Expected {check.expected}</p>
              </div>
              <div className="inset-well flex justify-between p-space-md font-mono-data-compact text-on-surface">
                <span>Observed: <strong className={check.passed ? "text-secondary" : "text-error"}>{check.observed}</strong></span>
                {baseline && /breach/i.test(check.name) && <span className="text-outline">Historical: {baseline.breach_minutes} min</span>}
                {baseline && /peak/i.test(check.name) && <span className="text-outline">Historical: {pct(baseline.peak_error_rate)}</span>}
              </div>
            </div>
          ))}
          <div className="glass animate-fade-up flex flex-col justify-between gap-space-md p-space-lg" style={{ animationDelay: `${verification.checks.length * 80}ms` }}>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <Label>Stress test</Label>
                <Badge tone={verification.stress_test_passed ? "secondary" : "error"} className="font-bold">{verification.stress_test_passed ? "Pass" : "Fail"}</Badge>
              </div>
              <span className="font-headline-sm font-semibold text-on-surface">Stress variant</span>
              <p className="font-body-sm text-on-surface-variant">Reported by the verifier alongside the SLO checks.</p>
            </div>
          </div>
        </div>
      )}

      {execution && (
        <Panel className="flex flex-col gap-space-md">
          <Label>Applied changes (simulated environment)</Label>
          <ul className="flex flex-col gap-space-md">
            {execution.applied_changes.map((change, i) => (
              <li key={i} className="inset-well flex flex-wrap items-center gap-space-lg p-space-lg font-mono-data">
                <Icon name="deployed_code" className="text-[18px] text-primary" />
                <code className="text-on-surface">{describeAction(change)}</code>
                <Badge tone={execution.status === "applied" ? "secondary" : "error"}>{execution.status}</Badge>
              </li>
            ))}
          </ul>
          {sim && baseline && verification && (
            <p className="font-body-sm text-on-surface-variant">
              Replaying the incident with {execution.intervention_id}: peak error {pct(baseline.peak_error_rate)} → <strong className="text-on-surface">{pct(sim.peak_error_rate)}</strong>, breach {baseline.breach_minutes} → <strong className="text-on-surface">{sim.breach_minutes}</strong> min.
            </p>
          )}
        </Panel>
      )}

      {failed && inv.stage !== "failed" && (
        <Notice
          tone="tertiary"
          icon="refresh"
          title={`${verification.intervention_id} ${interventionTitle(inv, verification.intervention_id)} did not hold up`}
          action={<Button variant="primary" onClick={() => nav.go("gate")}>Back to the gate</Button>}
        >
          The remaining options were re-ranked. Attempt {inv.attempts} is recorded; approve the new recommendation or pick another row.
        </Notice>
      )}

      {inv.stage === "failed" && (
        <Notice tone="error" icon="report" title="The investigation stopped without a verified fix">
          {inv.error ?? "No reason was recorded."}
        </Notice>
      )}

      {passed && (
        <div className="glass flex flex-col items-center justify-between gap-space-lg p-space-lg sm:flex-row">
          <div className="flex items-center gap-space-lg">
            <Icon name="task_alt" className="text-[22px] text-secondary" />
            <span className="font-body-md text-on-surface-variant">
              Resolved after {inv.attempts} approval attempt{inv.attempts === 1 ? "" : "s"}. The decision, the evidence and the verification are in the report.
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-space-md">
            <Button icon={copied ? "check" : "content_copy"} onClick={copySummary}>{copied ? "Copied" : "Copy summary"}</Button>
            <Button variant="primary" icon="description" onClick={() => downloadText(`${inv.incident.id}-${inv.id}-report.md`, buildReport(inv), "text/markdown")}>
              Download report
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
