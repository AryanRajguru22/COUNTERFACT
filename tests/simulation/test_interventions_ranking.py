"""H12: root-cause-aware intervention generation and the ranking formula."""

import pytest

from contracts.models import CausalLink, RootCause, SimSeries, SimulationResult
from data.loader import load_events
from evidence import build_timeline, determine_root_cause, gather_evidence, seed_hypotheses, test_hypothesis
from simulation import generate_interventions, get_intervention, load_system_model, rank, simulate
from simulation.interventions import CATALOGUE
from simulation.ranking import EFFORT_PENALTY_PER_HOUR, RISK_PENALTY

INCIDENT = "INC-2041"


def _root_cause() -> RootCause:
    timeline = build_timeline(INCIDENT)
    hypotheses = seed_hypotheses(INCIDENT, timeline)
    evidence = [e for h in hypotheses for e in gather_evidence(INCIDENT, h)]
    tested = [test_hypothesis(h, [e for e in evidence if h.id in e.stance]) for h in hypotheses]
    return determine_root_cause(tested, evidence, timeline)


def _chain(*event_ids: str) -> RootCause:
    return RootCause(hypothesis_id="HX", statement="test", confidence=0.5,
                     causal_chain=[CausalLink(event_id=e, effect="test") for e in event_ids])


def _ids(root_cause: RootCause) -> list[str]:
    return [i.id for i in generate_interventions(root_cause, load_system_model(INCIDENT))]


def _result(ids: list[str], breach_minutes: int, peak: float = 0.0) -> SimulationResult:
    return SimulationResult(intervention_ids=ids, seed=0, series=SimSeries(error_rate=[], pool_wait_ms=[], inflight=[]),
                            peak_error_rate=peak, breach_minutes=breach_minutes, prevented=breach_minutes == 0)


def _incident_ranking():
    model = load_system_model(INCIDENT)
    interventions = generate_interventions(_root_cause(), model)
    results = [simulate(model, [])] + [simulate(model, [i]) for i in interventions]
    return rank(results, interventions), interventions


# ---------------------------------------------------------------- catalogue


def test_catalogue_entries_are_valid_and_unique():
    assert [i.id for i in CATALOGUE] == ["I1", "I2", "I3", "I4", "I5"]
    event_ids = {e.id for e in load_events(INCIDENT)}
    params = set(load_system_model(INCIDENT).params)
    for intervention in CATALOGUE:
        action = intervention.action
        assert action.target in (event_ids if action.op in ("block_event", "shift_event") else params)


def test_incident_root_cause_gets_the_whole_catalogue_in_order():
    root_cause = _root_cause()
    assert root_cause.hypothesis_id == "H1"
    assert _ids(root_cause) == ["I1", "I2", "I3", "I4", "I5"]


@pytest.mark.parametrize("chain, expected", [
    (("E-001",), ["I1", "I3", "I4", "I5"]),  # pool cut only: no batch job to move
    (("E-004", "E-009"), ["I1", "I2", "I3", "I5"]),  # batch contention only: the pool cut is not on the path
    (("E-002",), ["I5"]),  # a v2.4.1 regression: only the rollback addresses it
])
def test_root_cause_chain_selects_the_interventions_that_address_it(chain, expected):
    assert _ids(_chain(*chain)) == expected


@pytest.mark.parametrize("chain", [("E-003",), ("E-404",), ()])
def test_root_cause_no_entry_addresses_gets_no_interventions(chain):
    # Gateway degradation, unknown event or an empty chain: the rollback control is not offered on its own.
    assert _ids(_chain(*chain)) == []


def test_generation_is_deterministic_and_returns_copies():
    root_cause, model = _root_cause(), load_system_model(INCIDENT)
    catalogue_before = [i.model_dump() for i in CATALOGUE]
    first = generate_interventions(root_cause, model)
    first[0].action.value = 999
    assert generate_interventions(root_cause, model) == generate_interventions(root_cause, model)
    assert [i.model_dump() for i in CATALOGUE] == catalogue_before
    assert get_intervention("I1").action.value == 50


def test_generation_does_not_mutate_its_inputs():
    root_cause, model = _root_cause(), load_system_model(INCIDENT)
    before = (root_cause.model_dump(), model.model_dump())
    generate_interventions(root_cause, model)
    assert (root_cause.model_dump(), model.model_dump()) == before


# ---------------------------------------------------------------- ranking


