// Pure derivations over the contract types. Nothing here touches the DOM or the network, so it is unit-tested.
import type {
  Evidence,
  Event,
  Hypothesis,
  Intervention,
  Investigation,
  MetricSeries,
  RankedIntervention,
  SimulationResult,
  Stage,
  SystemModel,
} from "../types";

// ---------------------------------------------------------------- views and stages

export type ViewId = "overview" | "timeline" | "hypotheses" | "evidence" | "root-cause" | "lab" | "gate" | "verification";

export interface ViewMeta {
  id: ViewId;
  label: string;
  icon: string;
}

export const VIEWS: readonly ViewMeta[] = [
  { id: "overview", label: "Overview", icon: "dashboard" },
  { id: "timeline", label: "Timeline", icon: "timeline" },
  { id: "hypotheses", label: "Hypotheses", icon: "biotech" },
  { id: "evidence", label: "Evidence", icon: "fact_check" },
  { id: "root-cause", label: "Root Cause", icon: "account_tree" },
  { id: "lab", label: "Counterfactual Lab", icon: "science" },
  { id: "gate", label: "Approval Gate", icon: "verified_user" },
  { id: "verification", label: "Execution & Verification", icon: "task_alt" },
];

export const TERMINAL_STAGES: readonly Stage[] = ["resolved", "failed"];

export const isTerminal = (stage: Stage): boolean => TERMINAL_STAGES.includes(stage);

export const isViewId = (value: string): value is ViewId => VIEWS.some((v) => v.id === value);

/** The view that shows what the agent is doing in `stage`; "follow live" navigates here as the stage advances. */
export function viewForStage(stage: Stage): ViewId {
  switch (stage) {
    case "timeline":
      return "timeline";
    case "hypotheses":
    case "testing":
      return "hypotheses";
    case "evidence":
      return "evidence";
    case "root_cause":
      return "root-cause";
    case "counterfactual":
      return "lab";
    case "awaiting_approval":
    case "replanning":
      return "gate";
    case "executing":
    case "verifying":
    case "resolved":
      return "verification";
    case "created":
    case "failed":
      return "overview";
  }
}

export const STAGE_LABEL: Record<Stage, string> = {
  created: "Queued",
  timeline: "Reconstructing timeline",
  hypotheses: "Proposing hypotheses",
  evidence: "Gathering evidence",
  testing: "Testing hypotheses",
  root_cause: "Determining root cause",
  counterfactual: "Running counterfactuals",
  awaiting_approval: "Awaiting approval",
  executing: "Executing fix (simulated)",
  verifying: "Verifying fix",
  resolved: "Resolved",
  replanning: "Replanning",
  failed: "Failed",
};

export type StepState = "done" | "active" | "waiting" | "pending" | "failed";

export interface PipelineStep {
  id: string;
  label: string;
  view: ViewId;
  state: StepState;
}

const PIPELINE: readonly { id: string; label: string; view: ViewId }[] = [
  { id: "timeline", label: "Timeline Reconstruction", view: "timeline" },
  { id: "hypotheses", label: "Competing Hypotheses", view: "hypotheses" },
  { id: "evidence", label: "Evidence & Testing", view: "evidence" },
  { id: "root_cause", label: "Root Cause Analysis", view: "root-cause" },
  { id: "counterfactual", label: "Counterfactual Replay", view: "lab" },
  { id: "approval", label: "Intervention Approval", view: "gate" },
  { id: "verification", label: "Execution & Verification", view: "verification" },
];

const STEP_OF_STAGE: Record<Exclude<Stage, "failed">, number> = {
  created: -1,
  timeline: 0,
  hypotheses: 1,
  evidence: 2,
  testing: 2,
  root_cause: 3,
  counterfactual: 4,
  awaiting_approval: 5,
  replanning: 5,
  executing: 6,
  verifying: 6,
  resolved: PIPELINE.length,
};

/** Where a failed run stopped: the first pipeline step whose output is missing. */
function firstMissingStep(inv: Investigation): number {
  const produced = [
    inv.timeline.length > 0,
    inv.hypotheses.length > 0,
    inv.evidence.length > 0,
    inv.root_cause !== null,
    inv.ranking.length > 0,
    inv.approval !== null,
    inv.verification?.passed === true,
  ];
  const missing = produced.findIndex((ok) => !ok);
  return missing === -1 ? produced.length - 1 : missing;
}

export function pipeline(inv: Investigation): PipelineStep[] {
  const failed = inv.stage === "failed";
  const current = failed ? firstMissingStep(inv) : STEP_OF_STAGE[inv.stage as Exclude<Stage, "failed">];
  return PIPELINE.map((step, i) => {
    let state: StepState;
    if (i < current) state = "done";
    else if (i === current) state = failed ? "failed" : inv.stage === "awaiting_approval" ? "waiting" : "active";
    else state = "pending";
    return { ...step, state };
  });
}

export function viewState(inv: Investigation, view: ViewId): StepState | "idle" {
  if (view === "overview") return "idle";
  const step = pipeline(inv).find((s) => s.view === view);
  return step ? step.state : "idle";
}

// ---------------------------------------------------------------- timeline

export type EventClass = "cause" | "symptom" | "decoy" | "recovery";

export const EVENT_CLASS_LABEL: Record<EventClass, string> = {
  cause: "Causal trigger",
  symptom: "Symptom",
  decoy: "Decoy",
  recovery: "Recovery",
};

/** Classify from the annotations the evidence engine writes onto `Event.attributes`. */
export function eventClass(event: Event): EventClass {
  if (event.attributes["decoy"] === true) return "decoy";
  if (event.attributes["causal"] === true) return "cause";
  if (/recover/i.test(event.summary)) return "recovery";
  return "symptom";
}

