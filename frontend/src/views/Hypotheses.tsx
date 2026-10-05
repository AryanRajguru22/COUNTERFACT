import { Badge, Button, Icon, Label, Meter, Pending, ViewHeader, cx, type Tone } from "../components/ui";
import { hypothesisCounts, refutingEvidence, supportingEvidence } from "../lib/derive";
import { pctWhole } from "../lib/format";
import type { Nav } from "../lib/nav";
import type { Hypothesis, HypothesisStatus, Investigation } from "../types";

const STATUS_TONE: Record<HypothesisStatus, Tone> = { confirmed: "secondary", supported: "secondary", rejected: "error", testing: "tertiary", proposed: "muted" };

export default function Hypotheses({ inv, nav }: { inv: Investigation; nav: Nav }) {
  if (inv.hypotheses.length === 0) {
    return <Pending title="Proposing competing hypotheses" hint="Each candidate explanation predicts different evidence, which is what the agent tests next." rows={4} />;
  }
  const counts = hypothesisCounts(inv.hypotheses);
  const selected: Hypothesis =
    inv.hypotheses.find((h) => h.id === nav.focus.hypothesisId) ?? inv.hypotheses.find((h) => h.status === "confirmed") ?? inv.hypotheses[0];
  const supports = supportingEvidence(selected, inv.evidence);
  const refutes = refutingEvidence(selected, inv.evidence);
  const passed = selected.tests.filter((t) => t.passed).length;
  const sorted = [...inv.hypotheses].sort((a, b) => b.confidence - a.confidence || a.id.localeCompare(b.id));
  const testing = inv.stage === "testing" || inv.stage === "evidence";

  return (
    <div className="flex animate-fade-in flex-col gap-space-md">
      <ViewHeader
        title="Competing Hypotheses"
        subtitle={`${inv.hypotheses.length} candidate failure mechanisms weighed against the evidence${testing ? "; verdicts are still landing." : "."}`}
      >
        <div className="flex flex-wrap items-center gap-space-md rounded-lg bg-surface-container-lowest p-1.5 shadow-sm">
          <Stat dot="bg-secondary" value={counts.confirmed} label="Confirmed" />
          <Stat dot="bg-error" value={counts.rejected} label="Rejected" />
          {counts.open > 0 && <Stat dot="bg-tertiary animate-pulse" value={counts.open} label="Open" />}
          <Stat icon="cable" value={inv.evidence.length} label="Evidence" />
        </div>
      </ViewHeader>

      <div className="grid grid-cols-1 items-start gap-space-lg xl:grid-cols-12">
        <ul className="flex flex-col gap-space-md xl:col-span-7" aria-label="Hypotheses">
          {sorted.map((h, i) => {
            const isSelected = h.id === selected.id;
            const confirmed = h.status === "confirmed";
            const rejected = h.status === "rejected";
            return (
              <li key={h.id} className="animate-fade-up" style={{ animationDelay: `${i * 70}ms` }}>
                <button
                  type="button"
                  onClick={() => nav.setFocus({ hypothesisId: h.id })}
                  aria-pressed={isSelected}
                  className={cx(
                    "group relative w-full rounded-xl border p-space-xl text-left transition-all",
                    confirmed ? "border-secondary/60 shadow-[0_0_25px_rgba(78,222,163,0.18)]" : "border-white/10",
                    isSelected ? "bg-surface-container-low" : "bg-surface-container-lowest/80 hover:bg-surface-container-low",
                    rejected && !isSelected && "opacity-80",
                  )}
                >
                  <span className={cx("absolute bottom-0 left-0 top-0 w-1 rounded-l-xl transition-colors", confirmed ? "bg-secondary" : isSelected ? "bg-primary" : "bg-transparent")} />
                  <div className="flex flex-col gap-space-lg pl-2">
                    <div className="flex flex-wrap items-center justify-between gap-space-md">
                      <div className="flex min-w-0 items-center gap-space-lg">
                        <Badge tone={confirmed ? "secondary" : rejected ? "error" : "muted"} className="font-semibold">{h.id}</Badge>
                        <span className={cx("font-headline-sm", rejected ? "text-on-surface-variant" : "text-on-surface")}>{h.title}</span>
                      </div>
                      <div className="flex items-center gap-space-md">
                        {h.origin === "llm" && <Badge tone="primary" title="Proposed by the LLM, then tested like any other">LLM proposed</Badge>}
                        <Badge tone={STATUS_TONE[h.status]}>{h.status}</Badge>
                        <span className={cx("rounded bg-surface-container-lowest px-2 py-0.5 font-mono-metric-lg !text-[14px] tabular-nums", confirmed ? "text-secondary" : "text-outline")}>{pctWhole(h.confidence)}</span>
                      </div>
                    </div>
                    <Meter value={h.confidence} tone={confirmed ? "secondary" : rejected ? "error" : "primary"} />
                    <p className="font-body-sm text-on-surface-variant">
                      <span className="mr-1.5 font-mono-label-caps uppercase tracking-wider text-outline">{rejected ? "Rejection rationale:" : "Mechanism:"}</span>
                      {rejected && h.rejection_reason ? h.rejection_reason : h.mechanism}
                    </p>
                    <div className="flex flex-wrap items-center justify-between gap-space-md font-mono-label-caps text-outline">
                      <div className="flex items-center gap-space-xl normal-case">
                        <span className="flex items-center gap-1.5 text-on-surface"><Icon name="check_circle" className="text-[16px] text-secondary" />{h.supporting_evidence_ids.length} supporting</span>
                        <span className={cx("flex items-center gap-1.5", h.refuting_evidence_ids.length ? "text-error" : "text-outline")}><Icon name={h.refuting_evidence_ids.length ? "cancel" : "remove_circle_outline"} className="text-[16px]" />{h.refuting_evidence_ids.length} refuting</span>
                        <span className="text-outline">{h.tests.filter((t) => t.passed).length}/{h.tests.length} tests passed</span>
                      </div>
                      <span className="flex items-center gap-1 font-medium text-primary transition-transform group-hover:translate-x-0.5">
                        Inspect dossier <Icon name="chevron_right" className="text-[16px]" />
                      </span>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>

        <aside key={selected.id} className="glass animate-fade-up flex flex-col gap-space-xl p-space-xl xl:sticky xl:top-20 xl:col-span-5" aria-label={`Dossier for ${selected.id}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-space-md">
              <Icon name="biotech" className="text-[20px] text-secondary" />
              <span className="font-headline-sm text-on-surface">Diagnostic dossier</span>
            </div>
            <Badge tone="muted" className="!text-on-surface">{selected.id} focus</Badge>
          </div>

          <p className="font-body-sm text-on-surface-variant">{selected.mechanism}</p>

          {selected.rejection_reason && (
            <div className="rounded border border-error/30 bg-error-container/20 p-space-lg">
              <Label className="!text-error">Why it was rejected</Label>
              <p className="mt-1 font-body-sm text-on-surface">{selected.rejection_reason}</p>
            </div>
          )}

          <div className="flex flex-col gap-space-md">
            <Label>
              Hypothesis tests ({passed}/{selected.tests.length} passed)
            </Label>
            {selected.tests.length === 0 && <p className="font-body-sm text-outline">No tests have run for this hypothesis yet.</p>}
            <ul className="flex max-h-[420px] flex-col gap-space-md overflow-y-auto pr-1">
              {selected.tests.map((test, i) => (
                <li key={i} className="flex items-start gap-space-lg rounded bg-surface-container-lowest p-space-lg">
                  <Icon name={test.passed ? "verified" : "cancel"} className={cx("mt-0.5 text-[16px]", test.passed ? "text-secondary" : "text-error")} />
                  <div className="flex flex-col gap-0.5">
                    <span className="font-body-md font-medium text-on-surface">If true: {test.prediction}</span>
                    <span className="font-body-sm text-outline">{test.observed}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid grid-cols-2 gap-space-md">
            <EvidenceList title="Supporting" tone="secondary" items={supports.map((e) => e.id)} onPick={(id) => nav.go("evidence", { hypothesisId: selected.id, eventId: null, evidenceId: id })} />
            <EvidenceList title="Refuting" tone="error" items={refutes.map((e) => e.id)} onPick={(id) => nav.go("evidence", { hypothesisId: selected.id, eventId: null, evidenceId: id })} />
          </div>

          <div className="flex flex-col gap-space-md pt-1">
            {inv.root_cause && selected.id === inv.root_cause.hypothesis_id ? (
              <Button variant="primary" icon="arrow_forward" className="flex-row-reverse" onClick={() => nav.go("root-cause")}>Proceed to root cause</Button>
            ) : null}
            {inv.ranking.length > 0 && selected.status === "confirmed" && (
              <Button icon="science" onClick={() => nav.go("lab")}>Simulate in Counterfactual Lab</Button>
            )}
            <Button icon="fact_check" variant="ghost" onClick={() => nav.go("evidence", { hypothesisId: selected.id })}>
              Open all evidence for {selected.id}
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Stat({ value, label, dot, icon }: { value: number; label: string; dot?: string; icon?: string }) {
  return (
    <div className="flex items-center gap-space-md rounded bg-surface-container-low px-space-xl py-1.5">
      {icon ? <Icon name={icon} className="text-[15px] text-secondary" /> : <span className={cx("h-2 w-2 rounded-full", dot)} />}
      <div className="flex items-baseline gap-1.5">
        <span className="font-headline-sm font-semibold tabular-nums text-on-surface">{value}</span>
        <span className="font-mono-label-caps uppercase text-outline">{label}</span>
      </div>
    </div>
  );
}

function EvidenceList({ title, tone, items, onPick }: { title: string; tone: Tone; items: string[]; onPick: (id: string) => void }) {
  return (
    <div className="flex flex-col gap-space-md rounded bg-surface-container-lowest p-space-lg">
      <Label className={tone === "error" ? "!text-error" : "!text-secondary"}>{title} ({items.length})</Label>
      {items.length === 0 ? (
        <span className="font-mono-data-compact text-outline">none</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {items.map((id) => (
            <button key={id} type="button" onClick={() => onPick(id)} className="rounded bg-white/5 px-1.5 py-0.5 font-mono-data-compact text-primary transition-colors hover:bg-primary/20">
              {id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
