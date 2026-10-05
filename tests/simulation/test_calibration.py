"""H11: the INC-2041 baseline calibration (BATCH_CONN_DUTY) stays inside its acceptance envelope."""

import pytest

from contracts.models import SystemModel
from data.loader import load_metrics
from simulation import load_system_model, simulate
from simulation.simulator import BATCH_CONN_DUTY

INCIDENT = "INC-2041"
BREACH_MINUTES = (19, 25)  # 22 +/- 3
PEAK_ERROR_RATE = (0.33, 0.43)  # 0.38 +/- 0.05


def _model() -> SystemModel:
    return load_system_model(INCIDENT)


def _with_duty(duty: float) -> SystemModel:
    model = _model()
    return model.model_copy(update={"params": {**model.params, "batch_conn_duty": duty}})


def _window(error_rate) -> tuple[int, int]:
    breach = [t for t, e in enumerate(error_rate) if e > 0.05]
    return breach[0], breach[-1]


def _observed_error_rate() -> list[float]:
    series = next(m for m in load_metrics(INCIDENT) if m.name == "checkout_5xx_rate")
    return [p.value for p in series.points]


def _inside(result) -> bool:
    return (BREACH_MINUTES[0] <= result.breach_minutes <= BREACH_MINUTES[1]
            and PEAK_ERROR_RATE[0] <= result.peak_error_rate <= PEAK_ERROR_RATE[1])


def test_fixture_does_not_override_the_calibration_constant():
    assert "batch_conn_duty" not in _model().params  # so the baseline below really tests BATCH_CONN_DUTY


def test_baseline_is_inside_the_acceptance_envelope():
    baseline = simulate(_model(), [])
    assert BREACH_MINUTES[0] <= baseline.breach_minutes <= BREACH_MINUTES[1]
    assert PEAK_ERROR_RATE[0] <= baseline.peak_error_rate <= PEAK_ERROR_RATE[1]
    assert not baseline.prevented


def test_baseline_breach_window_matches_the_observed_incident():
    start, end = _window(simulate(_model(), []).series.error_rate)
    observed_start, observed_end = _window(_observed_error_rate())  # t=32..53 in metrics.json
    assert abs(start - observed_start) <= 2 and abs(end - observed_end) <= 2
    assert start > 30  # the batch job (E-004, t=30) starts the breach; nothing breaches before it


def test_baseline_tracks_the_observed_error_rate():
    simulated, observed = simulate(_model(), []).series.error_rate, _observed_error_rate()
    mean_abs_error = sum(abs(s - o) for s, o in zip(simulated, observed)) / len(observed)
    assert mean_abs_error < 0.04  # 0.029 at calibration; the model ramps up more slowly than observed


def test_calibrated_baseline_is_deterministic_and_leaves_the_model_alone():
    model = _model()
    before = model.model_dump()
    assert simulate(model, []) == simulate(model, [])
    assert model.model_dump() == before


def test_param_override_reproduces_the_constant():
    assert simulate(_with_duty(BATCH_CONN_DUTY), []).series == simulate(_model(), []).series


# ---------------------------------------------------------------- sensitivity


@pytest.mark.parametrize("duty, breach_minutes, peak_error_rate", [
    (0.25, 20, 0.307),
    (0.26, 22, 0.387),
    (0.27, 23, 0.437),
])
def test_sensitivity_around_the_selected_duty(duty, breach_minutes, peak_error_rate):
    result = simulate(_with_duty(duty), [])
    assert result.breach_minutes == breach_minutes
    assert result.peak_error_rate == pytest.approx(peak_error_rate, abs=0.001)


def test_selected_duty_is_inside_a_narrow_envelope():
    # Pool 10 sits right at the edge of ~8.2 erlangs of demand, so the peak moves ~0.04 per 0.01 of duty.
    # Both neighbours miss the peak band, which is why the value is pinned rather than approximate.
    below, selected, above = (simulate(_with_duty(d), []) for d in (0.25, BATCH_CONN_DUTY, 0.27))
    assert _inside(selected)
    assert below.peak_error_rate < PEAK_ERROR_RATE[0] and above.peak_error_rate > PEAK_ERROR_RATE[1]
    assert below.peak_error_rate < selected.peak_error_rate < above.peak_error_rate


@pytest.mark.parametrize("duty", [0.20, 0.24, 0.30, 0.50])
def test_miscalibrated_duty_leaves_the_envelope(duty):
    assert not _inside(simulate(_with_duty(duty), []))
