import { Badge, Button, Icon, Label, Meter, Panel, Pending, cx } from "../components/ui";
import { CLASS_COLOR } from "../components/charts/ErrorChart";
import { eventClass } from "../lib/derive";
import { minuteLabel, pctWhole } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { Investigation } from "../types";

export default function RootCause({ inv, nav }: { inv: Investigation; nav: Nav }) {
  const rc = inv.root_cause;
  if (!rc) {
    return <Pending title="Determining the root cause" hint="The strongest surviving hypothesis is promoted and its causal chain is built from the supporting evidence." rows={4} />;
  }
  const hypothesis = inv.hypotheses.find((h) => h.id === rc.hypothesis_id);
  const byId = new Map(inv.timeline.map((e) => [e.id, e]));

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <Panel glow="secondary" className="flex flex-col justify-between gap-space-xl md:flex-row md:items-center">
        <div className="flex items-start gap-space-xl">
          <Icon name="account_tree" className="text-[32px] text-secondary drop-shadow-[0_0_10px_rgba(78,222,163,0.5)]" />
          <div className="min-w-0">
            <span className="font-mono-label-caps font-semibold uppercase text-secondary">
              Confirmed root cause · {pctWhole(rc.confidence)} confidence · {rc.hypothesis_id}
            </span>
            <p className="font-headline-sm text-on-surface">{hypothesis?.title ?? rc.hypothesis_id}</p>
            <p className="mt-1 max-w-4xl font-body-sm text-on-surface-variant">{rc.statement}</p>
            <div className="mt-2 max-w-xs"><Meter value={rc.confidence} tone="secondary" /></div>
          </div>
        </div>
        <Button variant="primary" icon="science" onClick={() => nav.go("lab")} disabled={inv.ranking.length === 0} className="shrink-0 uppercase">
          Simulate fix in lab
        </Button>
      </Panel>

      <Panel className="flex flex-col gap-space-xl !p-space-xl">
        <div className="flex items-center justify-between">
          <Label>End-to-end causal chain</Label>
          <span className="font-mono-data-compact text-outline">{rc.causal_chain.length} links · click a node to open it in the timeline</span>
        </div>
        <ol className="relative flex flex-col gap-0">
          {rc.causal_chain.map((link, i) => {
            const event = byId.get(link.event_id);
            const cls = event ? eventClass(event) : "symptom";
            const color = CLASS_COLOR[cls];
            const lastLink = i === rc.causal_chain.length - 1;
            return (
              <li key={`${link.event_id}-${i}`} className="animate-fade-up relative flex gap-space-xl" style={{ animationDelay: `${i * 90}ms` }}>
                <div className="flex w-10 shrink-0 flex-col items-center">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 bg-[#08090c] font-mono-data-compact font-semibold" style={{ borderColor: color, color, boxShadow: `0 0 10px ${color}55` }}>
                    {i + 1}
                  </span>
                  {!lastLink && <span className="w-px flex-1 bg-gradient-to-b from-white/30 to-white/10" />}
                </div>
                <button
                  type="button"
                  onClick={() => nav.go("timeline", { eventId: link.event_id })}
                  className={cx("group mb-space-lg flex-1 rounded border border-white/10 bg-[#101318]/80 p-space-lg text-left transition-all hover:border-white/30 hover:bg-[#161a22]")}
                  style={{ borderLeft: `3px solid ${color}` }}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-space-md">
                    <code className="font-semibold" style={{ color }}>{link.event_id}</code>
                    {event && <span className="font-mono-data-compact text-outline">{minuteLabel(inv.incident.window.start, event.t)} UTC</span>}
                    {event?.state_change && <Badge tone="tertiary">{event.state_change.param}: {String(event.state_change.from)} → {String(event.state_change.to)}</Badge>}
                    <Icon name="open_in_new" className="ml-auto text-[14px] text-outline opacity-0 transition-opacity group-hover:opacity-100" />
                  </div>
                  <p className="font-body-md text-on-surface">{link.effect}</p>
                  {event && <p className="mt-0.5 font-mono-data-compact text-outline">{event.summary}</p>}
                </button>
              </li>
            );
          })}
        </ol>
      </Panel>

      {rc.contributing_factors.length > 0 && (
        <Panel className="flex flex-col gap-space-lg !p-space-xl">
          <Label>{rc.contributing_factors.length} contributing factors</Label>
          <ul className="grid grid-cols-1 gap-space-md md:grid-cols-2">
            {rc.contributing_factors.map((factor, i) => (
              <li key={i} className="animate-fade-up rounded border border-white/10 bg-[#08090c]/80 p-space-lg transition-colors hover:border-primary/40" style={{ animationDelay: `${i * 70}ms` }}>
                <span className="font-mono-data-compact font-bold text-primary">{i + 1}.</span>
                <span className="ml-1 font-body-sm text-on-surface-variant">{factor}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
