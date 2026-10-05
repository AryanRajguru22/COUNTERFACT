import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Icon, Pending, ViewHeader, cx, type Tone } from "../components/ui";
import { downloadText, toCsv } from "../lib/download";
import { humanize } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { EvidenceKind, Investigation, Stance } from "../types";

const KIND_TONE: Record<EvidenceKind, Tone> = { metric: "primary", trace: "secondary", log: "error", config_diff: "tertiary", deploy_record: "muted", external: "muted" };
const STANCE_TONE: Record<Stance, Tone> = { supports: "secondary", refutes: "error", neutral: "muted" };

type Sort = "id" | "weight";

export default function Evidence({ inv, nav }: { inv: Investigation; nav: Nav }) {
  const [kind, setKind] = useState<EvidenceKind | "all">("all");
  const [sort, setSort] = useState<Sort>("id");
  const hypothesisFilter = nav.focus.hypothesisId;
  const eventFilter = nav.focus.eventId;

  // Arriving from a hypothesis chip scrolls to that row once, then releases the highlight.
  const targetEvidence = nav.focus.evidenceId;
  useEffect(() => {
    if (!targetEvidence) return;
    document.getElementById(`ev-${targetEvidence}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    const timer = setTimeout(() => nav.setFocus({ evidenceId: null }), 2500);
    return () => clearTimeout(timer);
    // nav.setFocus is stable; only a new target should restart this
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetEvidence]);

  const kinds = useMemo(() => [...new Set(inv.evidence.map((e) => e.kind))], [inv.evidence]);
  const rows = useMemo(() => {
    const filtered = inv.evidence.filter(
      (e) => (kind === "all" || e.kind === kind) && (!hypothesisFilter || hypothesisFilter in e.stance) && (!eventFilter || e.source_event_ids.includes(eventFilter)),
    );
    return filtered.sort((a, b) => (sort === "weight" ? b.weight - a.weight : a.id.localeCompare(b.id)));
  }, [inv.evidence, kind, sort, hypothesisFilter, eventFilter]);

  if (inv.evidence.length === 0) {
    return <Pending title="Gathering evidence" hint="Metrics, traces, logs, deploy records and config diffs are being matched to each hypothesis." rows={5} />;
  }

  const tally = inv.hypotheses.map((h) => ({
    id: h.id,
    supports: inv.evidence.filter((e) => e.stance[h.id] === "supports").length,
    refutes: inv.evidence.filter((e) => e.stance[h.id] === "refutes").length,
  }));
  const filtered = Boolean(hypothesisFilter || eventFilter || kind !== "all");

  const exportCsv = () =>
    downloadText(
      `${inv.incident.id}-evidence.csv`,
      toCsv(["id", "kind", "weight", "stances", "source_events", "description"], inv.evidence.map((e) => [e.id, e.kind, e.weight, Object.entries(e.stance).map(([h, s]) => `${h}:${s}`).join(" "), e.source_event_ids.join(" "), e.description])),
      "text/csv",
    );

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <ViewHeader title="Forensic Evidence Matrix" subtitle={`${inv.evidence.length} artifacts mapped to hypotheses. Each item can support one hypothesis and refute another.`}>
        <div className="flex flex-wrap items-center gap-space-md font-mono-data-compact">
          {tally.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={hypothesisFilter === t.id}
              onClick={() => nav.setFocus({ hypothesisId: hypothesisFilter === t.id ? null : t.id })}
              className={cx("flex items-center gap-1.5 rounded border px-space-lg py-0.5 transition-colors", hypothesisFilter === t.id ? "border-primary/60 bg-primary/15" : "border-white/10 hover:border-white/25")}
              title={`Filter to ${t.id}`}
            >
              <span className="font-semibold text-on-surface">{t.id}</span>
              <span className="text-secondary">{t.supports}↑</span>
              <span className="text-error">{t.refutes}↓</span>
            </button>
          ))}
        </div>
        <Button icon="file_download" onClick={exportCsv}>Export CSV</Button>
      </ViewHeader>

      <div className="flex flex-wrap items-center justify-between gap-space-md">
        <div className="flex flex-wrap items-center gap-space-md" role="group" aria-label="Filter by kind">
          {(["all", ...kinds] as const).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={cx("rounded border px-space-xl py-1 font-mono-data transition-colors", kind === k ? "border-primary/50 bg-primary/15 text-primary" : "border-white/10 bg-[#0c0e12]/75 text-on-surface-variant hover:text-on-surface")}
            >
              {k === "all" ? "All kinds" : humanize(k)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-space-md font-mono-data-compact text-outline">
          {eventFilter && (
            <button type="button" onClick={() => nav.setFocus({ eventId: null })} className="flex items-center gap-1 rounded bg-primary/15 px-space-lg py-0.5 text-primary hover:bg-primary/25">
              event {eventFilter} <Icon name="close" className="text-[13px]" />
            </button>
          )}
          {hypothesisFilter && (
            <button type="button" onClick={() => nav.setFocus({ hypothesisId: null })} className="flex items-center gap-1 rounded bg-primary/15 px-space-lg py-0.5 text-primary hover:bg-primary/25">
              {hypothesisFilter} <Icon name="close" className="text-[13px]" />
            </button>
          )}
          <span>Sort</span>
          {(["id", "weight"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={sort === s} onClick={() => setSort(s)} className={cx("rounded px-space-md py-0.5", sort === s ? "bg-white/10 text-on-surface" : "hover:text-on-surface")}>
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="glass overflow-hidden shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left font-mono-data">
            <thead>
              <tr className="border-b border-white/10 bg-[#12151c]/80 font-mono-label-caps uppercase text-outline">
                <th className="px-space-xl py-space-lg">ID</th>
                <th className="px-space-xl py-space-lg">Kind</th>
                <th className="px-space-xl py-space-lg">Telemetry description</th>
                <th className="px-space-xl py-space-lg">Source events</th>
                <th className="px-space-xl py-space-lg">Impact</th>
                <th className="px-space-xl py-space-lg">Weight</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map((e) => {
                const highlighted = nav.focus.evidenceId === e.id;
                return (
                  <tr
                    key={e.id}
                    id={`ev-${e.id}`}
                    className={cx("align-top transition-colors hover:bg-white/5", highlighted && "bg-primary/10")}
                  >
                    <td className="px-space-xl py-space-lg font-bold text-primary">{e.id}</td>
                    <td className="px-space-xl py-space-lg"><Badge tone={KIND_TONE[e.kind]}>{humanize(e.kind)}</Badge></td>
                    <td className="max-w-xl px-space-xl py-space-lg font-body-sm text-on-surface">{e.description}</td>
                    <td className="px-space-xl py-space-lg">
                      <div className="flex flex-wrap gap-1">
                        {e.source_event_ids.length === 0 && <span className="text-outline">—</span>}
                        {e.source_event_ids.map((id) => (
                          <button key={id} type="button" onClick={() => nav.go("timeline", { eventId: id })} className="rounded bg-white/5 px-1.5 py-0.5 font-mono-data-compact text-on-surface-variant transition-colors hover:bg-primary/20 hover:text-primary">
                            {id}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="px-space-xl py-space-lg">
                      <div className="flex flex-col gap-1">
                        {Object.entries(e.stance).map(([h, s]) => (
                          <button key={h} type="button" onClick={() => nav.go("hypotheses", { hypothesisId: h })} className="self-start">
                            <Badge tone={STANCE_TONE[s]} className="transition-opacity hover:opacity-80">{s} {h}</Badge>
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="min-w-[110px] px-space-xl py-space-lg">
                      <div className="flex items-center gap-space-md">
                        <div className="h-1.5 w-14 overflow-hidden rounded bg-white/10" aria-hidden="true">
                          <div className="h-full rounded bg-primary transition-[width] duration-700" style={{ width: `${e.weight * 100}%` }} />
                        </div>
                        <span className="tabular-nums text-on-surface">{e.weight.toFixed(2)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-space-xl py-space-xl text-center font-body-sm text-outline">
                    No evidence matches these filters.{" "}
                    {filtered && (
                      <button type="button" className="text-primary underline" onClick={() => { setKind("all"); nav.setFocus({ hypothesisId: null, eventId: null, evidenceId: null }); }}>
                        Clear filters
                      </button>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
