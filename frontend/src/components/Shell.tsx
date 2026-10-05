// App chrome from the Stitch workspace: top bar, left navigation and the stage ribbon.
import {
  STAGE_LABEL,
  VIEWS,
  baselineOf,
  pipeline,
  viewState,
  type StepState,
  type ViewId,
} from "../lib/derive";
import type { Investigation } from "../types";
import { Badge, Button, Icon, cx, type Tone } from "./ui";

function LogoMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true" className="drop-shadow-[0_0_8px_rgba(6,182,212,0.45)]">
      <rect x="1.5" y="1.5" width="29" height="29" rx="3" stroke="#06b6d4" strokeWidth="1.5" />
      <path d="M6 22 L12 22 L16 10 L20 22 L26 22" stroke="#4cd7f6" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M12 22 C 15 22, 17 14, 26 10" stroke="#4edea3" strokeWidth="1.5" strokeDasharray="2.5 2" strokeLinecap="round" />
    </svg>
  );
}

const SEVERITY_TONE: Record<string, Tone> = { sev1: "error", sev2: "tertiary", sev3: "primary" };

export function StagePill({ inv }: { inv: Investigation }) {
  const stage = inv.stage;
  const tone: Tone =
    stage === "resolved" ? "secondary" : stage === "failed" ? "error" : stage === "replanning" ? "tertiary" : stage === "awaiting_approval" ? "primary" : "tertiary";
  const live = stage !== "resolved" && stage !== "failed" && stage !== "awaiting_approval";
  const dot: Record<Tone, string> = { primary: "bg-primary", secondary: "bg-secondary", tertiary: "bg-tertiary", error: "bg-error", muted: "bg-outline" };
  return (
    <Badge tone={tone} className="py-1" title={`stage: ${stage}`}>
      <span className={cx("h-1.5 w-1.5 rounded-full", dot[tone], live && "animate-pulse")} />
      {STAGE_LABEL[stage]}
    </Badge>
  );
}

export function Header({
  inv,
  online,
  llmMode,
  onOpenAgent,
  onNew,
}: {
  inv: Investigation | null;
  online: boolean | null;
  llmMode: string | null;
  onOpenAgent: () => void;
  onNew: () => void;
}) {
  return (
    <header className="fixed inset-x-0 top-0 z-50 flex h-14 select-none items-center justify-between gap-space-md border-b border-white/10 bg-[#08090c]/80 px-space-lg shadow-[0_4px_30px_rgba(0,0,0,0.5)] backdrop-blur-xl">
      <button type="button" onClick={onNew} className="flex items-center gap-space-md rounded text-left" aria-label="COUNTERFACT home">
        <LogoMark />
        <div className="hidden flex-col sm:flex">
          <span className="font-mono-metric-lg text-headline-sm uppercase leading-none tracking-wider text-primary drop-shadow-[0_0_10px_rgba(76,215,246,0.45)]">Counterfact</span>
          <span className="mt-space-xs hidden font-mono-label-caps uppercase leading-none tracking-widest text-outline sm:block">Incident Investigation</span>
        </div>
      </button>

      {inv && (
        <div className="hidden min-w-0 items-center gap-space-md rounded border border-white/10 bg-[#12151b]/80 px-space-lg py-space-md shadow-inner backdrop-blur-md lg:flex">
          <span className="font-mono-data font-semibold text-primary">{inv.incident.id}</span>
          <span className="font-mono-data text-outline">·</span>
          <span className="max-w-xs truncate font-body-sm text-on-surface" title={inv.incident.title}>{inv.incident.title}</span>
          <span className="font-mono-data text-outline">·</span>
          <Badge tone={SEVERITY_TONE[inv.incident.severity.toLowerCase()] ?? "muted"}>{inv.incident.severity}</Badge>
          <span className="font-mono-data text-outline">·</span>
          <span className="font-mono-data text-on-surface-variant">{inv.incident.service}</span>
        </div>
      )}

      <div className="flex items-center gap-space-md">
        {inv && (
          <span
            className="hidden items-center rounded border border-white/10 bg-[#14161a]/90 p-0.5 sm:flex"
            title={`This run was started in ${inv.mode} mode. The backend LLM is configured as "${llmMode ?? "unknown"}".`}
          >
            {(["replay", "live"] as const).map((mode) => (
              <span
                key={mode}
                className={cx(
                  "rounded px-space-lg py-0.5 font-mono-label-caps uppercase",
                  inv.mode === mode ? "bg-primary-container font-semibold text-on-primary-container shadow-[0_0_12px_rgba(6,182,212,0.4)]" : "text-outline",
                )}
              >
                {mode}
              </span>
            ))}
          </span>
        )}
        {inv && <StagePill inv={inv} />}
        {inv && (
          <Button onClick={onOpenAgent} icon="smart_toy" className="!px-space-lg !py-1">
            <span className="hidden md:inline">Agent Trace</span>
            <span className="rounded bg-primary/20 px-1 font-mono-label-caps font-semibold text-primary tabular-nums" aria-label={`${inv.steps.length} steps`}>
              {inv.steps.length}
            </span>
          </Button>
        )}
        {inv && (
          <Button onClick={onNew} icon="add" variant="ghost" className="!px-space-lg !py-1" aria-label="New investigation">
            <span className="hidden xl:inline">New</span>
          </Button>
        )}
        <span
          className="flex items-center gap-1.5 font-mono-label-caps uppercase text-outline"
          title={online === false ? "Backend unreachable" : online ? "Backend connected" : "Connecting to backend"}
        >
          <span className={cx("h-1.5 w-1.5 rounded-full", online === false ? "bg-error animate-pulse" : online ? "bg-secondary" : "bg-outline animate-pulse")} />
          <span className="hidden 2xl:inline">{online === false ? "offline" : online ? "api" : "…"}</span>
        </span>
      </div>
    </header>
  );
}