export function sortedTimeline(events: readonly Event[]): Event[] {
  return [...events].sort((a, b) => a.t - b.t || a.id.localeCompare(b.id));
}

export function evidenceForEvent(evidence: readonly Evidence[], eventId: string): Evidence[] {
  return evidence.filter((e) => e.source_event_ids.includes(eventId));
}

// ---------------------------------------------------------------- hypotheses and evidence

export function evidenceById(evidence: readonly Evidence[]): Map<string, Evidence> {
  return new Map(evidence.map((e) => [e.id, e]));
}

export function supportingEvidence(h: Hypothesis, evidence: readonly Evidence[]): Evidence[] {
  const byId = evidenceById(evidence);
  return h.supporting_evidence_ids.flatMap((id) => byId.get(id) ?? []);
}

export function refutingEvidence(h: Hypothesis, evidence: readonly Evidence[]): Evidence[] {
  const byId = evidenceById(evidence);
  return h.refuting_evidence_ids.flatMap((id) => byId.get(id) ?? []);
}

export function hypothesisCounts(hypotheses: readonly Hypothesis[]) {
  return {
    confirmed: hypotheses.filter((h) => h.status === "confirmed").length,
    rejected: hypotheses.filter((h) => h.status === "rejected").length,
    open: hypotheses.filter((h) => h.status !== "confirmed" && h.status !== "rejected").length,
  };
}

// ---------------------------------------------------------------- simulation

export const baselineOf = (sims: readonly SimulationResult[]): SimulationResult | undefined =>
  sims.find((s) => s.intervention_ids.length === 0);

/** The simulation for exactly this set of interventions, in any order. */
export function simulationFor(sims: readonly SimulationResult[], ids: readonly string[]): SimulationResult | undefined {
  const key = [...ids].sort().join("+");
  return sims.find((s) => [...s.intervention_ids].sort().join("+") === key);
}

export interface BreachWindow {
  start: number;
  /** Exclusive end: the first minute back under the SLO. */
  end: number;
  minutes: number;
}

/** The longest run of minutes whose error rate is above the SLO. */
export function breachWindow(errorRate: readonly number[], sloMaxErrorRate: number): BreachWindow | null {
  let best: BreachWindow | null = null;
  let start = -1;
  for (let t = 0; t <= errorRate.length; t++) {
    const over = t < errorRate.length && errorRate[t] > sloMaxErrorRate;
    if (over && start === -1) start = t;
    if (!over && start !== -1) {
      const run = { start, end: t, minutes: t - start };
      if (!best || run.minutes > best.minutes) best = run;
      start = -1;
    }
  }
  return best;
}

export const DEFAULT_SLO = 0.05;

export function sloOf(model: SystemModel | null | undefined): number {
  return model?.slo.max_error_rate ?? DEFAULT_SLO;
}

/** Requests that failed in the simulated baseline: sum of demand (rps) x 60 s x error rate over each minute. */
export function estimatedFailedRequests(demandRps: readonly number[], errorRate: readonly number[]): number {
  let total = 0;
  for (let t = 0; t < Math.min(demandRps.length, errorRate.length); t++) total += demandRps[t] * 60 * errorRate[t];
  return total;
}

/** A "nice" upper bound for an error-rate axis: 0.382 -> 0.4, 0.07 -> 0.1. */
export function niceCeil(value: number, step = 0.1): number {
  if (!(value > 0)) return step;
  return Math.max(step, Math.ceil(value / step - 1e-9) * step);
}

export function metricByName(metrics: readonly MetricSeries[], name: string): MetricSeries | undefined {
  return metrics.find((m) => m.name === name);
}

// ---------------------------------------------------------------- interventions

export interface InterventionRow {
  intervention: Intervention;
  ranked: RankedIntervention | undefined;
  simulation: SimulationResult | undefined;
}

/** One row per intervention, joined to its ranking and its single-intervention simulation. Ranked rows first. */
export function interventionRows(inv: Investigation): InterventionRow[] {
  const rows = inv.interventions.map((intervention) => ({
    intervention,
    ranked: inv.ranking.find((r) => r.intervention_id === intervention.id),
    simulation: simulationFor(inv.simulations, [intervention.id]),
  }));
  return rows.sort((a, b) => (a.ranked?.rank ?? 99) - (b.ranked?.rank ?? 99) || a.intervention.id.localeCompare(b.intervention.id));
}

export type Outcome = "prevented" | "partial" | "no_effect";

export const OUTCOME_LABEL: Record<Outcome, string> = {
  prevented: "Prevented",
  partial: "Partial",
  no_effect: "No effect",
};

export function outcomeOf(sim: SimulationResult | undefined, baseline: SimulationResult | undefined): Outcome {
  if (!sim) return "no_effect";
  if (sim.prevented) return "prevented";
  const base = baseline?.breach_minutes ?? 0;
  return sim.breach_minutes < base ? "partial" : "no_effect";
}

/** Dropped from the ranking by a replan (rejected or failed verification) but still in the catalogue. */
export function droppedInterventionIds(inv: Investigation): string[] {
  const ranked = new Set(inv.ranking.map((r) => r.intervention_id));
  return inv.interventions.filter((i) => !ranked.has(i.id)).map((i) => i.id);
}

export function interventionTitle(inv: Investigation, id: string): string {
  return inv.interventions.find((i) => i.id === id)?.title ?? id;
}

export function describeAction(action: { op: string; target: string; value?: number | string | null }): string {
  const value = action.value === null || action.value === undefined ? "" : ` = ${action.value}`;
  return `${action.op} ${action.target}${value}`;
}

// ---------------------------------------------------------------- misc