def _score(result: SimulationResult, baseline_breach: int) -> float:
    intervention = get_intervention(result.intervention_ids[0])
    avoided = baseline_breach - result.breach_minutes
    return round(avoided - RISK_PENALTY[intervention.risk] - EFFORT_PENALTY_PER_HOUR * intervention.effort_hours, 2)


def test_incident_ranking_order():
    ranking, _ = _incident_ranking()
    assert [r.intervention_id for r in ranking] == ["I1", "I2", "I4", "I5", "I3"]
    assert [r.rank for r in ranking] == [1, 2, 3, 4, 5]
    assert [r.prevented for r in ranking] == [True, True, True, False, False]


def test_scores_follow_the_formula():
    model = load_system_model(INCIDENT)
    baseline = simulate(model, [])
    ranking, interventions = _incident_ranking()
    for entry in ranking:
        result = simulate(model, [get_intervention(entry.intervention_id)])
        assert entry.score == _score(result, baseline.breach_minutes)
        assert entry.breach_minutes_avoided == baseline.breach_minutes - result.breach_minutes
    assert {r.intervention_id: r.score for r in ranking} == {"I1": 21.88, "I2": 21.75, "I4": 20.0, "I5": -0.12,
                                                              "I3": -2.0}


def test_i3_improves_on_the_baseline_but_its_cost_ranks_it_below_the_i5_no_op():
    # The formula scores breach minutes, not peak error. I3 halves the peak but saves only 2 of 22 minutes,
    # which does not cover its med-risk (3) and 2 h effort (1) penalties. I5 saves nothing and costs ~0.
    ranking, _ = _incident_ranking()
    by_id = {r.intervention_id: r for r in ranking}
    assert by_id["I3"].breach_minutes_avoided > 0 and not by_id["I3"].prevented
    assert by_id["I5"].breach_minutes_avoided == 0 and not by_id["I5"].prevented
    assert by_id["I3"].score == 2 - RISK_PENALTY["med"] - EFFORT_PENALTY_PER_HOUR * 2.0
    assert by_id["I5"].rank < by_id["I3"].rank


def test_prevention_outranks_any_score():
    interventions = [get_intervention("I3"), get_intervention("I4")]
    results = [_result([], 30), _result(["I3"], 1), _result(["I4"], 0)]
    # I3 saves 29 of 30 minutes (score 25). I4 prevents, but as high risk with 40 h effort it scores 2. It still leads.
    cheap = [i.model_copy(update={"risk": "high", "effort_hours": 40.0}) if i.id == "I4" else i for i in interventions]
    ranking = rank(results, cheap)
    assert [r.intervention_id for r in ranking] == ["I4", "I3"]
    assert ranking[0].score < ranking[1].score


def test_ties_break_by_intervention_id():
    twins = [get_intervention(i).model_copy(update={"risk": "low", "effort_hours": 1.0}) for i in ("I2", "I1")]
    results = [_result([], 10), _result(["I2"], 5), _result(["I1"], 5)]
    assert [r.intervention_id for r in rank(results, twins)] == ["I1", "I2"]


def test_ranking_is_deterministic_and_independent_of_input_order():
    model = load_system_model(INCIDENT)
    interventions = generate_interventions(_root_cause(), model)
    results = [simulate(model, [])] + [simulate(model, [i]) for i in interventions]
    assert rank(results, interventions) == rank(list(reversed(results)), list(reversed(interventions)))


def test_ranking_has_no_id_special_cases():
    # Relabel every intervention: the order follows outcomes and costs, not names.
    ranking, interventions = _incident_ranking()
    model = load_system_model(INCIDENT)
    relabel = {"I1": "Z9", "I2": "Z8", "I3": "Z7", "I4": "Z6", "I5": "Z5"}
    renamed = [i.model_copy(update={"id": relabel[i.id]}) for i in interventions]
    results = [simulate(model, [])] + [simulate(model, [i]).model_copy(update={"intervention_ids": [relabel[i.id]]})
                                       for i in interventions]
    assert [r.intervention_id for r in rank(results, renamed)] == [relabel[r.intervention_id] for r in ranking]


def test_combination_results_are_not_ranked_as_single_interventions():
    interventions = [get_intervention("I1"), get_intervention("I3")]
    results = [_result([], 22), _result(["I1", "I3"], 0), _result(["I3"], 20)]
    assert [r.intervention_id for r in rank(results, interventions)] == ["I3"]
