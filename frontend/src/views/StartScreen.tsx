// Entry screen: pick an incident and a run mode, then start an investigation.
import { useState } from "react";
import { Badge, Button, Icon, Notice, cx, type Tone } from "../components/ui";
import { clock } from "../lib/format";
import type { BackendState } from "../hooks/useBackend";
import type { Incident, InvestigationMode } from "../types";

const SEVERITY_TONE: Record<string, Tone> = { sev1: "error", sev2: "tertiary", sev3: "primary" };

export default function StartScreen({
  backend,
  starting,
  error,
  lastRunId,
  onStart,
  onResume,
}: {
  backend: BackendState;
  starting: boolean;
  error: string | null;
  lastRunId: string | null;
  onStart: (incident: Incident, mode: InvestigationMode) => void;
  onResume: (id: string) => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [mode, setMode] = useState<InvestigationMode>("replay");
  const selected = backend.incidents.find((i) => i.id === (picked ?? backend.incidents[0]?.id)) ?? null;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center gap-space-xl px-space-xl pb-16 pt-24">
      <div className="animate-fade-up flex flex-col gap-space-md">
        <Badge tone="primary" className="self-start">
          <Icon name="science" className="text-[12px]" /> Forensic incident lab
        </Badge>
        <h1 className="font-headline-xl text-[32px] leading-10 text-on-surface">
          Replay the outage. <span className="text-primary">Change one thing.</span> See if history changes.
        </h1>
        <p className="max-w-2xl font-body-md text-on-surface-variant">
          COUNTERFACT reconstructs what happened, tests competing explanations against the evidence, then re-runs the incident with candidate fixes to find the one that
          would have prevented it. You approve before anything is executed, and execution only ever touches the simulated environment.
        </p>
      </div>

      {backend.online === false && (
        <Notice
          tone="error"
          icon="cloud_off"
          title="The backend is not reachable"
          action={<Button onClick={backend.recheck} icon="refresh">Retry</Button>}
        >
          Start it from the repository root with <code className="text-primary">python -m uvicorn backend.main:app --port 8000</code>. This page keeps checking.
        </Notice>
      )}
      {backend.healthError && (
        <Notice tone="error" icon="report" title="The backend reports a broken fixture">
          {backend.healthError}
        </Notice>
      )}
      {error && (
        <Notice tone="error" icon="error" title="Could not start the investigation">
          {error}
        </Notice>
      )}

      <div className="glass animate-fade-up flex flex-col gap-space-xl p-space-xl" style={{ animationDelay: "80ms" }}>
        <div className="flex items-center justify-between">
          <span className="font-mono-label-caps uppercase tracking-wider text-outline">Incident</span>
          <span className="font-mono-data-compact text-outline">{backend.incidents.length} available</span>
        </div>

        {backend.incidents.length === 0 && backend.online !== false && (
          <div className="flex flex-col gap-space-md">
            <div className="skeleton h-20" />
          </div>
        )}

        <div className="flex flex-col gap-space-md" role="radiogroup" aria-label="Incident">
          {backend.incidents.map((incident) => {
            const active = incident.id === selected?.id;
            return (
              <button
                key={incident.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setPicked(incident.id)}
                className={cx(
                  "flex flex-col gap-space-md rounded border p-space-xl text-left transition-all",
                  active ? "border-primary bg-primary/10 shadow-[0_0_20px_rgba(76,215,246,0.18)]" : "border-white/10 bg-[#101318]/60 hover:border-white/25",
                )}
              >
                <div className="flex flex-wrap items-center gap-space-md">
                  <span className="font-mono-data font-semibold text-primary">{incident.id}</span>
                  <Badge tone={SEVERITY_TONE[incident.severity.toLowerCase()] ?? "muted"}>{incident.severity}</Badge>
                  <span className="font-mono-data text-on-surface-variant">{incident.service}</span>
                  <span className="ml-auto font-mono-data-compact text-outline">
                    detected {clock(incident.detected_at)} UTC · {incident.window.minutes} min window
                  </span>
                </div>
                <div className="font-headline-sm text-on-surface">{incident.title}</div>
                <p className="font-body-sm text-on-surface-variant">{incident.summary}</p>
              </button>
            );
          })}
        </div>

        <div className="flex flex-col gap-space-md border-t border-white/10 pt-space-xl md:flex-row md:items-end md:justify-between">
          <div className="flex flex-col gap-space-md">
            <span className="font-mono-label-caps uppercase tracking-wider text-outline">Agent narration</span>
            <div className="flex items-center self-start rounded border border-white/10 bg-[#14161a]/90 p-0.5" role="radiogroup" aria-label="Run mode">
              {(["replay", "live"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => setMode(m)}
                  className={cx(
                    "rounded px-space-xl py-1 font-mono-label-caps uppercase transition-colors",
                    mode === m ? "bg-primary-container font-semibold text-on-primary-container shadow-[0_0_12px_rgba(6,182,212,0.4)]" : "text-on-surface-variant hover:text-on-surface",
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
            <p className="max-w-md font-body-sm text-on-surface-variant">
              {mode === "replay"
                ? "Recorded narration: deterministic, no network or API key needed."
                : `Live LLM narration from the configured endpoint (backend is set to "${backend.llmMode ?? "replay"}"). If it is not configured or a call fails, the run falls back to replay and says so in the agent trace.`}
            </p>
          </div>
          <Button
            variant="primary"
            icon="play_arrow"
            disabled={!selected || starting || backend.online === false}
            onClick={() => selected && onStart(selected, mode)}
            className="!px-space-xl !py-2 uppercase"
          >
            {starting ? "Starting…" : "Investigate"}
          </Button>
        </div>
      </div>

      {lastRunId && (
        <button
          type="button"
          onClick={() => onResume(lastRunId)}
          className="animate-fade-up flex items-center gap-space-md self-start rounded border border-white/10 px-space-xl py-space-md font-mono-data text-on-surface-variant transition-colors hover:border-white/25 hover:text-on-surface"
          style={{ animationDelay: "160ms" }}
        >
          <Icon name="history" className="text-[16px]" />
          Resume last run <code className="text-primary">{lastRunId}</code>
        </button>
      )}
    </div>
  );
}
