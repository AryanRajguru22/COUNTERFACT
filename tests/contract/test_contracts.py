"""Contract parsing: the shared models accept the JSON shapes everyone codes against."""

import pytest
from pydantic import ValidationError

from contracts.models import AgentStep, Approval, Event, Investigation
from data.loader import load_incident


def test_event_state_change_uses_from_alias():
    event = Event.model_validate({
        "id": "E-1", "ts": "2026-09-28T14:05:00Z", "t": 5, "source": "svc", "kind": "config_change",
        "summary": "x", "state_change": {"param": "pool_size", "from": 50, "to": 10},
    })
    assert event.state_change.from_ == 50
    assert event.model_dump(mode="json")["state_change"] == {"param": "pool_size", "from": 50, "to": 10}


def test_investigation_round_trips_through_json():
    investigation = Investigation(
        id="inv-1", incident=load_incident("INC-2041"),
        steps=[AgentStep(n=1, stage="timeline", kind="thought", output_summary="hi", at="2026-09-28T14:00:00Z")],
        approval=Approval(intervention_id="I1", decision="approved", approver="aryan"),
    )
    restored = Investigation.model_validate_json(investigation.model_dump_json())
    assert restored == investigation
    assert restored.stage == "created"


def test_invalid_enum_is_rejected():
    with pytest.raises(ValidationError):
        Approval(intervention_id="I1", decision="maybe", approver="x")
