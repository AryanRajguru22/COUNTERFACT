"""COUNTERFACT shared domain models — contract v1 (frozen at foundation).

Gatekeeper: Rohit. Rules: additive only (new optional fields), never rename or
remove a field, announce every change in team chat, and mirror it in
frontend/src/types.ts in the same hour.

Conventions:
- Event timestamps are ISO-8601 UTC strings.
- `t` is an integer minute index from Incident.window.start.
- IDs are short readable strings: E-001, H2, EV-05, I3.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    # Accept and emit the JSON field names (e.g. "from") everywhere.
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True, serialize_by_alias=True)


# ---------------------------------------------------------------- enums

Stage = Literal[
    "created",
    "timeline",
    "hypotheses",
    "evidence",
    "testing",
    "root_cause",
    "counterfactual",
    "awaiting_approval",
    "executing",
    "verifying",
    "resolved",
    "replanning",
    "failed",
]
EventKind = Literal[
    "deploy", "config_change", "job_start", "job_end", "metric", "log", "alert", "trace", "external"
]
HypothesisOrigin = Literal["seed", "llm"]
HypothesisStatus = Literal["proposed", "testing", "supported", "rejected", "confirmed"]
EvidenceKind = Literal["metric", "trace", "log", "config_diff", "deploy_record", "external"]
Stance = Literal["supports", "refutes", "neutral"]
InterventionCategory = Literal["config", "schedule", "resilience", "guardrail", "rollback"]
InterventionOp = Literal["set_param", "block_event", "shift_event", "cap_param"]
Risk = Literal["low", "med", "high"]
Decision = Literal["approved", "rejected"]
ExecutionStatus = Literal["applied", "failed"]
AgentStepKind = Literal["thought", "tool_call", "tool_result", "decision"]
InvestigationMode = Literal["replay", "live"]

Scalar = int | float | str


# ---------------------------------------------------------------- incident data


class Window(Contract):
    start: str
    minutes: int


class Incident(Contract):
    id: str
    title: str
    service: str
    severity: str
    started_at: str
    detected_at: str
    resolved_at: str | None = None
    summary: str
    window: Window


class StateChange(Contract):
    param: str
    from_: Scalar = Field(alias="from")
    to: Scalar


class Event(Contract):
    id: str
    ts: str
    t: int
    source: str
    kind: EventKind
    summary: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    state_change: StateChange | None = None


class MetricPoint(Contract):
    t: int
    value: float


class MetricSeries(Contract):
    name: str
    unit: str
    service: str
    points: list[MetricPoint]


# ---------------------------------------------------------------- investigation reasoning


class HypothesisTest(Contract):
    prediction: str
    observed: str
    passed: bool


class Hypothesis(Contract):
    id: str
    title: str
    mechanism: str
    origin: HypothesisOrigin
    status: HypothesisStatus
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    refuting_evidence_ids: list[str] = Field(default_factory=list)
    tests: list[HypothesisTest] = Field(default_factory=list)
    rejection_reason: str | None = None


class Evidence(Contract):
    id: str
    kind: EvidenceKind
    description: str
    source_event_ids: list[str] = Field(default_factory=list)
    stance: dict[str, Stance]  # hypothesis_id -> stance
    weight: float = Field(ge=0, le=1)


class CausalLink(Contract):
    event_id: str
    effect: str


class RootCause(Contract):
    hypothesis_id: str
    statement: str
    causal_chain: list[CausalLink]
    contributing_factors: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


# ---------------------------------------------------------------- counterfactual


class Exogenous(Contract):
    demand_rps: list[float]  # one value per t


class ParamChange(Contract):
    t: int
    param: str
    value: Scalar
    event_id: str


class Slo(Contract):
    max_error_rate: float
    max_breach_minutes: int


class SystemModel(Contract):
    params: dict[str, Scalar]  # pool_size, conn_hold_ms, timeout_ms, retry_max, batch_conns, ...
    exogenous: Exogenous
    param_changes: list[ParamChange]
    slo: Slo


class InterventionAction(Contract):
    op: InterventionOp
    target: str
    value: Scalar | None = None


class Intervention(Contract):
    id: str
    title: str
    category: InterventionCategory
    action: InterventionAction
    risk: Risk
    effort_hours: float
    rationale: str


class SimSeries(Contract):
    error_rate: list[float]
    pool_wait_ms: list[float]
    inflight: list[float]


class SimulationResult(Contract):
    intervention_ids: list[str]  # [] = baseline
    seed: int
    series: SimSeries
    peak_error_rate: float
    breach_minutes: int
    prevented: bool


class RankedIntervention(Contract):
    intervention_id: str
    rank: int
    score: float
    prevented: bool
    breach_minutes_avoided: int
    reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- approval / execution


class Approval(Contract):
    intervention_id: str
    decision: Decision
    approver: str
    note: str = ""
    at: str | None = None  # filled by the backend when omitted


class ExecutionResult(Contract):
    intervention_id: str
    applied_changes: list[InterventionAction]
    status: ExecutionStatus


class VerificationCheck(Contract):
    name: str
    expected: str
    observed: str
    passed: bool


class VerificationResult(Contract):
    intervention_id: str
    passed: bool
    checks: list[VerificationCheck]
    stress_test_passed: bool


# ---------------------------------------------------------------- agent / investigation


class AgentStep(Contract):
    n: int
    stage: Stage
    kind: AgentStepKind
    tool: str | None = None
    input: dict[str, Any] | None = None
    output_summary: str
    at: str


class Investigation(Contract):
    id: str
    incident: Incident
    stage: Stage = "created"
    mode: InvestigationMode = "replay"  # persisted at creation; the orchestrator reads it from here
    timeline: list[Event] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    root_cause: RootCause | None = None
    interventions: list[Intervention] = Field(default_factory=list)
    simulations: list[SimulationResult] = Field(default_factory=list)
    ranking: list[RankedIntervention] = Field(default_factory=list)
    recommendation: RankedIntervention | None = None
    approval: Approval | None = None
    execution: ExecutionResult | None = None
    verification: VerificationResult | None = None
    attempts: int = 0
    steps: list[AgentStep] = Field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------- API request/response bodies


class HealthResponse(Contract):
    ok: bool
    llm_mode: str


class CreateInvestigationRequest(Contract):
    incident_id: str
    mode: InvestigationMode = "replay"


class CreateInvestigationResponse(Contract):
    investigation_id: str


class SimulateRequest(Contract):
    incident_id: str
    intervention_ids: list[str] = Field(default_factory=list)
