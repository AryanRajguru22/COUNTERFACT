"""H15: in-memory execution, verification from applied_changes, and the +20% demand stress run."""

import pytest

from contracts.models import ExecutionResult, Intervention, InterventionAction, SystemModel
from simulation import execute, get_intervention, load_system_model, simulate, verify
from simulation.executor import apply_changes
from simulation.interventions import CATALOGUE
from simulation.replay import replay
from simulation.verify import STRESS_DEMAND_FACTOR, stress_variant

INCIDENT = "INC-2041"


def _model() -> SystemModel:
    return load_system_model(INCIDENT)


def _action(op: str, target: str, value=None) -> InterventionAction:
    return InterventionAction(op=op, target=target, value=value)


def _intervention(action: InterventionAction, id_: str = "X") -> Intervention:
    return Intervention(id=id_, title="what-if", category="config", risk="low", effort_hours=0, rationale="test",
                        action=action)


def _verify(intervention_id: str):
    model = _model()
    return verify(execute(get_intervention(intervention_id), model), model, seed=0)


def _check(result, prefix: str):
    return next(c for c in result.checks if c.name.startswith(prefix))


# ---------------------------------------------------------------- execution


def test_execute_reports_exactly_the_applied_action():
    intervention = get_intervention("I1")
    execution = execute(intervention, _model())
    assert execution.status == "applied" and execution.intervention_id == "I1"
    assert execution.applied_changes == [intervention.action]
    execution.applied_changes[0].value = 1
    assert intervention.action.value == 50  # an independent copy


@pytest.mark.parametrize("action", [
    _action("set_param", "pool_sise", 50),  # unknown param
    _action("set_param", "pool_size"),  # no value
    _action("cap_param", "retry_max", "one"),  # non-numeric cap
    _action("shift_event", "E-004", 1.5),  # not a whole number of minutes
])
def test_invalid_actions_fail_without_claiming_success(action):
    model = _model()
    before = model.model_dump()
    execution = execute(_intervention(action), model)
    assert execution.status == "failed" and execution.applied_changes == []
    assert model.model_dump() == before


def test_set_param_pins_the_param_on_the_copy():
    changed = apply_changes(_model(), [get_intervention("I1").action])
    assert changed.params["pool_size"] == 50
    assert all(c.param != "pool_size" for c in changed.param_changes)


def test_cap_param_caps_the_param_and_its_changes():
    changed = apply_changes(_model(), [_action("cap_param", "batch_conns", 4)])
    assert [c.value for c in changed.param_changes if c.param == "batch_conns"] == [4, 0]
    assert apply_changes(_model(), [get_intervention("I3").action]).params["retry_max"] == 1


def test_block_event_removes_its_change():
    changed = apply_changes(_model(), [get_intervention("I4").action])
    assert [c.event_id for c in changed.param_changes] == ["E-004", "E-009"]


def test_shift_event_moves_the_job_with_its_end():
    changed = apply_changes(_model(), [get_intervention("I2").action])
    assert {c.event_id: c.t for c in changed.param_changes} == {"E-001": 5, "E-004": -690, "E-009": -668}


def test_event_without_a_param_change_leaves_the_model_as_it_was():
    model = _model()
    assert apply_changes(model, [get_intervention("I5").action]) == model


def test_apply_changes_returns_an_independent_copy_and_leaves_the_input_alone():
    model = _model()
    before = model.model_dump()
    changed = apply_changes(model, [get_intervention("I1").action, get_intervention("I3").action])
    changed.params["pool_size"] = 999
    changed.param_changes[0].t = 999
    changed.exogenous.demand_rps[0] = 999.0
    assert model.model_dump() == before


@pytest.mark.parametrize("actions", [
    *([i.action] for i in CATALOGUE),
    [_action("set_param", "pool_size", 50), _action("cap_param", "retry_max", 1)],
    [_action("shift_event", "E-004", 5), _action("cap_param", "retry_max", 1)],
    [_action("set_param", "pool_size", 50), _action("cap_param", "pool_size", 20)],
    [_action("cap_param", "pool_size", 20), _action("set_param", "pool_size", 50)],
])
def test_changed_model_replays_like_the_actions(actions):
    model = _model()
    assert replay(apply_changes(model, actions)) == replay(model, actions)


# ---------------------------------------------------------------- verification


@pytest.mark.parametrize("intervention_id", ["I1", "I2", "I4"])
def test_preventing_interventions_pass_verification_and_stress(intervention_id):
    result = _verify(intervention_id)
    assert result.passed and result.stress_test_passed
    assert [c.passed for c in result.checks] == [True, True, True]
    assert _check(result, "breach minutes").observed == "0"


