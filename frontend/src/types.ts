// Hand-written mirror of contracts/models.py (contract v1). Owner: Aryan.
// Update in the same hour as any contract change. Field names match the JSON exactly.

export type Stage =
  | "created"
  | "timeline"
  | "hypotheses"
  | "evidence"
  | "testing"
  | "root_cause"
  | "counterfactual"
  | "awaiting_approval"
  | "executing"
  | "verifying"
  | "resolved"
  | "replanning"
  | "failed";
export type EventKind =
  | "deploy"
  | "config_change"
  | "job_start"
  | "job_end"
  | "metric"
  | "log"
  | "alert"
  | "trace"
  | "external";
export type HypothesisOrigin = "seed" | "llm";
export type HypothesisStatus = "proposed" | "testing" | "supported" | "rejected" | "confirmed";
export type EvidenceKind = "metric" | "trace" | "log" | "config_diff" | "deploy_record" | "external";
export type Stance = "supports" | "refutes" | "neutral";
export type InterventionCategory = "config" | "schedule" | "resilience" | "guardrail" | "rollback";
export type InterventionOp = "set_param" | "block_event" | "shift_event" | "cap_param";
export type Risk = "low" | "med" | "high";
export type Decision = "approved" | "rejected";
export type ExecutionStatus = "applied" | "failed";
export type AgentStepKind = "thought" | "tool_call" | "tool_result" | "decision";
export type InvestigationMode = "replay" | "live";
export type Scalar = number | string;

// ---------------------------------------------------------------- incident data

export interface Window {
  start: string;
  minutes: number;
}

export interface Incident {
  id: string;
  title: string;
  service: string;
  severity: string;
  started_at: string;
  detected_at: string;
  resolved_at: string | null;
  summary: string;
  window: Window;
}

export interface StateChange {
  param: string;
  from: Scalar;
  to: Scalar;
}

export interface Event {
  id: string;
  ts: string;
  t: number;
  source: string;
  kind: EventKind;
  summary: string;
  attributes: Record<string, unknown>;
  state_change: StateChange | null;
}

export interface MetricPoint {
  t: number;
  value: number;
}

export interface MetricSeries {
  name: string;
  unit: string;
  service: string;
  points: MetricPoint[];
}

// ---------------------------------------------------------------- investigation reasoning

export interface HypothesisTest {
  prediction: string;
  observed: string;
  passed: boolean;
}

export interface Hypothesis {
  id: string;
  title: string;
  mechanism: string;
  origin: HypothesisOrigin;
  status: HypothesisStatus;
  confidence: number;
  supporting_evidence_ids: string[];
  refuting_evidence_ids: string[];
  tests: HypothesisTest[];
  rejection_reason: string | null;
}

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  description: string;
  source_event_ids: string[];
  stance: Record<string, Stance>;
  weight: number;
}

export interface CausalLink {
  event_id: string;
  effect: string;
}

export interface RootCause {
  hypothesis_id: string;
  statement: string;
  causal_chain: CausalLink[];
  contributing_factors: string[];
  confidence: number;
}

// ---------------------------------------------------------------- counterfactual

export interface Exogenous {
  demand_rps: number[];
}

export interface ParamChange {
  t: number;
  param: string;
  value: Scalar;
  event_id: string;
}

export interface Slo {
  max_error_rate: number;
  max_breach_minutes: number;
}

export interface SystemModel {
  params: Record<string, Scalar>;
  exogenous: Exogenous;
  param_changes: ParamChange[];
  slo: Slo;
}

export interface InterventionAction {
  op: InterventionOp;
  target: string;
  value: Scalar | null;
}

export interface Intervention {
  id: string;
  title: string;
  category: InterventionCategory;
  action: InterventionAction;
  risk: Risk;
  effort_hours: number;
  rationale: string;
}

export interface SimSeries {
  error_rate: number[];
  pool_wait_ms: number[];
  inflight: number[];
}

export interface SimulationResult {
  intervention_ids: string[]; // [] = baseline
  seed: number;
  series: SimSeries;
  peak_error_rate: number;
  breach_minutes: number;
  prevented: boolean;
}

export interface RankedIntervention {
  intervention_id: string;
  rank: number;
  score: number;
  prevented: boolean;
  breach_minutes_avoided: number;
  reasons: string[];
}

// ---------------------------------------------------------------- approval / execution

export interface Approval {
  intervention_id: string;
  decision: Decision;
  approver: string;
  note?: string;
  at?: string | null;
}

export interface ExecutionResult {
  intervention_id: string;
  applied_changes: InterventionAction[];
  status: ExecutionStatus;
}

export interface VerificationCheck {
  name: string;
  expected: string;
  observed: string;
  passed: boolean;
}

export interface VerificationResult {
  intervention_id: string;
  passed: boolean;
  checks: VerificationCheck[];
  stress_test_passed: boolean;
}

// ---------------------------------------------------------------- agent / investigation

export interface AgentStep {
  n: number;
  stage: Stage;
  kind: AgentStepKind;
  tool: string | null;
  input: Record<string, unknown> | null;
  output_summary: string;
  at: string;
}

export interface Investigation {
  id: string;
  incident: Incident;
  stage: Stage;
  mode: InvestigationMode;
  timeline: Event[];
  hypotheses: Hypothesis[];
  evidence: Evidence[];
  root_cause: RootCause | null;
  interventions: Intervention[];
  simulations: SimulationResult[];
  ranking: RankedIntervention[];
  recommendation: RankedIntervention | null;
  approval: Approval | null;
  execution: ExecutionResult | null;
  verification: VerificationResult | null;
  attempts: number;
  steps: AgentStep[];
  error: string | null;
}

// ---------------------------------------------------------------- API bodies

export interface HealthResponse {
  ok: boolean;
  llm_mode: string;
}

export interface CreateInvestigationRequest {
  incident_id: string;
  mode?: InvestigationMode;
}

export interface CreateInvestigationResponse {
  investigation_id: string;
}

export interface SimulateRequest {
  incident_id: string;
  intervention_ids: string[];
}
