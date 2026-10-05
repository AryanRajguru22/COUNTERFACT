import { useMemo } from "react";
import ErrorChart, { type ChartMarker } from "../components/charts/ErrorChart";
import { Badge, Button, Icon, Kpi, Label, Meter, Panel, cx } from "../components/ui";
import type { IncidentData } from "../hooks/useBackend";
import {
  baselineOf,
  breachWindow,
  eventClass,
  estimatedFailedRequests,
  metricByName,
  pipeline,
  sloOf,
  sortedTimeline,
  type StepState,
  type ViewId,
} from "../lib/derive";
import { clock, compactNumber, minuteLabel, pct, pctWhole } from "../lib/format";
import type { Investigation } from "../types";

const STEP_TEXT: Record<StepState, string> = { done: "Completed", active: "In progress", waiting: "Needs your approval", pending: "Pending", failed: "Stopped here" };

export default function Overview({ inv, data, onNavigate }: { inv: Investigation; data: IncidentData; onNavigate: (v: ViewId) => void }) {
  const slo = sloOf(data.model);
  const baseline = baselineOf(inv.simulations);
  const observed = metricByName(data.metrics, "checkout_5xx_rate");
  const observedValues = useMemo(() => observed?.points.map((p) => p.value) ?? [], [observed]);
  // Prefer observed telemetry for the incident's own numbers; fall back to the simulated baseline.
  const errorSeries = observedValues.length ? observedValues : (baseline?.series.error_rate ?? []);
  const breach = useMemo(() => breachWindow(errorSeries, slo), [errorSeries, slo]);
  const peak = errorSeries.length ? Math.max(...errorSeries) : null;
  const failed = data.model && baseline ? estimatedFailedRequests(data.model.exogenous.demand_rps, baseline.series.error_rate) : null;
  const confidence = inv.root_cause?.confidence ?? null;
  const steps = pipeline(inv);

  const markers: ChartMarker[] = useMemo(
    () =>
      sortedTimeline(inv.timeline)
        .filter((e) => e.state_change || e.attributes["causal"] === true)
        .map((e) => ({ id: e.id, t: e.t, label: e.summary, cls: eventClass(e) })),
    [inv.timeline],
  );

  const recommendation = inv.recommendation;
  const recommended = recommendation ? inv.interventions.find((i) => i.id === recommendation.intervention_id) : undefined;
  const resolved = inv.stage === "resolved";
  const failedRun = inv.stage === "failed";
  const ranked = [...inv.hypotheses].sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <div className="glass relative flex flex-col justify-between gap-space-xl overflow-hidden p-space-xl shadow-[0_8px_32px_rgba(0,0,0,0.4)] xl:flex-row xl:items-center">
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative z-10 flex flex-col gap-space-md">
          <div className="flex flex-wrap items-center gap-space-md">
            <Badge tone="error" className="font-bold">
              <span className="h-1.5 w-1.5 animate-ping rounded-full bg-error" />
              {inv.incident.severity} incident
            </Badge>
            <span className="font-mono-data font-semibold text-primary">{inv.incident.id}</span>
            <span className="text-outline">•</span>
            <span className="font-mono-data text-on-surface-variant">{inv.incident.service}</span>
            <span className="text-outline">•</span>
            {resolved ? (
              <Badge tone="secondary">Fix verified</Badge>
            ) : failedRun ? (
              <Badge tone="error">Investigation stopped</Badge>
            ) : inv.stage === "awaiting_approval" ? (
              <Badge tone="primary">Awaiting your approval</Badge>
            ) : (
              <Badge tone="tertiary">Investigation in progress</Badge>
            )}
          </div>
          <h1 className="font-headline-xl text-on-surface">{inv.incident.title}</h1>
          <p className="max-w-4xl font-body-md text-on-surface-variant">{inv.incident.summary}</p>
        </div>
        <div className="relative z-10 flex shrink-0 flex-col gap-space-md">
          {inv.stage === "awaiting_approval" ? (
            <Button variant="primary" icon="verified_user" onClick={() => onNavigate("gate")} className="!px-space-xl !py-2 uppercase">
              Review recommendation
            </Button>
          ) : (
            <Button
              variant="primary"
              icon="science"
              disabled={inv.ranking.length === 0}
              onClick={() => onNavigate("lab")}
              className="!px-space-xl !py-2 uppercase"
            >
              Launch Counterfactual Lab
            </Button>
          )}
          {inv.ranking.length === 0 && <span className="text-center font-mono-data-compact text-outline">Unlocks when the simulations finish</span>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-space-md md:grid-cols-4">
        <Kpi
          label="Peak error rate (5xx)"
          tone="error"
          value={peak === null ? "—" : pct(peak, 1)}
          sub={<span>SLO limit {pct(slo, 1)}{peak !== null && ` · +${pct(Math.max(0, peak - slo), 1)} over`}</span>}
        />
        <Kpi
          label="SLO breach duration"
          tone="error"
          value={breach ? breach.minutes : "—"}
          unit={breach ? "min" : undefined}
          sub={breach ? `${minuteLabel(inv.incident.window.start, breach.start)} – ${minuteLabel(inv.incident.window.start, breach.end)} UTC` : "waiting for telemetry"}
        />
        <Kpi
          label="Est. failed checkouts"
          tone="tertiary"
          value={failed === null ? "—" : compactNumber(failed)}
          sub="simulated baseline, demand × error rate"
        />
        <Kpi
          label="Causal diagnosis confidence"
          tone="secondary"
          value={confidence === null ? "—" : pctWhole(confidence)}
          sub={
            inv.root_cause
              ? `${inv.root_cause.hypothesis_id} confirmed`
              : inv.hypotheses.length
                ? "testing hypotheses…"
                : "no hypotheses yet"
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-space-md lg:grid-cols-3">
        <Panel className="flex flex-col gap-space-md lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-space-md">
              <Icon name="show_chart" className="text-[16px] text-primary" />
              <Label className="!text-on-surface">
                Telemetry · checkout 5xx · {minuteLabel(inv.incident.window.start, 0)}–{minuteLabel(inv.incident.window.start, inv.incident.window.minutes - 1)} UTC
              </Label>
            </div>
            <span className="font-mono-data-compact text-outline">{observedValues.length ? "observed" : "simulated baseline"}</span>
          </div>
          {errorSeries.length ? (
            <ErrorChart
              ariaLabel="Checkout 5xx error rate over the incident window"
              series={[{ id: "obs", label: observedValues.length ? "Observed 5xx" : "Baseline 5xx", values: errorSeries, color: "#ffb4ab", area: true, width: 2.5 }]}
              slo={slo}
              minutes={inv.incident.window.minutes}
              windowStart={inv.incident.window.start}
              breach={breach}
              markers={markers}
              height={230}
            />
          ) : (
            <div className="skeleton h-[230px]" />
          )}
          <div className="flex flex-wrap items-center gap-space-lg font-mono-data-compact text-outline">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rotate-45 bg-tertiary" /> causal state change</span>
            <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 border-t border-dashed border-tertiary" /> SLO threshold</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-3 bg-error/20" /> breach window</span>
          </div>
        </Panel>

        <Panel className="flex flex-col justify-between gap-space-md">
          <div className="flex flex-col gap-space-md">
            <div className="flex items-center justify-between">
              <Label className="!text-on-surface">Hypotheses rank</Label>
              <button type="button" className="flex items-center gap-0.5 font-mono-data-compact text-primary hover:underline" onClick={() => onNavigate("hypotheses")}>
                View details <Icon name="arrow_forward" className="text-[14px]" />
              </button>
            </div>
            {ranked.length === 0 && <div className="skeleton h-24" />}
            <ul className="flex flex-col gap-space-md">
              {ranked.map((h) => {
                const confirmed = h.status === "confirmed";
                const rejected = h.status === "rejected";
                return (
                  <li
                    key={h.id}
                    className={cx(
                      "flex items-center justify-between gap-space-md rounded border p-space-md",
                      confirmed ? "border-secondary/50 bg-secondary-container/20 shadow-[0_0_10px_rgba(78,222,163,0.15)]" : "border-white/5 bg-[#101318]/60",
                      rejected && "opacity-70",
                    )}
                  >
                    <span className={cx("min-w-0 truncate font-mono-data-compact", confirmed ? "font-semibold text-secondary" : "text-on-surface-variant", rejected && "line-through")} title={h.title}>
                      {h.id}: {h.title}
                    </span>
                    <Badge tone={confirmed ? "secondary" : rejected ? "error" : "muted"}>{pctWhole(h.confidence)} {h.status}</Badge>
                  </li>
                );
              })}
            </ul>
          </div>
          {recommended && recommendation ? (
            <div className="inset-well flex items-start gap-space-md p-space-lg">
              <Icon name="verified" className="mt-0.5 text-[18px] text-primary" />
              <span className="font-body-sm text-on-surface-variant">
                Recommended fix: <strong className="text-on-surface">{recommended.id} · {recommended.title}</strong>
                {recommendation.prevented ? ` removes ${recommendation.breach_minutes_avoided} of the breach minutes.` : ` is the best available option.`}
              </span>
            </div>
          ) : (
            <div className="inset-well flex items-center gap-space-md p-space-lg font-body-sm text-on-surface-variant">
              <Icon name="hourglass_top" className="animate-pulse text-[18px] text-primary" /> The recommendation appears once counterfactuals finish.
            </div>
          )}
        </Panel>
      </div>

      <div className="flex flex-col gap-space-md">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-on-surface">Investigation pipeline</h2>
          <span className="font-mono-data-compact text-outline">
            {steps.filter((s) => s.state === "done").length} of {steps.length} stages complete
          </span>
        </div>
        <div className="grid grid-cols-2 gap-space-md md:grid-cols-4 xl:grid-cols-7">
          {steps.map((step, i) => (
            <button
              key={step.id}
              type="button"
              onClick={() => onNavigate(step.view)}
              className={cx(
                "glass flex h-28 flex-col justify-between p-space-lg text-left transition-all hover:border-white/25",
                step.state === "active" && "border-primary/50 shadow-[0_0_16px_rgba(76,215,246,0.2)]",
                step.state === "waiting" && "border-primary/60 shadow-[0_0_16px_rgba(76,215,246,0.25)]",
                step.state === "failed" && "border-error/50",
                step.state === "pending" && "opacity-60",
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono-data text-outline">{String(i + 1).padStart(2, "0")}</span>
                {step.state === "done" ? (
                  <Icon name="check_circle" className="text-[18px] text-secondary" />
                ) : step.state === "failed" ? (
                  <Icon name="error" className="text-[18px] text-error" />
                ) : step.state === "pending" ? (
                  <Icon name="radio_button_unchecked" className="text-[18px] text-outline" />
                ) : (
                  <Icon name={step.state === "waiting" ? "front_hand" : "play_circle"} className="animate-pulse text-[18px] text-primary" />
                )}
              </div>
              <div>
                <div className="font-body-md text-body-md font-medium text-on-surface">{step.label}</div>
                <span className={cx("font-mono-data-compact", step.state === "done" ? "text-secondary" : step.state === "failed" ? "text-error" : step.state === "pending" ? "text-outline" : "text-primary")}>
                  {STEP_TEXT[step.state]}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="inset-well flex flex-col items-center justify-between gap-space-md p-space-lg sm:flex-row">
        <div className="flex items-center gap-space-lg">
          <Icon name="tune" className="text-[20px] text-outline" />
          <span className="font-body-sm text-on-surface-variant">
            {inv.root_cause
              ? `Root cause: ${inv.hypotheses.find((h) => h.id === inv.root_cause?.hypothesis_id)?.title ?? inv.root_cause.hypothesis_id}`
              : `Detected ${clock(inv.incident.detected_at)} UTC. The agent is still working toward a root cause.`}
          </span>
        </div>
        <div className="flex w-full items-center gap-space-md sm:w-60">
          <Label>Diagnosis</Label>
          <Meter value={confidence ?? 0} tone="secondary" />
        </div>
      </div>
    </div>
  );
}
