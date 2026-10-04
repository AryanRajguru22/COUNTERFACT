import { useMemo, useState } from "react";
import TimelineStrip, { type Stream } from "../components/charts/TimelineStrip";
import { Badge, Button, Icon, Label, Panel, Pending, ViewHeader, cx, type Tone } from "../components/ui";
import type { IncidentData } from "../hooks/useBackend";
import {
  EVENT_CLASS_LABEL,
  baselineOf,
  breachWindow,
  eventClass,
  evidenceForEvent,
  metricByName,
  sloOf,
  sortedTimeline,
  type EventClass,
} from "../lib/derive";
import { downloadText, toCsv } from "../lib/download";
import { clock, clockSeconds, humanize, minuteLabel, pct } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { Event, Investigation } from "../types";

type Filter = "all" | EventClass;

const CLASS_TONE: Record<EventClass, Tone> = { cause: "tertiary", symptom: "error", decoy: "muted", recovery: "secondary" };
const KIND_ICON: Record<string, string> = {
  deploy: "deployed_code",
  config_change: "tune",
  job_start: "play_circle",
  job_end: "stop_circle",
  metric: "monitoring",
  log: "article",
  alert: "crisis_alert",
  trace: "route",
  external: "public",
};

function shortLabel(event: Event): string {
  if (event.state_change) return `${event.id} ${event.state_change.param} ${event.state_change.from} → ${event.state_change.to}`;
  const text = event.summary.replace(/^(Alert|Batch job|Deploy|Rollback)\b:?\s*/i, "$1 ");
  return `${event.id} ${text.length > 20 ? `${text.slice(0, 19)}…` : text}`;
}

