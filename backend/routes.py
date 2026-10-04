"""REST API (prefix /api). Owner: Rohit. Contract: contracts/CONTRACTS.md."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from agent import orchestrator, tools
from agent.llm import llm_mode
from backend.store import store
from contracts.models import (
    Approval,
    CreateInvestigationRequest,
    CreateInvestigationResponse,
    HealthResponse,
    Incident,
    Investigation,
    SimulateRequest,
    SimulationResult,
)

router = APIRouter(prefix="/api")


def _get_or_404(investigation_id: str) -> Investigation:
    investigation = store.get(investigation_id)
    if investigation is None:
        raise HTTPException(404, f"unknown investigation: {investigation_id}")
    return investigation


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, llm_mode=llm_mode())


@router.get("/incidents", response_model=list[Incident])
def list_incidents() -> list[Incident]:
    return tools.list_incidents()


@router.post("/investigations", response_model=CreateInvestigationResponse)
def create_investigation(body: CreateInvestigationRequest, background: BackgroundTasks) -> CreateInvestigationResponse:
    try:
        incident = tools.get_incident(body.incident_id)
    except KeyError:
        raise HTTPException(404, f"unknown incident: {body.incident_id}")
    investigation = Investigation(id=f"inv-{uuid.uuid4().hex[:8]}", incident=incident, mode=body.mode)
    store.put(investigation)
    background.add_task(orchestrator.run, investigation.id, store)
    return CreateInvestigationResponse(investigation_id=investigation.id)


@router.get("/investigations/{investigation_id}", response_model=Investigation)
def get_investigation(investigation_id: str) -> Investigation:
    return _get_or_404(investigation_id)


@router.post("/investigations/{investigation_id}/approval", response_model=Investigation)
def submit_approval(investigation_id: str, approval: Approval, background: BackgroundTasks) -> Investigation:
    investigation = _get_or_404(investigation_id)
    if investigation.stage != "awaiting_approval":
        raise HTTPException(409, f"investigation is {investigation.stage}, not awaiting_approval")
    if approval.intervention_id not in {i.id for i in investigation.interventions}:
        raise HTTPException(400, f"unknown intervention: {approval.intervention_id}")
    if approval.at is None:
        approval = approval.model_copy(update={"at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    # Leave awaiting_approval before returning so a double-click gets a 409 instead of a second resume.
    investigation = investigation.model_copy(update={
        "approval": approval,
        "stage": "executing" if approval.decision == "approved" else "replanning",
    })
    store.put(investigation)
    background.add_task(orchestrator.resume_after_approval, investigation_id, approval, store)
    return investigation


@router.post("/simulate", response_model=SimulationResult)
def simulate(body: SimulateRequest) -> SimulationResult:
    try:
        model = tools.call("load_system_model", body.incident_id)
        interventions = [tools.call("get_intervention", i) for i in body.intervention_ids]
    except KeyError as error:
        raise HTTPException(404, str(error))
    return tools.call("simulate", model, interventions, seed=0)
