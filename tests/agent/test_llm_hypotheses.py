"""H18: LLM-origin hypotheses.

Part A: an LLM-origin hypothesis keeps the evidence the engine tags for it (stances are merged, not dropped).
Part B: with LLM_HYPOTHESES=1 the agent asks the LLM for up to 2 extra hypotheses, parsed defensively.

No network: the LLM is a spy or a faked endpoint; recordings are copied to a temp dir before anything writes.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from agent import llm, orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Hypothesis, Investigation

INCIDENT = "INC-2041"
THOUGHT_KEYS = ["thought.timeline", "thought.hypotheses", "thought.evidence", "thought.testing",
                "thought.root_cause", "thought.counterfactual", "thought.recommendation"]
POOL = ("Connection pool starvation", "The payment-svc connection pool ran out of free connections.")
RELEASE = ("Bad release", "A bug shipped in the latest deploy breaks payments.")
COSMIC = ("Cosmic rays", "Bit flips in memory corrupted requests.")


def _llm(hid: str, title: str, mechanism: str) -> Hypothesis:
    return Hypothesis(id=hid, title=title, mechanism=mechanism, origin="llm", status="proposed", confidence=0.25)


def _run(investigation_id: str = "inv-h18", mode: str = "replay") -> Investigation:
    store = InvestigationStore()
    store.put(Investigation(id=investigation_id, incident=tools.get_incident(INCIDENT), mode=mode))
    orchestrator.run(investigation_id, store)
    return store.get(investigation_id)


def _by_id(inv: Investigation) -> dict[str, Hypothesis]:
    return {h.id: h for h in inv.hypotheses}


def _seed_titles() -> list[str]:
    timeline = tools.call("build_timeline", incident_id=INCIDENT)
    return [h.title for h in tools.call("seed_hypotheses", incident_id=INCIDENT, timeline=timeline)]


# ================================================================ Part A: stance merging


@pytest.fixture
def inject(monkeypatch):
    """Append the given LLM-origin hypotheses to the seeds, as if the agent had proposed them."""
    def _inject(*extra: Hypothesis):
        seed = tools.TOOLS["seed_hypotheses"]
        monkeypatch.setitem(tools.TOOLS, "seed_hypotheses",
                            lambda incident_id, timeline: seed(incident_id, timeline) + [h.model_copy() for h in extra])
    return _inject


def test_pool_family_llm_hypothesis_gets_merged_evidence_and_is_supported(inject):
    inject(_llm("H5", *POOL))
    inv = _run()
    h1, h5 = _by_id(inv)["H1"], _by_id(inv)["H5"]
    assert h5.status == "supported" and h5.confidence == h1.confidence > 0
    assert sorted(h5.supporting_evidence_ids) == sorted(h1.supporting_evidence_ids)
    assert sum("H5" in e.stance for e in inv.evidence) == sum("H1" in e.stance for e in inv.evidence) > 0
    assert inv.root_cause.hypothesis_id == "H1"  # a tie with the seed goes to the lowest id


def test_regression_family_llm_hypothesis_is_rejected_like_its_seed(inject):
    inject(_llm("H5", *RELEASE))
    inv = _run()
    h2, h5 = _by_id(inv)["H2"], _by_id(inv)["H5"]
    assert h5.status == h2.status == "rejected"
    assert h5.confidence == h2.confidence and h5.rejection_reason
    assert any(s.kind == "decision" and s.output_summary.startswith("Rejected H5 Bad release:") for s in inv.steps)


def test_llm_hypothesis_matching_no_family_stays_proposed_and_the_run_continues(inject):
    inject(_llm("H5", *COSMIC))
    inv = _run()
    h5 = _by_id(inv)["H5"]
    assert h5.status == "proposed" and h5.confidence == 0
    assert not any("H5" in e.stance for e in inv.evidence)
    assert inv.stage == "awaiting_approval", inv.error


def test_seed_results_are_unchanged_by_llm_hypotheses(inject):
    baseline = _run("inv-base")
    inject(_llm("H5", *POOL), _llm("H6", *RELEASE), _llm("H7", *COSMIC))
    mixed = _run("inv-mixed")
    fields = ("status", "confidence", "supporting_evidence_ids", "refuting_evidence_ids", "tests", "rejection_reason")
    for hid in ("H1", "H2", "H3", "H4"):
        before, after = _by_id(baseline)[hid], _by_id(mixed)[hid]
        assert [getattr(before, f) for f in fields] == [getattr(after, f) for f in fields], hid
    assert [e.id for e in mixed.evidence] == [e.id for e in baseline.evidence]
    for b, m in zip(baseline.evidence, mixed.evidence):  # seed stances untouched by the merge
        assert {k: v for k, v in m.stance.items() if k in b.stance} == b.stance
    assert mixed.root_cause.hypothesis_id == baseline.root_cause.hypothesis_id == "H1"
    assert mixed.root_cause.causal_chain == baseline.root_cause.causal_chain
    assert mixed.recommendation == baseline.recommendation


def test_evidence_ids_stay_unique_and_carry_both_stances(inject):
    inject(_llm("H5", *POOL))
    inv = _run()
    ids = [e.id for e in inv.evidence]
    assert len(ids) == len(set(ids))
    shared = [e for e in inv.evidence if "H1" in e.stance and "H5" in e.stance]
    assert shared and all(e.stance["H5"] == e.stance["H1"] for e in shared)


def test_reported_evidence_counts_match_the_stances_kept(inject):
    inject(_llm("H5", *POOL), _llm("H6", *RELEASE))
    inv = _run()
    reported = {s.output_summary.split(" ", 1)[0]: s.output_summary for s in inv.steps
                if s.kind == "tool_result" and s.tool == "gather_evidence"}
    assert set(reported) == {h.id for h in inv.hypotheses}
    for hid, summary in reported.items():
        total, supporting, refuting = map(int, re.search(r"(\d+) evidence items \((\d+) supporting, (\d+) refuting",
                                                         summary).groups())
        assert total == sum(hid in e.stance for e in inv.evidence), hid
        assert supporting == sum(e.stance.get(hid) == "supports" for e in inv.evidence), hid
        assert refuting == sum(e.stance.get(hid) == "refutes" for e in inv.evidence), hid


# ================================================================ Part B: proposals behind LLM_HYPOTHESES=1


@pytest.fixture
def spy(monkeypatch):
    """A silent LLM that records every (key, messages) and answers from `replies` (default "")."""
    calls: list[tuple[str, list[dict[str, str]]]] = []
    replies: dict[str, str] = {}

    class SpyLLM:
        fallback_reason = None

        def __init__(self, incident_id, mode=None):
            self.record = False

        def complete(self, key, messages=None):
            calls.append((key, messages))
            return replies.get(key, "")

    monkeypatch.setattr(orchestrator, "LLMClient", SpyLLM)
    return calls, replies


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv("LLM_HYPOTHESES", "1")


def _proposals(*pairs: tuple[str, str]) -> str:
    return json.dumps([{"title": t, "mechanism": m} for t, m in pairs])


def _llm_hypotheses(inv: Investigation) -> list[Hypothesis]:
    return [h for h in inv.hypotheses if h.origin == "llm"]


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", " 1"])
def test_flag_off_makes_no_proposal_call(monkeypatch, spy, value):
    calls, replies = spy
    if value is None:
        monkeypatch.delenv("LLM_HYPOTHESES", raising=False)
    else:
        monkeypatch.setenv("LLM_HYPOTHESES", value)
    replies[orchestrator.PROPOSE_KEY] = _proposals(POOL)
    inv = _run()
    assert [key for key, _ in calls] == THOUGHT_KEYS
    assert _llm_hypotheses(inv) == []


def test_flag_on_adds_up_to_two_llm_hypotheses(monkeypatch, spy, flag_on):
    calls, replies = spy
    replies[orchestrator.PROPOSE_KEY] = _proposals(POOL, RELEASE)
    seen_by_engine = []
    gather = tools.TOOLS["gather_evidence"]
    def recording_gather(incident_id, hypothesis):
        seen_by_engine.append(hypothesis)
        return gather(incident_id, hypothesis)

    monkeypatch.setitem(tools.TOOLS, "gather_evidence", recording_gather)
    inv = _run()
    keys = [key for key, _ in calls]
    assert keys == THOUGHT_KEYS[:2] + [orchestrator.PROPOSE_KEY] + THOUGHT_KEYS[2:]
    added = _llm_hypotheses(inv)
    assert [(h.id, h.title, h.mechanism) for h in added] == [("H5", *POOL), ("H6", *RELEASE)]
    as_proposed = [h for h in seen_by_engine if h.origin == "llm"]
    assert [(h.status, h.confidence) for h in as_proposed] == [("proposed", 0.25), ("proposed", 0.25)]
    decisions = [s for s in inv.steps if s.kind == "decision" and s.output_summary.startswith("Added LLM-proposed")]
    assert [(d.stage, d.output_summary) for d in decisions] == [
        ("hypotheses", f"Added LLM-proposed hypothesis H5 {POOL[0]}: {POOL[1]}"),
        ("hypotheses", f"Added LLM-proposed hypothesis H6 {RELEASE[0]}: {RELEASE[1]}")]
    assert _by_id(inv)["H5"].status == "supported" and _by_id(inv)["H6"].status == "rejected"
    assert inv.stage == "awaiting_approval" and inv.root_cause.hypothesis_id == "H1"
    for i, step in enumerate(inv.steps):  # the H12 rule still holds: every tool call is followed by its result
        if step.kind == "tool_call":
            assert inv.steps[i + 1].kind == "tool_result" and inv.steps[i + 1].tool == step.tool


@pytest.mark.parametrize("fence", ["```json\n{}\n```", "```\n{}\n```", "Here you go:\n```json\n{}\n```\nThanks"])
def test_code_fenced_json_is_accepted(spy, flag_on, fence):
    _, replies = spy
    replies[orchestrator.PROPOSE_KEY] = fence.replace("{}", _proposals(POOL))
    assert [(h.id, h.title) for h in _llm_hypotheses(_run())] == [("H5", POOL[0])]


@pytest.mark.parametrize("reply", [
    "not json at all",
    '{"title": "Pool starvation", "mechanism": "ran out"}',  # an object, not a list
    '["Pool starvation"]',  # a list, but not of objects
    '[{"title": "Pool starvation"}]',  # missing mechanism
    '[{"title": "", "mechanism": "ran out"}]',  # empty title
    '[{"title": "Pool starvation", "mechanism": "   "}]',  # blank mechanism
    '[{"title": 5, "mechanism": "ran out"}]',  # wrong type
    "[]",
    "",
])
def test_unusable_proposals_are_ignored_and_the_run_continues(spy, flag_on, reply):
    _, replies = spy
    replies[orchestrator.PROPOSE_KEY] = reply
    inv = _run()
    assert _llm_hypotheses(inv) == [] and [h.id for h in inv.hypotheses] == ["H1", "H2", "H3", "H4"]
    assert inv.stage == "awaiting_approval", inv.error


def test_seed_duplicates_are_dropped_and_at_most_two_are_kept(spy, flag_on):
    _, replies = spy
    seed_title = _seed_titles()[0]
    long_title = "Long " * 100
    replies[orchestrator.PROPOSE_KEY] = _proposals(
        (seed_title.upper(), "Same as the first seed, shouted."),  # duplicate of a seed: dropped
        ("Bad   release", RELEASE[1]),
        ("bad release", "Repeats the previous proposal."),  # duplicate of a proposal: dropped
        (long_title, "x " * 1000),
        POOL,  # third usable proposal: over the cap
    )
    added = _llm_hypotheses(_run())
    assert [h.id for h in added] == ["H5", "H6"]
    assert added[0].title == "Bad release"
    assert len(added[1].title) == orchestrator.TITLE_MAX and added[1].title.endswith("…")
    assert len(added[1].mechanism) == orchestrator.MECHANISM_MAX and added[1].mechanism.endswith("…")


def test_replay_with_the_flag_on_but_no_recorded_proposal_adds_nothing(flag_on):
    recording = Path(llm.RECORDINGS_DIR) / f"{INCIDENT}.json"
    before = recording.read_bytes()
    recorded = json.loads(before)
    assert orchestrator.PROPOSE_KEY not in recorded
    inv = _run()
    assert _llm_hypotheses(inv) == [] and inv.stage == "awaiting_approval"
    assert [s.output_summary for s in inv.steps if s.kind == "thought"] == [recorded[k] for k in THOUGHT_KEYS]
    assert recording.read_bytes() == before


def test_recorded_proposals_replay_exactly(monkeypatch, tmp_path, flag_on):
    golden = json.loads((Path(llm.RECORDINGS_DIR) / f"{INCIDENT}.json").read_text(encoding="utf-8"))
    (tmp_path / f"{INCIDENT}.json").write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    monkeypatch.setattr(llm, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setenv("RECORD", "1")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def post(url, json=None, **kwargs):
        prompt = json["messages"][-1]["content"]
        content = _proposals(POOL, RELEASE) if "additional root-cause hypotheses" in prompt else "Live narration."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    live = _run("inv-live", mode="live")
    assert [(h.id, h.title) for h in _llm_hypotheses(live)] == [("H5", POOL[0]), ("H6", RELEASE[0])]
    recorded = json.loads((tmp_path / f"{INCIDENT}.json").read_text(encoding="utf-8"))
    assert json.loads(recorded[orchestrator.PROPOSE_KEY]) == [{"title": t, "mechanism": m} for t, m in (POOL, RELEASE)]

    replay = _run("inv-replay", mode="replay")
    fields = ("id", "title", "mechanism", "origin", "status", "confidence")
    assert [[getattr(h, f) for f in fields] for h in replay.hypotheses] == \
           [[getattr(h, f) for f in fields] for h in live.hypotheses]
    assert [s.output_summary for s in replay.steps if s.kind in ("thought", "decision")] == \
           [s.output_summary for s in live.steps if s.kind in ("thought", "decision")]


def test_proposal_prompt_has_the_system_message_and_real_seed_titles(spy, flag_on):
    calls, _ = spy
    _run()
    [(_, messages)] = [(k, m) for k, m in calls if k == orchestrator.PROPOSE_KEY]
    system = (orchestrator.PROMPTS_DIR / "system.md").read_text(encoding="utf-8").strip()
    assert [m["role"] for m in messages] == ["system", "user"] and messages[0]["content"] == system
    prompt = messages[1]["content"]
    assert "unknown" not in prompt
    assert all(title in prompt for title in _seed_titles())
    timeline = tools.call("build_timeline", incident_id=INCIDENT)
    assert all(e.id in prompt for e in timeline if e.state_change)
    assert '[{"title": ' in prompt  # the doubled braces render as a literal JSON example