function StepIcon({ state }: { state: StepState | "idle" }) {
  switch (state) {
    case "done":
      return <Icon name="check_circle" className="text-[15px] text-secondary" />;
    case "active":
      return <span className="h-2 w-2 animate-pulse rounded-full bg-primary shadow-[0_0_8px_#4cd7f6]" />;
    case "waiting":
      return <Icon name="front_hand" className="text-[14px] text-primary" />;
    case "failed":
      return <Icon name="error" className="text-[15px] text-error" />;
    case "pending":
      return <Icon name="lock" className="text-[13px] text-outline/60" />;
    default:
      return null;
  }
}

export function Sidebar({ inv, view, onSelect }: { inv: Investigation; view: ViewId; onSelect: (v: ViewId) => void }) {
  const baseline = baselineOf(inv.simulations);
  return (
    <aside className="fixed bottom-0 left-0 top-14 z-40 hidden w-64 select-none flex-col justify-between border-r border-white/10 bg-[#090b10]/85 backdrop-blur-xl lg:flex">
      <div className="overflow-y-auto py-space-md">
        <div className="mb-space-md flex items-center justify-between px-space-xl">
          <span className="font-mono-label-caps uppercase tracking-wider text-outline">Investigation Canvas</span>
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary/70" />
        </div>
        <nav className="flex flex-col" aria-label="Investigation stages">
          {VIEWS.map((v) => {
            const active = v.id === view;
            const state = viewState(inv, v.id);
            return (
              <button
                key={v.id}
                type="button"
                onClick={() => onSelect(v.id)}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex h-9 items-center justify-between gap-space-md border-l-2 px-space-lg font-mono-data transition-colors",
                  active
                    ? "border-primary bg-primary/15 font-semibold text-primary shadow-[inset_0_0_12px_rgba(76,215,246,0.1)]"
                    : "border-transparent text-on-surface-variant hover:bg-white/5 hover:text-on-surface",
                )}
              >
                <span className="flex min-w-0 items-center gap-space-md whitespace-nowrap">
                  <Icon name={v.icon} className="text-[16px]" />
                  <span className="truncate">{v.label}</span>
                </span>
                <span className="flex w-4 shrink-0 items-center justify-center">
                  <StepIcon state={state} />
                </span>
              </button>
            );
          })}
        </nav>
      </div>
      <div className="border-t border-white/10 bg-[#0c0e12]/60 p-space-lg backdrop-blur-sm">
        <div className="flex flex-col gap-space-md font-mono-label-caps text-outline">
          <div className="flex items-center justify-between">
            <span className="text-on-surface-variant">{inv.incident.id}</span>
            <span className="font-semibold uppercase text-error">{inv.incident.severity}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>RUN</span>
            <span className="font-mono-data-compact text-on-surface-variant">{inv.id}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>SERVICE</span>
            <span className="font-mono-data-compact text-on-surface-variant">{inv.incident.service}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>SIMULATION</span>
            <span className="flex items-center gap-1 font-mono-data-compact text-secondary">
              <span className="h-1 w-1 rounded-full bg-secondary" />
              {baseline ? `Seed ${baseline.seed} (deterministic)` : "not run yet"}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

