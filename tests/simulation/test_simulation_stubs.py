"""Simulation engine stubs honour the frozen signatures and return valid contract objects."""

from data.loader import load_ground_truth
from evidence import build_timeline, determine_root_cause, gather_evidence, seed_hypotheses, test_hypothesis
from simulation import execute, generate_interventions, load_system_model, rank, replan, simulate, verify

INCIDENT = "INC-2041"


def _setup():
    model = load_system_model(INCIDENT)
    timeline = build_timeline(INCIDENT)
    hypotheses = seed_hypotheses(INCIDENT, timeline)
    evidence = [e for h in hypotheses for e in gather_evidence(INCIDENT, h)]
    tested = [test_hypothesis(h, [e for e in evidence if h.id in e.stance]) for h in hypotheses]
    return model, generate_interventions(determine_root_cause(tested, evidence, timeline), model)


def _all_results(model, interventions):
    return [simulate(model, [], seed=0)] + [simulate(model, [i], seed=0) for i in interventions]


def test_interventions_are_i1_to_i5():
    _, interventions = _setup()
    assert [i.id for i in interventions] == ["I1", "I2", "I3", "I4", "I5"]


def test_baseline_breaches_and_series_cover_window():
    model, _ = _setup()
    baseline = simulate(model, [], seed=0)
    assert baseline.intervention_ids == [] and not baseline.prevented
    assert baseline.breach_minutes == 22
    assert len(baseline.series.error_rate) == len(model.exogenous.demand_rps)


def test_simulate_is_deterministic():
    model, interventions = _setup()
    assert simulate(model, interventions[:1], seed=0) == simulate(model, interventions[:1], seed=0)


def test_preventing_set_matches_ground_truth():
    model, interventions = _setup()
    prevented = {i.id for i in interventions if simulate(model, [i], seed=0).prevented}
    assert prevented == set(load_ground_truth(INCIDENT)["preventing_intervention_ids"])


def test_rank_puts_preventing_interventions_first():
    model, interventions = _setup()
    ranking = rank(_all_results(model, interventions), interventions)
    assert [r.rank for r in ranking] == [1, 2, 3, 4, 5]
    assert ranking[0].prevented
    assert ranking[-1].intervention_id == "I5" and ranking[-1].breach_minutes_avoided == 0


def test_execute_verify_and_replan():
    model, interventions = _setup()
    by_id = {i.id: i for i in interventions}
    good = verify(execute(by_id["I1"], model), model, seed=0)
    assert good.passed and good.stress_test_passed
    bad = verify(execute(by_id["I3"], model), model, seed=0)
    assert not bad.passed
    replanned = replan(bad, rank(_all_results(model, interventions), interventions), model)
    assert "I3" not in {r.intervention_id for r in replanned}
    assert [r.rank for r in replanned] == list(range(1, len(replanned) + 1))
