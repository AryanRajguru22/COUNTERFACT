"""H9: the queue / timeout / retry simulator, driven by the H6 replay timeline."""

import pytest

from contracts.models import Intervention, InterventionAction, SystemModel
from simulation import get_intervention, load_system_model, simulate
from simulation.interventions import CATALOGUE
from simulation.simulator import _mmc_timeout

INCIDENT = "INC-2041"
BATCH = range(30, 52)  # batch job holds connections (E-004 .. E-009)
QUIET = range(5, 30)  # pool already cut to 10, no batch job yet


def _model() -> SystemModel:
    return load_system_model(INCIDENT)


def _run(*ids: str, model: SystemModel | None = None, seed: int = 0):
    return simulate(model or _model(), [get_intervention(i) for i in ids], seed=seed)


def _what_if(op: str, target: str, value=None) -> Intervention:
    return Intervention(id="X", title="what-if", category="config", risk="low", effort_hours=0, rationale="test",
                        action=InterventionAction(op=op, target=target, value=value))


def _breach_window(result) -> list[int]:
    return [t for t, e in enumerate(result.series.error_rate) if e > 0.05]


# ---------------------------------------------------------------- calibration and contract


def test_baseline_is_calibrated_to_the_observed_incident():
    baseline = _run()
    assert abs(baseline.breach_minutes - 22) <= 3
    assert abs(baseline.peak_error_rate - 0.38) <= 0.05
    assert not baseline.prevented and baseline.intervention_ids == []


def test_baseline_breach_falls_inside_the_batch_job_and_its_retry_tail():
    window = _breach_window(_run())
    assert window[0] >= BATCH.start and window[-1] <= BATCH.stop + 3


def test_every_series_covers_the_demand_window():
    model = _model()
    series = _run(model=model).series
    assert len(series.error_rate) == len(series.pool_wait_ms) == len(series.inflight) == 60
    assert len(model.exogenous.demand_rps) == 60


def test_summary_fields_follow_the_series_and_the_slo():
    model = _model()
    for intervention in [[]] + [[i.id] for i in CATALOGUE]:
        result = _run(*intervention, model=model)
        assert result.peak_error_rate == max(result.series.error_rate)
        assert result.breach_minutes == sum(1 for e in result.series.error_rate if e > model.slo.max_error_rate)
        assert result.prevented == (result.breach_minutes <= model.slo.max_breach_minutes)


def test_error_rates_are_probabilities_and_waits_stay_within_the_timeout():
    series = _run().series
    assert all(0 <= e <= 1 for e in series.error_rate)
    assert all(0 <= w <= 2000 for w in series.pool_wait_ms)
    assert all(n >= 0 for n in series.inflight)


# ---------------------------------------------------------------- determinism


def test_repeated_runs_are_identical():
    assert _run() == _run()
    assert _run("I1", "I3") == _run("I1", "I3")


def test_same_seed_gives_the_same_result():
    assert _run("I3", seed=7) == _run("I3", seed=7)


def test_the_model_has_no_noise_so_the_seed_is_only_recorded():
    a, b = _run("I3", seed=1), _run("I3", seed=2)
    assert (a.seed, b.seed) == (1, 2)
    assert a.series == b.series and a.breach_minutes == b.breach_minutes


def test_inputs_are_not_mutated():
    model = _model()
    interventions = [get_intervention(i.id) for i in CATALOGUE]
    model_before, interventions_before = model.model_dump(), [i.model_dump() for i in interventions]
    simulate(model, interventions)
    for intervention in interventions:
        simulate(model, [intervention])
    assert model.model_dump() == model_before
    assert [i.model_dump() for i in interventions] == interventions_before


# ---------------------------------------------------------------- the catalogue


@pytest.mark.parametrize("intervention_id", ["I1", "I2", "I4"])
def test_capacity_fixes_prevent_the_breach(intervention_id):
    result = _run(intervention_id)
    assert result.prevented and result.breach_minutes == 0
    assert result.peak_error_rate < 0.01


