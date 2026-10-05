"""H6: the replay engine turns the system model and intervention actions into per-minute parameters."""

import pytest

from contracts.models import InterventionAction, SystemModel
from data.loader import load_events
from simulation import get_intervention, load_system_model
from simulation.interventions import CATALOGUE
from simulation.replay import replay

INCIDENT = "INC-2041"
MINUTES = range(60)


def _model() -> SystemModel:
    return load_system_model(INCIDENT)


def _actions(*ids: str) -> list[InterventionAction]:
    return [get_intervention(i).action for i in ids]


def _series(timeline, param):
    return [minute[param] for minute in timeline]


def _batch(start: int, end: int) -> list[int]:
    """batch_conns when the job holds 8 connections for minutes [start, end)."""
    return [8 if start <= t < end else 0 for t in MINUTES]


BASELINE_POOL = [50 if t < 5 else 10 for t in MINUTES]
BASELINE_BATCH = _batch(30, 52)


def test_output_has_one_full_param_set_per_demand_minute():
    model = _model()
    timeline = replay(model)
    assert len(timeline) == len(model.exogenous.demand_rps) == 60
    assert all(set(minute) == set(model.params) for minute in timeline)


@pytest.mark.parametrize("t, pool_size, batch_conns", [
    (0, 50, 0), (4, 50, 0), (5, 10, 0), (29, 10, 0), (30, 10, 8), (51, 10, 8), (52, 10, 0), (59, 10, 0),
])
def test_baseline_boundary_minutes(t, pool_size, batch_conns):
    minute = replay(_model())[t]
    assert minute["pool_size"] == pool_size and minute["batch_conns"] == batch_conns


def test_baseline_timeline():
    model = _model()
    timeline = replay(model)
    assert _series(timeline, "pool_size") == BASELINE_POOL
    assert _series(timeline, "batch_conns") == BASELINE_BATCH
    for param in ("conn_hold_ms", "timeout_ms", "retry_max"):
        assert _series(timeline, param) == [model.params[param]] * 60


def test_i1_set_param_wins_over_the_later_pool_cut():
    timeline = replay(_model(), _actions("I1"))
    assert _series(timeline, "pool_size") == [50] * 60
    assert _series(timeline, "batch_conns") == BASELINE_BATCH


def test_i2_moves_the_whole_batch_job_out_of_the_window():
    timeline = replay(_model(), _actions("I2"))
    assert get_intervention("I2").action.value == -720
    assert _series(timeline, "batch_conns") == [0] * 60
    assert _series(timeline, "pool_size") == BASELINE_POOL


def test_shift_pairing_matches_the_job_identity_in_events():
    # The job's start and end share attributes.job in events.json; the replay pairs them by revert value.
    jobs = {e.id: e.attributes.get("job") for e in load_events(INCIDENT)}
    assert jobs["E-004"] == jobs["E-009"] == "settlement-reconcile"
    shifted = replay(_model(), [InterventionAction(op="shift_event", target="E-004", value=5)])
    assert _series(shifted, "batch_conns") == _batch(35, 57)


def test_shift_past_the_window_end_drops_the_changes_that_leave_it():
    shifted = replay(_model(), [InterventionAction(op="shift_event", target="E-004", value=10)])
    assert _series(shifted, "batch_conns") == _batch(40, 60)


def test_shift_before_the_window_applies_earlier_changes_before_minute_0():
    shifted = replay(_model(), [InterventionAction(op="shift_event", target="E-004", value=-40)])
    assert _series(shifted, "batch_conns") == _batch(0, 12)


def test_shift_without_a_revert_moves_only_the_target():
    # E-001 cuts the pool and nothing restores it, so only the cut moves.
    shifted = replay(_model(), [InterventionAction(op="shift_event", target="E-001", value=10)])
    assert _series(shifted, "pool_size") == [50 if t < 15 else 10 for t in MINUTES]
    assert _series(shifted, "batch_conns") == BASELINE_BATCH