def test_i3_is_reported_as_reducing_but_not_preventing_the_breach():
    result = _verify("I3")
    assert not result.passed and not result.stress_test_passed
    assert _check(result, "breach minutes").observed == "20"  # down from 22, still above the SLO
    peak = _check(result, "peak error rate")
    assert (peak.expected, peak.observed) == ("<= 5.0%", "18.9%")  # presentation only: no raw float in the text


def test_i5_rollback_fails_like_the_baseline():
    result, baseline = _verify("I5"), simulate(_model(), [])
    assert not result.passed
    assert _check(result, "breach minutes").observed == str(baseline.breach_minutes)


def test_verification_follows_applied_changes_not_the_catalogue():
    # The record says I3, but what actually ran was I1's pool fix, so the pool fix is what gets verified.
    model = _model()
    executed = ExecutionResult(intervention_id="I3", applied_changes=[get_intervention("I1").action], status="applied")
    result = verify(executed, model, seed=0)
    assert result.intervention_id == "I3" and result.passed
    nothing = ExecutionResult(intervention_id="I1", applied_changes=[], status="applied")
    assert not verify(nothing, model, seed=0).passed  # no changes: the baseline is verified, and fails


def test_verification_does_not_look_up_the_catalogue(monkeypatch):
    import simulation.interventions as catalogue
    monkeypatch.setattr(catalogue, "CATALOGUE", [])
    model = _model()
    executed = ExecutionResult(intervention_id="gone", applied_changes=[_action("set_param", "pool_size", 50)],
                               status="applied")
    assert verify(executed, model, seed=0).passed


def test_combined_changes_are_verified_together():
    model = _model()
    executed = ExecutionResult(intervention_id="I1+I3", status="applied",
                               applied_changes=[get_intervention("I1").action, get_intervention("I3").action])
    assert verify(executed, model, seed=0).passed


def test_failed_execution_fails_verification():
    model = _model()
    result = verify(ExecutionResult(intervention_id="I1", applied_changes=[], status="failed"), model, seed=0)
    assert not result.passed and not result.stress_test_passed
    assert result.checks[0].name == "execution applied" and result.checks[0].observed == "failed"


def test_invalid_applied_changes_fail_verification():
    model = _model()
    bogus = ExecutionResult(intervention_id="X", applied_changes=[_action("set_param", "pool_sise", 50)],
                            status="applied")
    result = verify(bogus, model, seed=0)
    assert not result.passed and "unknown param: pool_sise" in result.checks[0].observed


def test_verification_is_deterministic_and_leaves_inputs_alone():
    model, intervention = _model(), get_intervention("I2")
    before = (model.model_dump(), intervention.model_dump())
    execution = execute(intervention, model)
    execution_before = execution.model_dump()
    assert verify(execution, model, seed=0) == verify(execution, model, seed=0)
    assert (model.model_dump(), intervention.model_dump()) == before
    assert execution.model_dump() == execution_before


# ---------------------------------------------------------------- stress


def test_stress_variant_scales_every_minute_by_exactly_20_percent():
    model = _model()
    demand = list(model.exogenous.demand_rps)
    stressed = stress_variant(model)
    assert STRESS_DEMAND_FACTOR == 1.2
    assert stressed.exogenous.demand_rps == [rps * 1.2 for rps in demand]
    assert model.exogenous.demand_rps == demand
    assert stressed.params == model.params and stressed.param_changes == model.param_changes


def test_baseline_under_stress_breaches_longer_and_never_recovers():
    model = _model()
    normal, stressed = simulate(model, []), simulate(stress_variant(model), [])
    assert stressed.breach_minutes == 30 and normal.breach_minutes == 22
    breach = [t for t, e in enumerate(stressed.series.error_rate) if e > model.slo.max_error_rate]
    assert breach == list(range(30, 60))  # the storm outlives the batch job at +20% demand
    assert stressed.peak_error_rate > normal.peak_error_rate


def test_stress_check_reports_the_second_simulation():
    model = _model()
    for intervention in CATALOGUE:
        changed = apply_changes(model, [intervention.action])
        expected = simulate(stress_variant(changed), [], seed=0).breach_minutes
        result = verify(execute(intervention, model), model, seed=0)
        stress = _check(result, "breach minutes at +20% demand")
        assert stress.observed == str(expected)
        assert result.stress_test_passed == stress.passed == (expected <= model.slo.max_breach_minutes)


def test_stress_can_fail_where_the_normal_replay_passes():
    # Without the batch job, 9 connections carry the incident's ~8.2 erlangs, but not +20% (~9.8 erlangs).
    model = _model()
    executed = ExecutionResult(intervention_id="X", status="applied",
                               applied_changes=[_action("set_param", "pool_size", 9), _action("block_event", "E-004")])
    result = verify(executed, model, seed=0)
    assert [c.passed for c in result.checks] == [True, True, False]
    assert not result.stress_test_passed and not result.passed
    assert _check(result, "breach minutes at +20% demand").observed == "60"