function attributeText(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Timeline({ inv, data, nav }: { inv: Investigation; data: IncidentData; nav: Nav }) {
  const [filter, setFilter] = useState<Filter>("all");
  const events = useMemo(() => sortedTimeline(inv.timeline), [inv.timeline]);
  const items = useMemo(() => events.map((event) => ({ event, cls: eventClass(event), label: shortLabel(event) })), [events]);
  const slo = sloOf(data.model);
  const baseline = baselineOf(inv.simulations);
  const observed = metricByName(data.metrics, "checkout_5xx_rate");
  const errorValues = observed?.points.map((p) => p.value) ?? baseline?.series.error_rate ?? [];
  const breach = useMemo(() => breachWindow(errorValues, slo), [errorValues, slo]);

  const active = metricByName(data.metrics, "pool_active_connections");
  const poolMax = metricByName(data.metrics, "pool_max_connections");
  const waitP99 = metricByName(data.metrics, "pool_wait_p99_ms");
  const streams: Stream[] = useMemo(() => {
    const out: Stream[] = [];
    if (errorValues.length) {
      out.push({ id: "5xx", label: "checkout 5xx rate", values: errorValues, color: "#ffb4ab", max: Math.max(0.05, ...errorValues), format: (v) => pct(v, 1) });
    }
    if (active && poolMax) {
      const saturation = active.points.map((p, i) => (poolMax.points[i]?.value ? p.value / poolMax.points[i].value : 0));
      out.push({ id: "pool", label: "pool saturation (active / max)", values: saturation, color: "#ffb95f", max: 1, format: (v) => pct(v, 0) });
    }
    if (waitP99) {
      out.push({ id: "wait", label: "pool wait p99", values: waitP99.points.map((p) => p.value), color: "#4cd7f6", max: Math.max(1, ...waitP99.points.map((p) => p.value)), format: (v) => `${Math.round(v)} ms` });
    }
    return out;
  }, [errorValues, active, poolMax, waitP99]);

  if (events.length === 0) {
    return <Pending title="Reconstructing the timeline" hint="The agent is pulling deploys, config changes, jobs, alerts and logs into one ordered sequence." rows={4} />;
  }

  const counts: Record<Filter, number> = {
    all: events.length,
    cause: items.filter((i) => i.cls === "cause").length,
    symptom: items.filter((i) => i.cls === "symptom").length,
    decoy: items.filter((i) => i.cls === "decoy").length,
    recovery: items.filter((i) => i.cls === "recovery").length,
  };
  const pills = (["all", "cause", "symptom", "decoy", "recovery"] as const).filter((f) => f === "all" || counts[f] > 0);
  const visible = items.filter((i) => filter === "all" || i.cls === filter);

  const selected = events.find((e) => e.id === nav.focus.eventId) ?? events[0];
  const selectedCls = eventClass(selected);
  const chainIndex = inv.root_cause?.causal_chain.findIndex((l) => l.event_id === selected.id) ?? -1;
  const chainLink = chainIndex >= 0 ? inv.root_cause?.causal_chain[chainIndex] : undefined;
  const related = evidenceForEvent(inv.evidence, selected.id);
  const attrs = Object.entries(selected.attributes).filter(([k]) => k !== "causal" && k !== "decoy");

  const exportCsv = () =>
    downloadText(
      `${inv.incident.id}-timeline.csv`,
      toCsv(["id", "time_utc", "minute", "kind", "source", "classification", "summary", "state_change"], events.map((e) => [e.id, e.ts, e.t, e.kind, e.source, eventClass(e), e.summary, e.state_change ? `${e.state_change.param}: ${e.state_change.from} -> ${e.state_change.to}` : ""])),
      "text/csv",
    );

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <ViewHeader
        title="Reconstructed Causal Timeline"
        subtitle={`${events.length} events across ${clock(inv.incident.window.start)}–${minuteLabel(inv.incident.window.start, inv.incident.window.minutes)} UTC, classified as causal triggers, symptoms and decoys.`}
      >
        <Button icon="file_download" onClick={exportCsv}>Export CSV</Button>
      </ViewHeader>

      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <div className="flex flex-wrap items-center gap-space-md" role="group" aria-label="Filter events">
          {pills.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={cx(
                "flex items-center gap-space-md rounded border px-space-xl py-1 font-mono-data transition-all",
                filter === f ? "border-primary/50 bg-primary/15 font-semibold text-primary" : "border-white/10 bg-[#0c0e12]/75 text-on-surface-variant hover:text-on-surface",
              )}
            >
              {f !== "all" && <span className={cx("h-1.5 w-1.5 rounded-full", f === "cause" ? "bg-tertiary" : f === "symptom" ? "bg-error" : f === "decoy" ? "bg-outline" : "bg-secondary")} />}
              {f === "all" ? "All events" : f === "cause" ? "Causal triggers" : f === "symptom" ? "Symptoms" : f === "decoy" ? "Decoys" : "Recovery"}
              <span className="rounded bg-white/10 px-1 font-mono-label-caps tabular-nums">{counts[f]}</span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-space-xl font-mono-data-compact text-outline">
          <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-error-container/50" />SLO breach zone{breach ? ` (${breach.minutes} min)` : ""}</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rotate-45 bg-tertiary" />state change</span>
        </div>
      </div>

      <Panel className="!p-space-xl">
        <div className="mb-space-md flex items-center justify-between font-mono-label-caps uppercase tracking-wider text-outline">
          <span className="flex items-center gap-space-md"><Icon name="insights" className="text-[16px] text-primary" />Continuous forensic trajectory · {inv.incident.service}</span>
          <span className="font-mono-data-compact normal-case">1 minute / tick</span>
        </div>
        <TimelineStrip
          events={items.filter((i) => filter === "all" || i.cls === filter)}
          minutes={inv.incident.window.minutes}
          windowStart={inv.incident.window.start}
          breach={breach}
          streams={streams}
          selected={selected.id}
          onSelect={(id) => nav.setFocus({ eventId: id })}
        />
      </Panel>

      <div className="grid grid-cols-1 items-start gap-space-lg lg:grid-cols-12">
        <div className="flex flex-col gap-space-md lg:col-span-7">
          <div className="flex items-center justify-between px-2 font-mono-label-caps uppercase tracking-wider text-outline">
            <span>Causal chronology</span>
            <span>Showing {visible.length} of {events.length}</span>
          </div>
          <ul className="flex flex-col gap-space-md" aria-label="Events">
            {visible.map(({ event, cls }) => {
              const isSelected = event.id === selected.id;
              return (
                <li key={event.id}>
                  <button
                    type="button"
                    onClick={() => nav.setFocus({ eventId: event.id })}
                    aria-pressed={isSelected}
                    className={cx(
                      "flex w-full items-center justify-between gap-space-xl rounded border p-space-lg text-left transition-all",
                      isSelected ? "border-white/20 bg-surface-container-high" : "border-white/5 bg-[#0c0e12]/75 hover:bg-surface-container",
                      cls === "decoy" && !isSelected && "opacity-75",
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-space-xl">
                      <div className="flex flex-col items-center">
                        <span className={cx("font-mono-data font-medium tabular-nums", cls === "cause" ? "text-tertiary" : cls === "symptom" ? "text-error" : cls === "recovery" ? "text-secondary" : "text-outline")}>{clockSeconds(event.ts)}</span>
                        <span className="font-mono-data-compact text-[10px] text-outline">UTC</span>
                      </div>
                      <div className="h-8 w-px bg-surface-variant" />
                      <div className="flex min-w-0 flex-col">
                        <div className="flex items-center gap-space-md">
                          <span className={cx("shrink-0 whitespace-nowrap font-mono-data font-semibold", cls === "cause" ? "text-tertiary" : cls === "symptom" ? "text-error" : cls === "recovery" ? "text-secondary" : "text-outline")}>{event.id}</span>
                          <span className="truncate font-body-md text-on-surface">{event.summary}</span>
                        </div>
                        <span className="truncate font-mono-data-compact text-outline">
                          {event.source} · {humanize(event.kind)}
                          {event.state_change && ` · ${event.state_change.param}: ${event.state_change.from} → ${event.state_change.to}`}
                        </span>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-space-md">
                      <Badge tone={CLASS_TONE[cls]}>{EVENT_CLASS_LABEL[cls]}</Badge>
                      <Icon name="chevron_right" className={cx("text-[18px]", isSelected ? "text-primary" : "text-outline")} />
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <aside className="flex flex-col gap-space-md lg:sticky lg:top-20 lg:col-span-5" aria-label="Event dossier">
          <div className="flex items-center justify-between px-2 font-mono-label-caps uppercase tracking-wider text-outline">
            <span>Forensic dossier</span>
            <span className="font-medium text-primary">Inspecting {selected.id}</span>
          </div>
          <div key={selected.id} className="glass animate-fade-up flex flex-col gap-space-xl p-space-xl shadow-xl">
            <div className="flex items-start justify-between gap-space-md">
              <div>
                <div className="mb-1 flex items-center gap-space-md">
                  <Badge tone={CLASS_TONE[selectedCls]}>{EVENT_CLASS_LABEL[selectedCls]}</Badge>
                  <span className="font-mono-data text-outline">{clockSeconds(selected.ts)} UTC · minute {selected.t}</span>
                </div>
                <h3 className="font-headline-sm text-on-surface">{selected.summary}</h3>
              </div>
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-surface-container text-primary">
                <Icon name={KIND_ICON[selected.kind] ?? "event"} className="text-[20px]" />
              </div>
            </div>

            <dl className="flex flex-col gap-space-md rounded bg-surface-container-low p-space-lg font-mono-data">
              <div className="flex items-center justify-between"><dt className="text-outline">Source</dt><dd className="text-on-surface">{selected.source}</dd></div>
              <div className="flex items-center justify-between"><dt className="text-outline">Kind</dt><dd className="text-on-surface">{humanize(selected.kind)}</dd></div>
              {attrs.map(([key, value]) => (
                <div key={key} className="flex items-start justify-between gap-space-xl border-t border-white/5 pt-space-md">
                  <dt className="shrink-0 text-outline">{humanize(key)}</dt>
                  <dd className="min-w-0 break-words text-right text-on-surface">{attributeText(value)}</dd>
                </div>
              ))}
            </dl>

            {selected.state_change && (
              <div className="flex flex-col gap-space-md">
                <Label>State change</Label>
                <div className="flex items-center justify-between rounded bg-surface-container-low p-space-lg">
                  <div className="flex flex-col">
                    <span className="font-mono-data text-outline">{selected.state_change.param}</span>
                    <span className="font-headline-sm font-semibold text-tertiary tabular-nums">
                      {String(selected.state_change.to)} <span className="text-xs font-normal text-outline">was {String(selected.state_change.from)}</span>
                    </span>
                  </div>
                  {typeof selected.state_change.from === "number" && typeof selected.state_change.to === "number" && (
                    <div className="flex h-8 w-28 items-end gap-1" aria-hidden="true">
                      <span className="w-6 rounded-sm bg-surface-variant" style={{ height: "100%" }} />
                      <span className="w-6 rounded-sm bg-tertiary transition-[height] duration-700" style={{ height: `${Math.max(8, (selected.state_change.to / Math.max(selected.state_change.from, selected.state_change.to, 1)) * 100)}%` }} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {(chainLink || selectedCls === "decoy") && (
              <div className="flex flex-col gap-space-md">
                <Label>{chainLink ? `Role in the root cause (step ${chainIndex + 1} of ${inv.root_cause?.causal_chain.length})` : "Why it is a decoy"}</Label>
                <div className="rounded bg-surface-container p-space-lg font-body-sm leading-relaxed text-on-surface">
                  {chainLink
                    ? chainLink.effect
                    : related.find((e) => Object.values(e.stance).includes("refutes"))?.description ?? "The evidence engine found no causal link between this event and the breach."}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-space-md">
              <Label>Evidence from this event ({related.length})</Label>
              {related.length === 0 ? (
                <p className="font-body-sm text-outline">No evidence item cites this event.</p>
              ) : (
                <ul className="flex flex-col gap-space-md">
                  {related.map((ev) => (
                    <li key={ev.id} className="rounded bg-surface-container-low p-space-md font-body-sm text-on-surface-variant">
                      <div className="mb-0.5 flex flex-wrap items-center gap-space-md">
                        <code className="font-semibold text-primary">{ev.id}</code>
                        {Object.entries(ev.stance).map(([h, s]) => (
                          <Badge key={h} tone={s === "supports" ? "secondary" : s === "refutes" ? "error" : "muted"}>{s} {h}</Badge>
                        ))}
                      </div>
                      {ev.description}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {related.length > 0 && (
              <Button variant="primary" icon="arrow_forward" className="flex-row-reverse" onClick={() => nav.go("evidence", { eventId: selected.id })}>
                View correlated evidence ({related.map((e) => e.id).join(", ")})
              </Button>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