def test_i3_cuts_the_retry_storm_but_does_not_prevent_the_breach():
    baseline, capped = _run(), _run("I3")
    assert not capped.prevented
    assert 0 < capped.breach_minutes < baseline.breach_minutes
    assert capped.peak_error_rate < baseline.peak_error_rate / 1.5


def test_i5_rollback_matches_the_baseline():
    baseline, rolled_back = _run(), _run("I5")
    assert rolled_back.series == baseline.series
    assert rolled_back.breach_minutes == baseline.breach_minutes and not rolled_back.prevented


# ---------------------------------------------------------------- physics


def test_replay_actions_drive_the_simulation():
    baseline = _breach_window(_run())
    blocked = simulate(_model(), [_what_if("block_event", "E-004")])
    assert blocked.prevented
    later = _breach_window(simulate(_model(), [_what_if("shift_event", "E-004", 5)]))
    assert later[0] == baseline[0] + 5
    smaller_pool = simulate(_model(), [_what_if("set_param", "pool_size", 9)])
    assert smaller_pool.breach_minutes > _run().breach_minutes


def test_pool_pressure_drives_pool_wait():
    baseline = _run().series.pool_wait_ms
    roomy = _run("I1").series.pool_wait_ms
    assert max(baseline[t] for t in QUIET) < 50  # 10 connections for ~8 erlangs: short queue
    assert min(baseline[t] for t in BATCH[2:]) > 1500  # queue sits near the 2000 ms timeout
    assert max(roomy) < 1  # 50 connections: no queue
    assert all(baseline[t] > roomy[t] for t in BATCH)


def test_timeout_turns_waiting_into_errors():
    baseline = _run().series.error_rate
    impatient = simulate(_model(), [_what_if("set_param", "timeout_ms", 20)]).series.error_rate
    assert max(baseline[t] for t in QUIET) < 1e-6
    assert min(impatient[t] for t in QUIET) > 0.05  # same queue, but waits beyond 20 ms now fail


def test_retries_feed_back_into_demand():
    baseline = _run().series
    no_retries = simulate(_model(), [_what_if("cap_param", "retry_max", 0)]).series
    assert max(no_retries.error_rate) < max(_run("I3").series.error_rate) < max(baseline.error_rate)
    assert all(baseline.inflight[t] >= no_retries.inflight[t] for t in BATCH)
    assert baseline.error_rate[40] > 3 * baseline.error_rate[31]  # the storm builds over minutes


def test_storm_drains_after_the_batch_job_ends():
    error_rate = _run().series.error_rate
    assert all(e < 0.01 for e in error_rate[BATCH.stop + 3:])


def test_combinations_go_through_replay_not_ids():
    assert _run("I1", "I3").prevented
    assert _run("I3", "I5").series == _run("I3").series
    assert _run("I2", "I3").series == _run("I3", "I2").series


def test_calibration_constant_can_be_overridden_by_a_param():
    model = _model()
    heavier = model.model_copy(update={"params": {**model.params, "batch_conn_duty": 0.5}})
    assert simulate(heavier, []).peak_error_rate > _run().peak_error_rate


# ---------------------------------------------------------------- queue formula


def test_queue_matches_the_fluid_limit_in_heavy_overload():
    timed_out, wait = _mmc_timeout(2, 8.0, 25.0)  # 2 connections, 8 erlangs, 25 holds of patience
    assert timed_out == pytest.approx(0.75, abs=1e-6)
    assert 24 < wait <= 25


def test_queue_is_continuous_at_full_load():
    below, at, above = (_mmc_timeout(8, a, 25.0)[0] for a in (8 - 1e-4, 8.0, 8 + 1e-4))
    assert below == pytest.approx(at, abs=1e-3) and above == pytest.approx(at, abs=1e-3)


def test_no_connections_means_every_attempt_times_out():
    assert _mmc_timeout(0, 8.0, 25.0) == (1.0, 25.0)
