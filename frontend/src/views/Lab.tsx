import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import ErrorChart, { type ChartMarker, type ChartSeries } from "../components/charts/ErrorChart";
import { Badge, Button, Icon, Label, Panel, Pending, cx, type Tone } from "../components/ui";
import type { IncidentData } from "../hooks/useBackend";
import {
  OUTCOME_LABEL,
  baselineOf,
  breachWindow,
  describeAction,
  eventClass,
  interventionRows,
  metricByName,
  niceCeil,
  outcomeOf,
  simulationFor,
  sloOf,
  sortedTimeline,
  type Outcome,
} from "../lib/derive";
import { downloadText, toCsv } from "../lib/download";
import { effort, minuteLabel, pct } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { Investigation, SimulationResult } from "../types";

const OUTCOME_TONE: Record<Outcome, Tone> = { prevented: "secondary", partial: "tertiary", no_effect: "error" };
const OUTCOME_COLOR: Record<Outcome, string> = { prevented: "#4edea3", partial: "#ffb95f", no_effect: "#ffb4ab" };
const RISK_TONE: Record<string, Tone> = { low: "secondary", med: "tertiary", high: "error" };
const PLAY_MS = 7000;

export default function Lab({ inv, data, nav }: { inv: Investigation; data: IncidentData; nav: Nav }) {
  const baseline = baselineOf(inv.simulations);
  const rows = useMemo(() => interventionRows(inv), [inv]);
  const slo = sloOf(data.model);

  const defaultId = inv.recommendation?.intervention_id ?? inv.ranking[0]?.intervention_id ?? rows[0]?.intervention.id;
  const known = new Set(inv.interventions.map((i) => i.id));
  const picked = nav.focus.interventionIds.filter((id) => known.has(id));
  const selectedIds = picked.length ? picked : defaultId ? [defaultId] : [];
  const key = [...selectedIds].sort().join("+");

  // Combinations the agent did not simulate come from POST /api/simulate.
  const [custom, setCustom] = useState<Record<string, SimulationResult>>({});
  const [simError, setSimError] = useState<string | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const fromAgent = simulationFor(inv.simulations, selectedIds);
  const simulation = fromAgent ?? custom[key];

  useEffect(() => {
    if (!key || fromAgent || custom[key] || selectedIds.length < 2) return;
    let cancelled = false;
    setSimLoading(true);
    setSimError(null);
    api
      .simulate(inv.incident.id, selectedIds)
      .then((result) => !cancelled && setCustom((c) => ({ ...c, [key]: result })))
      .catch((e: Error) => !cancelled && setSimError(e.message))
      .finally(() => !cancelled && setSimLoading(false));
    return () => {
      cancelled = true;
    };
    // selectedIds is derived from `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, fromAgent, inv.incident.id]);

  // Replay playhead: animates left to right across the window.
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const frame = useRef(0);
  const minutes = inv.incident.window.minutes;
  useEffect(() => {
    if (!playing) return;
    const start = performance.now() - ((playhead ?? 0) / (minutes - 1)) * PLAY_MS;
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / PLAY_MS);
      setPlayhead(progress * (minutes - 1));
      if (progress < 1) frame.current = requestAnimationFrame(step);
      else setPlaying(false);
    };
    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
    // the loop restarts only when playback toggles
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, minutes]);
  useEffect(() => {
    setPlayhead(null);
    setPlaying(false);
  }, [key]);

  const observed = metricByName(data.metrics, "checkout_5xx_rate");
  const baseErr = baseline?.series.error_rate ?? [];
  const cfErr = simulation?.series.error_rate ?? [];
  const outcome = outcomeOf(simulation, baseline);
  const color = OUTCOME_COLOR[outcome];
  const breach = useMemo(() => breachWindow(baseErr, slo), [baseErr, slo]);
  const yMax = niceCeil(Math.max(slo * 1.2, ...baseErr, ...cfErr), 0.1);

  const markers: ChartMarker[] = useMemo(
    () => sortedTimeline(inv.timeline).filter((e) => e.state_change).map((e) => ({ id: e.id, t: e.t, label: e.summary, cls: eventClass(e) })),
    [inv.timeline],
  );

  const label = selectedIds.length ? selectedIds.join(" + ") : "—";
  const series: ChartSeries[] = [
    ...(observed ? [{ id: "obs", label: "Observed telemetry", values: observed.points.map((p) => p.value), color: "#869397", dashed: true, width: 1.2, opacity: 0.6 }] : []),
    { id: "base", label: "Actual (no fix)", values: baseErr, color: "#ffb4ab", area: true, width: 2.4 },
    ...(cfErr.length ? [{ id: "cf", label: `Counterfactual ${label}`, values: cfErr, color, dashed: outcome !== "no_effect", width: 2.6, area: outcome !== "no_effect" }] : []),
  ];

  if (rows.length === 0 || !baseline) {
    return <Pending title="Running counterfactuals" hint="The simulator replays the incident window once per candidate fix, with exactly one variable changed." rows={4} />;
  }

  const singles = rows.filter((r) => r.simulation);
  const prevented = singles.filter((r) => r.simulation?.prevented);
  const noEffect = singles.filter((r) => outcomeOf(r.simulation, baseline) === "no_effect");
  const selectedRows = rows.filter((r) => selectedIds.includes(r.intervention.id));

  const toggle = (id: string) => {
    const next = selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];
    nav.setFocus({ interventionIds: next.length ? next : [id] });
  };

  const at = playhead === null ? null : Math.round(playhead);
  const exportCsv = () =>
    downloadText(
      `${inv.incident.id}-counterfactuals.csv`,
      toCsv(
        ["intervention", "title", "category", "risk", "effort_hours", "peak_error_rate", "breach_minutes", "prevented", "rank", "score"],
        [
          ["baseline", "No intervention", "", "", "", baseline.peak_error_rate, baseline.breach_minutes, baseline.prevented, "", ""],
          ...rows.map((r) => [r.intervention.id, r.intervention.title, r.intervention.category, r.intervention.risk, r.intervention.effort_hours, r.simulation?.peak_error_rate ?? "", r.simulation?.breach_minutes ?? "", r.simulation?.prevented ?? "", r.ranked?.rank ?? "", r.ranked?.score ?? ""]),
        ],
      ),
      "text/csv",
    );

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <div className="glass relative flex flex-col justify-between gap-space-xl overflow-hidden p-space-xl shadow-[0_8px_32px_rgba(0,0,0,0.4)] lg:flex-row lg:items-center">
        <div className="pointer-events-none absolute -left-10 top-0 h-60 w-60 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative z-10 flex flex-col gap-space-md">
          <div className="flex flex-wrap items-center gap-space-lg">
            <Badge tone="primary" className="font-bold shadow-[0_0_10px_rgba(76,215,246,0.3)]">Deterministic simulator</Badge>
            <span className="font-mono-data-compact text-outline">
              Seed {baseline.seed} · replay {minuteLabel(inv.incident.window.start, 0)}–{minuteLabel(inv.incident.window.start, minutes - 1)} UTC
            </span>
          </div>
          <h2 className="font-headline-xl text-on-surface">Counterfactual Sandbox</h2>
          <p className="max-w-2xl font-body-md text-on-surface-variant">
            Replay the incident with exactly one change. See whether history changes, or whether the outage stays invariant.
          </p>
        </div>
        <div className="inset-well relative z-10 flex max-w-md items-center gap-space-lg p-space-lg">
          <Icon name="insights" className="text-[24px] text-primary drop-shadow-[0_0_8px_rgba(76,215,246,0.5)]" />
          <p className="font-body-sm leading-tight text-on-surface-variant">
            <strong className="font-medium text-primary">{prevented.length} of {rows.length} candidate fixes</strong> would have prevented the {baseline.breach_minutes}-minute outage.
            {noEffect.length > 0 && <> {noEffect.map((r) => r.intervention.title).join("; ")} would have changed nothing.</>}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-space-md lg:grid-cols-12">
        <div className="flex flex-col gap-space-md lg:col-span-4">
          <div className="flex items-center justify-between">
            <Label>Select intervention candidate</Label>
            <span className="font-mono-data-compact text-outline">tick boxes to combine</span>
          </div>
          {rows.map(({ intervention, ranked, simulation: sim }, i) => {
            const active = selectedIds.includes(intervention.id);
            const o = outcomeOf(sim, baseline);
            return (
              <div key={intervention.id} className="animate-fade-up relative" style={{ animationDelay: `${i * 60}ms` }}>
                <button
                  type="button"
                  onClick={() => nav.setFocus({ interventionIds: [intervention.id] })}
                  aria-pressed={active}
                  className={cx(
                    "flex w-full flex-col gap-space-md rounded border-2 bg-[#0c0e12]/80 p-space-lg pr-10 text-left backdrop-blur-md transition-all",
                    active ? "border-primary shadow-[0_0_20px_rgba(76,215,246,0.25)]" : "border-white/10 hover:border-white/25",
                    !sim && "opacity-70",
                  )}
                >
                  <div className="flex items-center justify-between gap-space-md">
                    <span className={cx("font-mono-data font-bold", active ? "text-primary" : "text-on-surface")}>{intervention.id}: {intervention.title}</span>
                  </div>
                  <div className="flex items-center gap-space-md">
                    {sim ? <Badge tone={OUTCOME_TONE[o]} className="font-bold">{OUTCOME_LABEL[o]}</Badge> : <Badge tone="muted">Simulating…</Badge>}
                    {ranked && <Badge tone="muted">#{ranked.rank}</Badge>}
                    <Badge tone={RISK_TONE[intervention.risk] ?? "muted"}>risk {intervention.risk}</Badge>
                  </div>
                  <p className="font-body-sm text-on-surface-variant">{intervention.rationale}</p>
                  <div className="flex items-center gap-space-md font-mono-data-compact text-outline">
                    <span>Peak: <strong className={sim ? (o === "prevented" ? "text-secondary" : o === "partial" ? "text-tertiary" : "text-error") : ""}>{sim ? pct(sim.peak_error_rate) : "—"}</strong></span>
                    <span>•</span>
                    <span>Breach: <strong className={sim ? (o === "prevented" ? "text-secondary" : o === "partial" ? "text-tertiary" : "text-error") : ""}>{sim ? `${sim.breach_minutes} min` : "—"}</strong></span>
                    <span>•</span>
                    <span className="font-semibold text-primary">Effort: {effort(intervention.effort_hours)}</span>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => toggle(intervention.id)}
                  aria-pressed={active}
                  aria-label={`${active ? "Remove" : "Add"} ${intervention.id} ${active ? "from" : "to"} the combination`}
                  className="absolute right-2 top-2 rounded p-1 text-outline transition-colors hover:text-primary"
                  title="Combine with other interventions"
                >
                  <Icon name={active ? "check_box" : "check_box_outline_blank"} className={cx("text-[20px]", active && "text-primary")} />
                </button>
              </div>
            );
          })}
        </div>

        <Panel className="flex flex-col justify-between gap-space-lg lg:col-span-8">
          <div className="flex flex-wrap items-center justify-between gap-space-md border-b border-white/10 pb-space-md">
            <span className="font-mono-metric-lg !text-[14px] uppercase text-primary drop-shadow-[0_0_8px_rgba(76,215,246,0.4)]">
              {selectedIds.length > 1 ? `Combination ${label}` : `Intervention ${label}`}: {selectedRows.map((r) => r.intervention.title).join(" + ")}
            </span>
            <div className="flex items-center gap-space-lg font-mono-data-compact">
              <span className="flex items-center gap-1.5 text-on-surface"><span className="h-0.5 w-3 bg-error shadow-[0_0_6px_#ffb4ab]" />Actual reality</span>
              <span className="flex items-center gap-1.5 font-semibold" style={{ color }}><span className="h-0.5 w-3 border-t-2 border-dashed" style={{ borderColor: color }} />Counterfactual</span>
            </div>
          </div>

          <div className="inset-well p-space-md">
            {simLoading && !simulation ? (
              <div className="skeleton h-[300px]" />
            ) : (
              <ErrorChart
                ariaLabel={`Error rate: actual versus counterfactual ${label}`}
                series={series}
                slo={slo}
                minutes={minutes}
                windowStart={inv.incident.window.start}
                breach={breach}
                markers={markers}
                yMax={yMax}
                height={300}
                playhead={at}
                selectedMarker={nav.focus.eventId}
                onMarkerClick={(id) => nav.go("timeline", { eventId: id })}
              />
            )}
          </div>

          <div className="flex flex-wrap items-center gap-space-xl rounded border border-white/10 bg-[#08090c]/60 px-space-lg py-space-md">
            <Button icon={playing ? "pause" : "play_arrow"} variant={playing ? "secondary" : "primary"} onClick={() => (playing ? setPlaying(false) : (playhead === null || playhead >= minutes - 1) ? (setPlayhead(0), setPlaying(true)) : setPlaying(true))} disabled={!simulation} className="!py-1">
              {playing ? "Pause" : playhead === null ? "Replay history" : "Resume"}
            </Button>
            <label className="flex min-w-[160px] flex-1 items-center gap-space-lg font-mono-data-compact text-outline">
              <span className="sr-only">Scrub through the incident window</span>
              <input
                type="range"
                min={0}
                max={minutes - 1}
                step={1}
                value={at ?? 0}
                onChange={(e) => { setPlaying(false); setPlayhead(Number(e.target.value)); }}
                className="h-1 flex-1 cursor-pointer accent-[#4cd7f6]"
                disabled={!simulation}
              />
            </label>
            {at !== null && simulation ? (
              <div className="flex items-center gap-space-xl font-mono-data-compact tabular-nums" aria-live="off">
                <span className="text-outline">{minuteLabel(inv.incident.window.start, at)} UTC</span>
                <span className="text-error">actual {pct(baseErr[at] ?? 0)}</span>
                <span style={{ color }}>cf {pct(cfErr[at] ?? 0)}</span>
                {(baseErr[at] ?? 0) > slo && (cfErr[at] ?? 0) <= slo && <Badge tone="secondary">breach avoided</Badge>}
                {(baseErr[at] ?? 0) > slo && (cfErr[at] ?? 0) > slo && <Badge tone="error">still breaching</Badge>}
              </div>
            ) : (
              <span className="font-mono-data-compact text-outline">Press replay to watch history unfold against the counterfactual.</span>
            )}
          </div>

          {simError && <p role="alert" className="font-body-sm text-error">Could not simulate {label}: {simError}</p>}

          <div className="grid grid-cols-1 gap-space-md rounded border border-white/10 bg-[#08090c]/90 p-space-lg shadow-inner sm:grid-cols-3">
            <Metric label="Simulated peak error" now={simulation ? pct(simulation.peak_error_rate) : "—"} was={pct(baseline.peak_error_rate)} sub={simulation ? `${simulation.peak_error_rate <= baseline.peak_error_rate ? "−" : "+"}${pct(Math.abs(baseline.peak_error_rate - simulation.peak_error_rate))} vs actual` : "…"} tone={simulation ? OUTCOME_TONE[outcome] : "muted"} />
            <Metric label="Breach minutes" now={simulation ? `${simulation.breach_minutes} min` : "—"} was={`${baseline.breach_minutes} min`} sub={simulation ? (simulation.breach_minutes === 0 ? "Outage eradicated" : simulation.breach_minutes < baseline.breach_minutes ? `${baseline.breach_minutes - simulation.breach_minutes} min avoided` : "Identical outage duration") : "…"} tone={simulation ? OUTCOME_TONE[outcome] : "muted"} />
            <div className="flex flex-col">
              <Label>Outcome</Label>
              <div className="mt-1">
                {simulation ? <Badge tone={OUTCOME_TONE[outcome]} className="font-bold">{simulation.prevented ? "Outage prevented" : outcome === "partial" ? "Not prevented (improved)" : "No effect"}</Badge> : <Badge tone="muted">Simulating…</Badge>}
              </div>
              <span className="mt-1 font-mono-data-compact text-on-surface-variant">
                {simulation ? (simulation.prevented ? "Stays under the SLO for the whole window." : outcome === "partial" ? "Shortens the breach but the SLO is still crossed." : "The breach plays out exactly as it did.") : ""}
              </span>
            </div>
          </div>

          {simulation && baseline && (
            <div className="grid grid-cols-1 gap-space-md md:grid-cols-2">
              <MiniSeries title="Pool wait (ms)" baseline={baseline.series.pool_wait_ms} cf={simulation.series.pool_wait_ms} color={color} minutes={minutes} windowStart={inv.incident.window.start} at={at} format={(v) => `${Math.round(v)}ms`} />
              <MiniSeries title="In-flight requests" baseline={baseline.series.inflight} cf={simulation.series.inflight} color={color} minutes={minutes} windowStart={inv.incident.window.start} at={at} format={(v) => v.toFixed(0)} />
            </div>
          )}

          <div className="flex flex-col gap-space-md border-t border-white/10 pt-space-lg">
            <Label>What the {selectedRows.length > 1 ? "combination changes" : "intervention changes"}</Label>
            <ul className="flex flex-col gap-space-md">
              {selectedRows.map((r) => (
                <li key={r.intervention.id} className="flex flex-wrap items-center gap-space-lg font-mono-data-compact">
                  <code className="font-semibold text-primary">{r.intervention.id}</code>
                  <code className="rounded bg-white/5 px-1.5 py-0.5 text-on-surface">{describeAction(r.intervention.action)}</code>
                  <Badge tone="muted">{r.intervention.category}</Badge>
                  <span className="text-outline">effort {effort(r.intervention.effort_hours)}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      </div>

      <div className="glass flex flex-col items-center justify-between gap-space-xl p-space-lg sm:flex-row">
        <div className="flex items-center gap-space-xl font-mono-data-compact text-outline">
          <span className="flex items-center gap-2"><Icon name="verified" className="text-[18px]" />Deterministic seed <span className="font-medium text-on-surface">{baseline.seed}</span></span>
          <span className="hidden md:inline">·</span>
          <span className="hidden md:inline">{inv.simulations.length} simulations run</span>
        </div>
        <div className="flex w-full flex-wrap items-center justify-end gap-space-md sm:w-auto">
          <Button icon="file_download" onClick={exportCsv}>Export comparison</Button>
          {inv.recommendation && (
            <Button variant="primary" icon="arrow_forward" className="flex-row-reverse" onClick={() => nav.go("gate")}>
              {inv.stage === "awaiting_approval" ? `Review recommended intervention (${inv.recommendation.intervention_id})` : "Open approval gate"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, now, was, sub, tone }: { label: string; now: string; was: string; sub: string; tone: Tone }) {
  const text: Record<Tone, string> = { primary: "text-primary", secondary: "text-secondary", tertiary: "text-tertiary", error: "text-error", muted: "text-on-surface" };
  return (
    <div className="flex flex-col">
      <Label>{label}</Label>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span className={cx("font-mono-metric-lg !text-[18px] font-bold tabular-nums transition-colors", text[tone])}>{now}</span>
        <span className="font-mono-data-compact text-outline line-through">{was}</span>
      </div>
      <span className={cx("font-mono-data-compact", text[tone])}>{sub}</span>
    </div>
  );
}

function MiniSeries({ title, baseline, cf, color, minutes, windowStart, at, format }: { title: string; baseline: readonly number[]; cf: readonly number[]; color: string; minutes: number; windowStart: string; at: number | null; format: (v: number) => string }) {
  return (
    <div className="inset-well p-space-lg">
      <div className="mb-1 flex items-center justify-between">
        <Label>{title}</Label>
        {at !== null && (
          <span className="font-mono-data-compact tabular-nums">
            <span className="text-error">{format(baseline[at] ?? 0)}</span> <span className="text-outline">→</span> <span style={{ color }}>{format(cf[at] ?? 0)}</span>
          </span>
        )}
      </div>
      <ErrorChart
        ariaLabel={`${title}: actual versus counterfactual`}
        unit="number"
        format={format}
        series={[
          { id: "base", label: "Actual", values: baseline, color: "#ffb4ab", width: 1.8 },
          { id: "cf", label: "Counterfactual", values: cf, color, dashed: true, width: 1.8 },
        ]}
        minutes={minutes}
        windowStart={windowStart}
        height={150}
        playhead={at}
      />
    </div>
  );
}
