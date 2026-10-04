// Agent trace drawer: every thought, tool call, tool result and decision, newest first.
import { useEffect, useMemo, useState } from "react";
import { STAGE_LABEL } from "../lib/derive";
import { clockSeconds } from "../lib/format";
import type { AgentStep, AgentStepKind, Investigation } from "../types";
import { Badge, Icon, cx, type Tone } from "./ui";

const KIND: Record<AgentStepKind, { label: string; icon: string; tone: Tone }> = {
  thought: { label: "Thought", icon: "psychology", tone: "primary" },
  tool_call: { label: "Tool call", icon: "build", tone: "tertiary" },
  tool_result: { label: "Result", icon: "data_object", tone: "muted" },
  decision: { label: "Decision", icon: "gavel", tone: "secondary" },
};

const FILTERS: { id: "all" | AgentStepKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "thought", label: "Thoughts" },
  { id: "tool_call", label: "Tools" },
  { id: "decision", label: "Decisions" },
];

function StepCard({ step }: { step: AgentStep }) {
  const meta = KIND[step.kind];
  const input = step.input ? Object.entries(step.input) : [];
  return (
    <li className="animate-fade-up flex flex-col gap-1 rounded border border-white/10 bg-[#101318]/80 p-space-md">
      <div className="flex items-center justify-between text-outline">
        <span className="flex items-center gap-1.5">
          <Icon name={meta.icon} className={cx("text-[14px]", step.kind === "decision" ? "text-secondary" : step.kind === "thought" ? "text-primary" : step.kind === "tool_call" ? "text-tertiary" : "text-outline")} />
          <span className={cx("font-bold uppercase", step.kind === "decision" ? "text-secondary" : step.kind === "thought" ? "text-primary" : step.kind === "tool_call" ? "text-tertiary" : "text-on-surface-variant")}>
            Step {step.n} · {meta.label}
          </span>
        </span>
        <span className="tabular-nums">{clockSeconds(step.at)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <Badge tone="muted">{step.stage}</Badge>
        {step.tool && <code className="rounded bg-white/5 px-1 text-tertiary">{step.tool}</code>}
      </div>
      <p className="text-on-surface">{step.output_summary}</p>
      {input.length > 0 && (
        <p className="flex flex-wrap gap-x-2 text-outline">
          {input.map(([k, v]) => (
            <span key={k}>
              {k}=<span className="text-on-surface-variant">{String(v)}</span>
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

export default function AgentDrawer({ inv, open, onClose }: { inv: Investigation; open: boolean; onClose: () => void }) {
  const [filter, setFilter] = useState<"all" | AgentStepKind>("all");

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const steps = useMemo(() => {
    const filtered = filter === "all" ? inv.steps : inv.steps.filter((s) => s.kind === filter || (filter === "tool_call" && s.kind === "tool_result"));
    return [...filtered].reverse();
  }, [inv.steps, filter]);

  const running = inv.stage !== "resolved" && inv.stage !== "failed" && inv.stage !== "awaiting_approval";

  return (
    <aside
      aria-label="Agent trace"
      aria-hidden={!open}
      className={cx(
        "fixed bottom-0 right-0 top-14 z-[60] flex w-full max-w-sm flex-col justify-between border-l border-white/10 bg-[#08090c]/95 shadow-[0_0_50px_rgba(0,0,0,0.8)] backdrop-blur-2xl transition-transform duration-300 ease-in-out",
        open ? "translate-x-0" : "pointer-events-none translate-x-full",
      )}
    >
      <div className="flex items-center justify-between border-b border-white/10 p-space-lg">
        <div className="flex items-center gap-space-md">
          <Icon name="smart_toy" className="text-[18px] text-primary" />
          <span className="font-mono-data font-bold text-on-surface">Investigation Agent Log</span>
          <span className="font-mono-data-compact text-outline">{inv.steps.length} steps</span>
        </div>
        <button type="button" onClick={onClose} className="rounded p-1 text-outline hover:text-on-surface" aria-label="Close agent trace" tabIndex={open ? 0 : -1}>
          <Icon name="close" className="text-[18px]" />
        </button>
      </div>
      <div className="flex gap-space-md border-b border-white/5 px-space-lg py-space-md" role="group" aria-label="Filter steps">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            tabIndex={open ? 0 : -1}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={cx(
              "rounded px-space-lg py-0.5 font-mono-data-compact transition-colors",
              filter === f.id ? "bg-primary/20 text-primary" : "text-outline hover:text-on-surface",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ol className="flex flex-1 flex-col gap-space-md overflow-y-auto p-space-lg font-mono-data-compact">
        {steps.length === 0 && <li className="text-outline">No steps yet.</li>}
        {steps.map((step) => (
          <StepCard key={step.n} step={step} />
        ))}
      </ol>
      <div className="flex items-center justify-between border-t border-white/10 bg-[#08090c]/80 p-space-lg font-mono-label-caps uppercase text-outline">
        <span>
          Mode: {inv.mode} · {STAGE_LABEL[inv.stage]}
        </span>
        <span className={cx("flex items-center gap-1", inv.stage === "failed" ? "text-error" : running ? "text-tertiary" : "text-secondary")}>
          <span className={cx("h-1.5 w-1.5 rounded-full", inv.stage === "failed" ? "bg-error" : running ? "animate-pulse bg-tertiary" : "bg-secondary")} />
          {inv.stage === "failed" ? "Stopped" : running ? "Working" : "Idle"}
        </span>
      </div>
    </aside>
  );
}
