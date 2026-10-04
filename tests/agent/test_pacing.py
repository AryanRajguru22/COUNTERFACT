"""H20: STEP_DELAY_MS paces the demo from one central place, and invalid values never strand a run.

Nothing here really sleeps: the orchestrator's `time` is swapped for a fake that records each pause, so the
pacing budget is checked exactly and in milliseconds.
"""

from types import SimpleNamespace

import pytest

from agent import orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation, VerificationCheck, VerificationResult

ID = "inv-h20"


class LoggingStore(InvestigationStore):
    """Logs every publish, so each pause can be attributed to the step or stage change before it."""

    def __init__(self, log: list):
        super().__init__()
        self.log = log

    def put(self, investigation: Investigation) -> None:
        super().put(investigation)
        last = investigation.steps[-1] if investigation.steps else None
        self.log.append(("put", investigation.stage, len(investigation.steps), last.kind if last else None))


@pytest.fixture
def log(monkeypatch) -> list:
    events: list = []
    monkeypatch.setattr(orchestrator, "time", SimpleNamespace(sleep=lambda s: events.append(("sleep", s))))
    return events


def _delay(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("STEP_DELAY_MS", raising=False)
    else:
        monkeypatch.setenv("STEP_DELAY_MS", value)


def _investigate(log: list) -> LoggingStore:
    store = LoggingStore(log)
    store.put(Investigation(id=ID, incident=tools.get_incident("INC-2041")))
    log.clear()
    orchestrator.run(ID, store)
    return store


def _approve(store: LoggingStore, intervention_id: str | None = None) -> Investigation:
    intervention_id = intervention_id or store.get(ID).recommendation.intervention_id
    orchestrator.resume_after_approval(ID, Approval(intervention_id=intervention_id, decision="approved",
                                                    approver="sre-lead"), store)
    return store.get(ID)


def _slept(log: list) -> list[float]:
    return [e[1] for e in log if e[0] == "sleep"]


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize("value, seconds", [
    (None, 0.7),  # unset: the 700 ms default
    ("700", 0.7),
    (" 650 ", 0.65),
    ("650.5", 0.6505),
    ("", 0.7), ("   ", 0.7), ("abc", 0.7), ("nan", 0.7), ("inf", 0.7), ("-inf", 0.7),  # invalid: default
    ("0", 0.0), ("-100", 0.0), ("-0.5", 0.0),  # zero or negative: no pause
])
def test_step_delay_is_parsed_defensively(monkeypatch, value, seconds):
    _delay(monkeypatch, value)
    assert orchestrator.step_delay_s() == pytest.approx(seconds)


def test_default_is_700_ms():
    assert orchestrator.DEFAULT_STEP_DELAY_MS == 700


@pytest.mark.parametrize("value", ["abc", "", "600.5", "nan"])
def test_invalid_delay_does_not_strand_the_investigation(monkeypatch, log, value):
    _delay(monkeypatch, value)  # int("abc") used to raise before run()'s try, leaving it in `created` forever
    store = _investigate(log)
    assert store.get(ID).stage == "awaiting_approval", store.get(ID).error
    expected = 0.6005 if value == "600.5" else 0.7
    assert _slept(log) and all(s == pytest.approx(expected) for s in _slept(log))


@pytest.mark.parametrize("value", ["0", "-100"])
def test_zero_or_negative_delay_never_sleeps(monkeypatch, log, value):
    _delay(monkeypatch, value)
    store = _investigate(log)
    assert _approve(store).stage == "resolved"
    assert _slept(log) == []


# ---------------------------------------------------------------- where the pauses happen


def _pauses_by_publish(log: list) -> list[tuple[str, str, float | None]]:
    """(what was published, stage, pause that followed it) for every publish in the log."""
    out, steps = [], None
    for i, event in enumerate(log):
        if event[0] != "put":
            continue
        _, stage, n_steps, last_kind = event
        what = "stage" if n_steps == steps else last_kind
        steps = n_steps
        following = log[i + 1] if i + 1 < len(log) else None
        out.append((what, stage, following[1] if following and following[0] == "sleep" else None))
    return out


def _check_pause_rules(publishes, delay: float) -> None:
    for what, stage, pause in publishes:
        if what == "tool_call" or (what == "stage" and stage in orchestrator.RESTING_STAGES):
            assert pause is None, (what, stage)
        else:  # every other step, and every other stage change, pauses exactly once
            assert pause == pytest.approx(delay), (what, stage)


def test_pauses_follow_steps_and_stages_but_not_tool_calls_or_resting_stages(monkeypatch, log):
    _delay(monkeypatch, "250")
    store = _investigate(log)
    investigation = _pauses_by_publish(log)
    log.clear()
    assert _approve(store).stage == "resolved"
    approval = _pauses_by_publish(log)
    for publishes in (investigation, approval):
        _check_pause_rules(publishes, 0.25)
    kinds = {what for what, _, _ in investigation}
    assert {"stage", "tool_call", "tool_result", "thought", "decision"} <= kinds
    assert investigation[-1][:2] == ("stage", "awaiting_approval") and investigation[-1][2] is None
    assert approval[-1][:2] == ("stage", "resolved") and approval[-1][2] is None
    # Each publish pauses at most once, so the sleeps equal the paused publishes.
    assert len(_slept(log)) == sum(p is not None for _, _, p in approval)


def test_failed_stage_does_not_pause(monkeypatch, log):
    _delay(monkeypatch, "250")

    def fail(execution, model, seed):
        check = VerificationCheck(name="breach minutes", expected="<= 0", observed="9", passed=False)
        return VerificationResult(intervention_id=execution.intervention_id, passed=False, checks=[check],
                                  stress_test_passed=False)

    monkeypatch.setitem(tools.TOOLS, "verify", fail)
    store = _investigate(log)
    for _ in range(orchestrator.MAX_ATTEMPTS):
        log.clear()
        inv = _approve(store)
    assert inv.stage == "failed"
    publishes = _pauses_by_publish(log)
    _check_pause_rules(publishes, 0.25)
    assert publishes[-1][:2] == ("stage", "failed") and publishes[-1][2] is None


# ---------------------------------------------------------------- the demo budget at the 700 ms default


def test_golden_investigation_takes_20_to_30_seconds(monkeypatch, log):
    _delay(monkeypatch, None)
    store = _investigate(log)
    assert store.get(ID).stage == "awaiting_approval"
    assert 20 <= sum(_slept(log)) <= 30, sum(_slept(log))


def test_approve_to_resolved_takes_4_to_6_seconds(monkeypatch, log):
    _delay(monkeypatch, None)
    store = _investigate(log)
    log.clear()
    assert _approve(store).stage == "resolved"
    assert 4 <= sum(_slept(log)) <= 6, sum(_slept(log))