const RIBBON_LABEL: Record<ViewId, string> = {
  overview: "Overview",
  timeline: "Timeline",
  hypotheses: "Hypotheses",
  evidence: "Evidence",
  "root-cause": "Root Cause",
  lab: "Lab",
  gate: "Gate",
  verification: "Verify",
};

export function StageRibbon({
  inv,
  view,
  follow,
  onSelect,
  onFollow,
}: {
  inv: Investigation;
  view: ViewId;
  follow: boolean;
  onSelect: (v: ViewId) => void;
  onFollow: () => void;
}) {
  const steps = pipeline(inv);
  const running = inv.stage !== "resolved" && inv.stage !== "failed";
  return (
    <section className="glass flex flex-col justify-between gap-space-md p-space-md md:flex-row md:items-center" aria-label="Stages">
      <div className="no-scrollbar flex items-center gap-space-sm overflow-x-auto py-0.5" role="tablist">
        {VIEWS.map((v, i) => {
          const active = v.id === view;
          const state = viewState(inv, v.id);
          const lab = v.id === "lab";
          return (
            <button
              key={v.id}
              role="tab"
              type="button"
              aria-selected={active}
              onClick={() => onSelect(v.id)}
              className={cx(
                "flex items-center gap-space-md whitespace-nowrap rounded border px-space-lg py-1 font-mono-label-caps uppercase transition-colors",
                active
                  ? "border-primary/40 bg-primary/15 text-primary shadow-[0_0_10px_rgba(76,215,246,0.2)]"
                  : "border-transparent text-on-surface-variant hover:text-on-surface",
                lab && !active && "border-primary/30 bg-primary-container/10 text-primary",
                state === "pending" && !active && "opacity-60",
              )}
            >
              {state === "active" ? (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary shadow-[0_0_6px_#4cd7f6]" />
              ) : state === "done" ? (
                <Icon name="check" className="text-[12px] text-secondary" />
              ) : state === "waiting" ? (
                <Icon name="front_hand" className="text-[12px]" />
              ) : state === "failed" ? (
                <Icon name="error" className="text-[12px] text-error" />
              ) : lab ? (
                <Icon name="science" className="text-[12px]" />
              ) : null}
              {i + 1}. {RIBBON_LABEL[v.id]}
              {v.id === "evidence" && inv.evidence.length > 0 && ` (${inv.evidence.length})`}
            </button>
          );
        })}
      </div>
      <div className="flex shrink-0 items-center gap-space-md">
        <div className="hidden items-center gap-space-md rounded border border-white/10 bg-[#08090c]/80 px-space-lg py-1 font-mono-data-compact text-on-surface-variant shadow-inner 2xl:flex">
          <span className="h-2 w-2 rounded-full bg-secondary shadow-[0_0_8px_#4edea3]" />
          <span className="font-medium text-on-surface">Deterministic Sandbox</span>
          <span className="text-outline">|</span>
          <span>{steps.filter((s) => s.state === "done").length}/{steps.length} stages</span>
        </div>
        {running && (
          <button
            type="button"
            onClick={onFollow}
            aria-pressed={follow}
            title={follow ? "Following the agent. Click a stage to take control." : "Jump to what the agent is doing now and follow it."}
            className={cx(
              "flex items-center gap-space-md rounded border px-space-lg py-1 font-mono-data-compact transition-all",
              follow ? "border-primary/50 bg-primary/15 text-primary" : "border-white/15 bg-[#161920]/80 text-on-surface hover:bg-[#1f232c]",
            )}
          >
            <Icon name={follow ? "podcasts" : "play_arrow"} className={cx("text-[14px]", follow && "animate-pulse")} />
            {follow ? "Following live" : "Follow live"}
          </button>
        )}
      </div>
    </section>
  );
}
