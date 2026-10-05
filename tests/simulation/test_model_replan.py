"""H18: replan re-simulates and re-ranks the remaining candidates against the model."""

from contracts.models import (CausalLink, RankedIntervention, RootCause, SystemModel, VerificationCheck,
                              VerificationResult)
from simulation import (execute, generate_interventions, get_intervention, load_system_model, rank, replan, simulate,
                        verify)
from simulation.interventions import CATALOGUE
from simulation.verify import stress_variant

INCIDENT = "INC-2041"
MAX_ATTEMPTS = 3  # agent/orchestrator.py; the cap lives there, replan only has to shrink the ranking


def _model() -> SystemModel:
    return load_system_model(INCIDENT)


def _ranking(model: SystemModel, root_cause: RootCause | None = None) -> list[RankedIntervention]:
    if root_cause is None:
        interventions = [get_intervention(i.id) for i in CATALOGUE]
    else:
        interventions = generate_interventions(root_cause, model)
    return rank([simulate(model, [])] + [simulate(model, [i]) for i in interventions], interventions)


def _failed(intervention_id: str) -> VerificationResult:
    return VerificationResult(intervention_id=intervention_id, passed=False, stress_test_passed=False,
                              checks=[VerificationCheck(name="human approval", expected="approved",
                                                        observed="rejected", passed=False)])


def _ids(ranking: list[RankedIntervention]) -> list[str]:
    return [r.intervention_id for r in ranking]


def test_replan_after_i3_fails_verification():
    model = _model()
    verification = verify(execute(get_intervention("I3"), model), model, seed=0)
    assert not verification.passed
    replanned = replan(verification, _ranking(model), model)
    assert _ids(replanned) == ["I1", "I2", "I4", "I5"]
    assert [r.rank for r in replanned] == [1, 2, 3, 4]
    assert "I3" not in _ids(replanned)


def test_replan_matches_a_fresh_simulation_and_ranking_of_the_remaining_candidates():
    model = _model()
    remaining = [get_intervention(i) for i in ("I2", "I3", "I4", "I5")]
    fresh = rank([simulate(model, [])] + [simulate(model, [i]) for i in remaining], remaining)
    assert replan(_failed("I1"), _ranking(model), model) == fresh


def test_stale_scores_and_outcomes_in_the_ranking_are_not_trusted():
    # A ranking that claims I5 prevents the breach with a top score is re-simulated, not believed.
    model = _model()
    forged = [RankedIntervention(intervention_id="I5", rank=1, score=100.0, prevented=True, breach_minutes_avoided=22),
              RankedIntervention(intervention_id="I3", rank=2, score=50.0, prevented=True, breach_minutes_avoided=22),
              RankedIntervention(intervention_id="I2", rank=3, score=-9.0, prevented=False, breach_minutes_avoided=0)]
    replanned = replan(_failed("I1"), forged, model)
    assert _ids(replanned) == ["I2", "I5", "I3"]
    by_id = {r.intervention_id: r for r in replanned}
    assert by_id["I2"].prevented and by_id["I2"].score == 21.75
    assert not by_id["I5"].prevented and by_id["I5"].breach_minutes_avoided == 0


def test_replan_follows_the_model_it_is_given_not_the_old_order():
    # If the pool had been cut to 8, moving the batch job (I2) would no longer prevent the breach. Deleting I1
    # from the old ranking would recommend I2 next; re-simulating recommends I4, which still prevents it.
    model = _model()
    tighter = model.model_copy(update={"param_changes": [c.model_copy(update={"value": 8}) if c.event_id == "E-001"
                                                         else c for c in model.param_changes]})
    old = _ranking(model)
    deleted = [r.intervention_id for r in old if r.intervention_id != "I1"]
    replanned = replan(_failed("I1"), old, tighter)
    assert deleted[0] == "I2"
    assert _ids(replanned)[0] == "I4" and replanned[0].prevented
    assert not next(r for r in replanned if r.intervention_id == "I2").prevented


def test_scores_reflect_the_model_state():
    model = _model()
    normal = {r.intervention_id: r for r in replan(_failed("I1"), _ranking(model), model)}
    stressed = {r.intervention_id: r for r in replan(_failed("I1"), _ranking(model), stress_variant(model))}
    assert normal["I2"].breach_minutes_avoided == 22 and stressed["I2"].breach_minutes_avoided == 30
    assert stressed["I3"].score != normal["I3"].score


def test_root_cause_filtering_is_kept():
    # A pool-cut-only root cause never offered I2, so replan must not bring it back.
    model = _model()
    root_cause = RootCause(hypothesis_id="HX", statement="test", confidence=0.5,
                           causal_chain=[CausalLink(event_id="E-001", effect="test")])
    initial = _ranking(model, root_cause)
    assert _ids(initial) == ["I1", "I4", "I5", "I3"]
    assert _ids(replan(_failed("I1"), initial, model)) == ["I4", "I5", "I3"]


def test_failed_intervention_never_comes_back_and_ids_stay_unique():
    model = _model()
    doubled = _ranking(model) + _ranking(model)
    replanned = replan(_failed("I1"), doubled, model)
    assert "I1" not in _ids(replanned)
    assert len(_ids(replanned)) == len(set(_ids(replanned))) == 4


def test_repeated_replans_shrink_until_nothing_is_left():
    model = _model()
    ranking, recommended = _ranking(model), []
    for _ in range(len(CATALOGUE)):
        recommended.append(ranking[0].intervention_id)
        ranking = replan(_failed(ranking[0].intervention_id), ranking, model)
    assert recommended == ["I1", "I2", "I4", "I5", "I3"]  # each one recommended once, in ranked order
    assert ranking == []
    assert len(recommended) > MAX_ATTEMPTS  # the orchestrator's cap, not replan, ends the loop sooner


def test_no_candidates_left_gives_an_empty_ranking():
    model = _model()
    only = [r for r in _ranking(model) if r.intervention_id == "I3"]
    assert replan(_failed("I3"), only, model) == []
    assert replan(_failed("I3"), [], model) == []


def test_replan_is_deterministic():
    model = _model()
    ranking = _ranking(model)
    assert replan(_failed("I3"), ranking, model) == replan(_failed("I3"), ranking, model)


def test_replan_leaves_its_inputs_alone():
    model = _model()
    ranking, failed = _ranking(model), _failed("I3")
    before = (model.model_dump(), [r.model_dump() for r in ranking], failed.model_dump())
    catalogue_before = [i.model_dump() for i in CATALOGUE]
    replan(failed, ranking, model)
    assert (model.model_dump(), [r.model_dump() for r in ranking], failed.model_dump()) == before
    assert [i.model_dump() for i in CATALOGUE] == catalogue_before


def test_a_failed_verification_leaves_the_model_clean_for_replan():
    # Verification works on a copy, so the replan baseline is still the incident's, not I3's.
    model = _model()
    before = model.model_dump()
    verify(execute(get_intervention("I3"), model), model, seed=0)
    assert model.model_dump() == before
    replanned = replan(_failed("I3"), _ranking(model), model)
    assert next(r for r in replanned if r.intervention_id == "I1").breach_minutes_avoided == 22