def test_i3_caps_retry_max_and_leaves_the_rest():
    model = _model()
    timeline = replay(model, _actions("I3"))
    assert _series(timeline, "retry_max") == [1] * 60
    assert _series(timeline, "pool_size") == BASELINE_POOL
    assert _series(timeline, "batch_conns") == BASELINE_BATCH


def test_cap_above_the_current_value_changes_nothing():
    timeline = replay(_model(), [InterventionAction(op="cap_param", target="retry_max", value=5)])
    assert _series(timeline, "retry_max") == [3] * 60


def test_i4_blocks_the_pool_cut():
    timeline = replay(_model(), _actions("I4"))
    assert _series(timeline, "pool_size") == [50] * 60
    assert _series(timeline, "batch_conns") == BASELINE_BATCH


def test_block_event_removes_the_batch_job_start_only():
    timeline = replay(_model(), [InterventionAction(op="block_event", target="E-004")])
    assert _series(timeline, "batch_conns") == [0] * 60


def test_i5_matches_the_baseline_because_the_deploy_changes_no_param():
    model = _model()
    assert replay(model, _actions("I5")) == replay(model)


def test_i1_plus_i3_applies_both_in_either_order():
    model = _model()
    combined = replay(model, _actions("I1", "I3"))
    assert _series(combined, "pool_size") == [50] * 60
    assert _series(combined, "retry_max") == [1] * 60
    assert _series(combined, "batch_conns") == BASELINE_BATCH
    assert replay(model, _actions("I3", "I1")) == combined


def test_set_and_cap_on_one_param_apply_in_action_order():
    set_50 = InterventionAction(op="set_param", target="pool_size", value=50)
    cap_20 = InterventionAction(op="cap_param", target="pool_size", value=20)
    assert _series(replay(_model(), [set_50, cap_20]), "pool_size") == [20] * 60
    assert _series(replay(_model(), [cap_20, set_50]), "pool_size") == [50] * 60


def test_replay_is_deterministic():
    model = _model()
    actions = _actions("I1", "I2", "I3")
    assert replay(model, actions) == replay(model, actions)


def test_minutes_are_independent_dicts():
    timeline = replay(_model())
    timeline[0]["pool_size"] = 999
    assert timeline[1]["pool_size"] == 50


def test_inputs_are_not_mutated():
    model = _model()
    interventions = [get_intervention(i.id) for i in CATALOGUE]
    model_before = model.model_dump()
    interventions_before = [i.model_dump() for i in interventions]
    for intervention in interventions:
        replay(model, [intervention.action])
    replay(model, [i.action for i in interventions])
    assert model.model_dump() == model_before
    assert [i.model_dump() for i in interventions] == interventions_before
    assert model == _model()


@pytest.mark.parametrize("op", ["set_param", "cap_param"])
def test_unknown_param_raises(op):
    with pytest.raises(KeyError, match="unknown param: pool_sise"):
        replay(_model(), [InterventionAction(op=op, target="pool_sise", value=1)])


@pytest.mark.parametrize("action, message", [
    (InterventionAction(op="set_param", target="pool_size"), "needs a value"),
    (InterventionAction(op="cap_param", target="retry_max", value="one"), "numeric value"),
    (InterventionAction(op="shift_event", target="E-004"), "needs a value"),
    (InterventionAction(op="shift_event", target="E-004", value=1.5), "whole number of minutes"),
])
def test_malformed_action_values_raise(action, message):
    with pytest.raises(ValueError, match=message):
        replay(_model(), [action])


@pytest.mark.parametrize("op, value", [("block_event", None), ("shift_event", 10)])
def test_event_without_a_param_change_is_a_documented_no_op(op, value):
    model = _model()
    assert replay(model, [InterventionAction(op=op, target="E-404", value=value)]) == replay(model)


def test_catalogue_event_targets_exist_in_the_incident():
    # Event ids outside param_changes are no-ops in replay, so typos are caught here instead.
    event_ids = {e.id for e in load_events(INCIDENT)}
    targets = {i.action.target for i in CATALOGUE if i.action.op in ("block_event", "shift_event")}
    assert targets <= event_ids
