import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import AgentDrawer from "./components/AgentDrawer";
import ShaderBackground from "./components/ShaderBackground";
import { Header, Sidebar, StageRibbon } from "./components/Shell";
import { Button, Icon, Notice, Pending, cx } from "./components/ui";
import { useBackend, useIncidentData } from "./hooks/useBackend";
import { useHashRoute, useStoredString } from "./hooks/useBrowser";
import { useInvestigation } from "./hooks/useInvestigation";
import { viewForStage, type ViewId } from "./lib/derive";
import { EMPTY_FOCUS, type Focus, type Nav } from "./lib/nav";
import type { Approval, Incident, InvestigationMode, Stage } from "./types";
import Evidence from "./views/Evidence";
import Gate from "./views/Gate";
import Hypotheses from "./views/Hypotheses";
import Lab from "./views/Lab";
import Overview from "./views/Overview";
import RootCause from "./views/RootCause";
import StartScreen from "./views/StartScreen";
import Timeline from "./views/Timeline";
import Verification from "./views/Verification";

interface Toast {
  id: number;
  tone: "primary" | "secondary" | "error";
  icon: string;
  text: string;
}

export default function App() {
  const backend = useBackend();
  const [route, navigate] = useHashRoute();
  const run = useInvestigation(route.investigationId);
  const inv = run.investigation;
  const data = useIncidentData(inv?.incident.id ?? null);

  const [focus, setFocusState] = useState<Focus>(EMPTY_FOCUS);
  const [follow, setFollow] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [approver, setApprover] = useStoredString("counterfact.approver", "operator");
  const [lastRun, setLastRun] = useStoredString("counterfact.lastRun", "");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const toast = useCallback((tone: Toast["tone"], icon: string, text: string) => {
    const id = ++toastId.current;
    setToasts((list) => [...list, { id, tone, icon, text }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 6000);
  }, []);

  const view = route.view;

  // Follow the agent: when the stage advances and the user has not taken over, move to the view that shows it.
  const seen = useRef<{ id: string; stage: Stage } | null>(null);
  useEffect(() => {
    if (!inv) {
      seen.current = null;
      return;
    }
    const prev = seen.current;
    seen.current = { id: inv.id, stage: inv.stage };
    if (!prev || prev.id !== inv.id || prev.stage === inv.stage) return;
    if (follow) navigate({ view: viewForStage(inv.stage) });
    if (inv.stage === "awaiting_approval") toast("primary", "front_hand", inv.attempts ? "New recommendation ready for your approval." : "Recommendation ready. Review it at the approval gate.");
    if (inv.stage === "resolved") toast("secondary", "task_alt", "Fix verified in the simulated environment.");
    if (inv.stage === "failed") toast("error", "report", inv.error ?? "The investigation stopped.");
  }, [inv, follow, navigate, toast]);

  // A stale id (the backend keeps runs in memory, so a restart forgets them) falls back to the start screen.
  useEffect(() => {
    if (run.gone && route.investigationId) {
      setNotice(`Investigation ${route.investigationId} no longer exists on the backend, which keeps runs in memory and forgets them on restart. Start a new one.`);
      if (lastRun === route.investigationId) setLastRun("");
      navigate({ investigationId: null, view: "overview" });
    }
  }, [run.gone, route.investigationId, lastRun, setLastRun, navigate]);

  useEffect(() => {
    document.title = inv ? `${inv.incident.id} · ${inv.stage.replace("_", " ")} · COUNTERFACT` : "COUNTERFACT";
  }, [inv]);

  const setFocus = useCallback((patch: Partial<Focus>) => setFocusState((f) => ({ ...f, ...patch })), []);
  const go = useCallback(
    (next: ViewId, patch?: Partial<Focus>) => {
      if (patch) setFocus(patch);
      setFollow(false);
      navigate({ view: next });
      window.scrollTo({ top: 0 });
    },
    [navigate, setFocus],
  );
  const nav: Nav = useMemo(() => ({ focus, go, setFocus }), [focus, go, setFocus]);

  const start = async (incident: Incident, mode: InvestigationMode) => {
    setStarting(true);
    setStartError(null);
    setNotice(null);
    try {
      const { investigation_id } = await api.startInvestigation(incident.id, mode);
      setLastRun(investigation_id);
      setFocusState(EMPTY_FOCUS);
      setFollow(true);
      navigate({ investigationId: investigation_id, view: "overview" });
    } catch (error) {
      setStartError(error instanceof ApiError ? error.message : (error as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const newRun = () => {
    setStartError(null);
    setNotice(null);
    setFocusState(EMPTY_FOCUS);
    navigate({ investigationId: null, view: "overview" });
  };

  const decide = async (approval: Approval) => {
    if (!inv) return;
    const next = await api.submitApproval(inv.id, approval); // throws ApiError; the gate shows its detail inline
    run.accept(next);
    setFollow(true);
    if (approval.decision === "approved") navigate({ view: "verification" });
  };

  const resumeFollow = () => {
    setFollow(true);
    if (inv) navigate({ view: viewForStage(inv.stage) });
  };

  const showStart = !route.investigationId;

  return (
    <div className="relative min-h-screen bg-[#08090c] text-on-surface">
      <ShaderBackground />
      <Header inv={inv} online={backend.online} llmMode={backend.llmMode} onOpenAgent={() => setDrawer((open) => !open)} onNew={newRun} />

      {showStart ? (
        <div className="relative z-10">
          <StartScreen
            backend={backend}
            starting={starting}
            error={startError}
            notice={notice}
            lastRunId={lastRun || null}
            onStart={start}
            onResume={(id) => {
              setStartError(null);
              setNotice(null);
              navigate({ investigationId: id, view: "overview" });
            }}
          />
        </div>
      ) : !inv ? (
        <div className="relative z-10 mx-auto max-w-3xl px-space-xl pt-24">
          {run.offline ? (
            <Notice tone="error" icon="cloud_off" title="The backend is not reachable" action={<Button onClick={newRun}>Back</Button>}>
              Still retrying run {route.investigationId}…
            </Notice>
          ) : (
            <Pending title={`Loading ${route.investigationId}`} hint="Fetching the investigation from the backend." rows={3} />
          )}
        </div>
      ) : (
        <>
          <Sidebar inv={inv} view={view} onSelect={(v) => go(v)} />
          <div className="relative z-10 pt-14 lg:pl-64">
            <main className="mx-auto flex w-full max-w-[1720px] flex-col gap-space-md p-space-lg">
              <StageRibbon inv={inv} view={view} follow={follow} onSelect={(v) => go(v)} onFollow={resumeFollow} />

              {run.offline && (
                <Notice tone="error" icon="cloud_off" title="Backend unreachable">
                  Showing the last known state. Retrying every 2 seconds.
                </Notice>
              )}
              {backend.healthError && (
                <Notice tone="error" icon="report" title="Backend health check failed">
                  {backend.healthError}
                </Notice>
              )}
              {inv.stage === "failed" && (
                <Notice tone="error" icon="report" title="The investigation stopped without a verified fix">
                  {inv.error ?? "No reason was recorded."}
                </Notice>
              )}
              {data.error && (
                <Notice tone="tertiary" icon="warning" title="Telemetry and SLO data could not be loaded">
                  Charts fall back to the simulated baseline and a 5% SLO. {data.error}
                </Notice>
              )}

              <div key={view} className="animate-fade-in">
                {view === "overview" && <Overview inv={inv} data={data} onNavigate={(v) => go(v)} />}
                {view === "timeline" && <Timeline inv={inv} data={data} nav={nav} />}
                {view === "hypotheses" && <Hypotheses inv={inv} nav={nav} />}
                {view === "evidence" && <Evidence inv={inv} nav={nav} />}
                {view === "root-cause" && <RootCause inv={inv} nav={nav} />}
                {view === "lab" && <Lab inv={inv} data={data} nav={nav} />}
                {view === "gate" && <Gate inv={inv} nav={nav} approver={approver} onApprover={setApprover} onDecide={decide} />}
                {view === "verification" && <Verification inv={inv} nav={nav} />}
              </div>
            </main>
          </div>
          <AgentDrawer inv={inv} open={drawer} onClose={() => setDrawer(false)} />
        </>
      )}

      <div className="pointer-events-none fixed bottom-4 left-1/2 z-[70] flex -translate-x-1/2 flex-col items-center gap-space-md" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto animate-fade-up flex items-center gap-space-lg rounded border bg-[#0c0e12]/95 px-space-xl py-space-lg font-body-sm shadow-xl backdrop-blur-md",
              t.tone === "error" ? "border-error/50 text-error" : t.tone === "secondary" ? "border-secondary/50 text-secondary" : "border-primary/50 text-primary",
            )}
          >
            <Icon name={t.icon} className="text-[18px]" />
            <span className="text-on-surface">{t.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
