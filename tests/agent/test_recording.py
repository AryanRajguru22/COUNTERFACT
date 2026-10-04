"""H12: RECORD=1 merges successful live responses into the recording so replay reproduces the live run.

Every test points RECORDINGS_DIR at a temp directory and fakes httpx.post: no network, and the real
agent/recordings/INC-2041.json is only ever read (to seed the temp copy), never written.
"""

import json
from pathlib import Path

import httpx
import pytest

from agent import llm, orchestrator, tools
from backend.store import InvestigationStore
from contracts.models import Approval, Investigation

GOLDEN = json.loads((llm.RECORDINGS_DIR / "INC-2041.json").read_text(encoding="utf-8"))
REPLAY_KEYS = list(GOLDEN)


def _canonical(recordings: dict[str, str]) -> bytes:
    return (json.dumps(recordings, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


@pytest.fixture
def recordings(monkeypatch, tmp_path) -> Path:
    """A temp recordings dir seeded with a copy of the golden INC-2041 recording; returns the file path."""
    monkeypatch.setattr(llm, "RECORDINGS_DIR", tmp_path)
    path = tmp_path / "INC-2041.json"
    path.write_bytes(_canonical(GOLDEN))
    return path


@pytest.fixture
def live_config(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")


@pytest.fixture
def record_on(monkeypatch):
    monkeypatch.setenv("RECORD", "1")


def _provider(monkeypatch, reply):
    """Fake the chat-completions endpoint. `reply(n)` gives the content for call n (0-based) or raises."""
    calls: list[list[dict[str, str]]] = []

    def post(url, json=None, **kwargs):
        calls.append(json["messages"])
        content = reply(len(calls) - 1)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    return calls


def _numbered(n: int) -> str:
    return f"Live narration #{n} → recorded verbatim."


def _run(mode: str, investigation_id: str = "inv-rec") -> tuple[InvestigationStore, Investigation]:
    store = InvestigationStore()
    store.put(Investigation(id=investigation_id, incident=tools.get_incident("INC-2041"), mode=mode))
    orchestrator.run(investigation_id, store)
    return store, store.get(investigation_id)


def _thoughts(investigation: Investigation) -> list[str]:
    return [s.output_summary for s in investigation.steps if s.kind == "thought"]


# ---------------------------------------------------------------- client level


@pytest.mark.parametrize("value", [None, "", "0", "true", "TRUE", "yes", "on", " 1"])
def test_recording_is_off_unless_record_is_exactly_1(monkeypatch, recordings, live_config, value):
    if value is None:
        monkeypatch.delenv("RECORD", raising=False)
    else:
        monkeypatch.setenv("RECORD", value)
    before = recordings.read_bytes()
    _provider(monkeypatch, _numbered)
    client = llm.LLMClient("INC-2041", "live")
    assert client.complete("thought.timeline") == _numbered(0)
    assert client.record is False
    assert recordings.read_bytes() == before


def test_live_response_is_merged_preserving_keys_order_and_format(monkeypatch, recordings, live_config, record_on):
    _provider(monkeypatch, _numbered)
    client = llm.LLMClient("INC-2041", "live")
    assert client.complete("thought.hypotheses") == _numbered(0)
    expected = {**GOLDEN, "thought.hypotheses": _numbered(0)}
    assert list(json.loads(recordings.read_text(encoding="utf-8"))) == REPLAY_KEYS
    assert recordings.read_bytes() == _canonical(expected)  # indent=2, non-ASCII kept, LF, trailing newline
    assert "→" in recordings.read_text(encoding="utf-8") and b"\r" not in recordings.read_bytes()
    assert [p.name for p in recordings.parent.iterdir()] == ["INC-2041.json"]  # no temp file left behind
    # The golden file is already in this exact format, so recording never reformats it.
    real = (Path(orchestrator.__file__).parent / "recordings" / "INC-2041.json").read_bytes()
    assert real == _canonical(json.loads(real))


def test_replay_mode_never_records(monkeypatch, recordings, record_on):
    calls = _provider(monkeypatch, _numbered)
    before = recordings.read_bytes()
    client = llm.LLMClient("INC-2041", "replay")
    assert client.complete("thought.timeline") == GOLDEN["thought.timeline"]
    assert calls == [] and recordings.read_bytes() == before


@pytest.mark.parametrize("configured", [True, False], ids=["provider_error", "missing_config"])
def test_failed_live_call_and_everything_after_fallback_is_not_recorded(monkeypatch, recordings, record_on,
                                                                        configured):
    if configured:
        monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
        monkeypatch.setenv("LLM_MODEL", "test-model")
    else:
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)

    def fail(n):
        raise httpx.ConnectError("connection refused")

    calls = _provider(monkeypatch, fail)
    before = recordings.read_bytes()
    client = llm.LLMClient("INC-2041", "live")
    assert client.complete("thought.timeline") == GOLDEN["thought.timeline"]
    assert client.fallback_reason
    assert client.complete("thought.hypotheses") == GOLDEN["thought.hypotheses"]
    assert len(calls) == (1 if configured else 0)
    assert recordings.read_bytes() == before


@pytest.mark.parametrize("content", ["", None], ids=["empty", "none"])
def test_empty_live_content_is_not_recorded(monkeypatch, recordings, live_config, record_on, content):
    _provider(monkeypatch, lambda n: content)
    before = recordings.read_bytes()
    assert llm.LLMClient("INC-2041", "live").complete("thought.timeline") == content
    assert recordings.read_bytes() == before


def test_missing_recording_file_is_created(monkeypatch, tmp_path, live_config, record_on):
    monkeypatch.setattr(llm, "RECORDINGS_DIR", tmp_path / "new")
    _provider(monkeypatch, _numbered)
    llm.LLMClient("INC-NEW", "live").complete("thought.timeline")
    assert (tmp_path / "new" / "INC-NEW.json").read_bytes() == _canonical({"thought.timeline": _numbered(0)})


# ---------------------------------------------------------------- record a live run, then replay it


def test_recorded_live_run_replays_exactly(monkeypatch, recordings, live_config, record_on):
    _provider(monkeypatch, _numbered)
    _, live = _run("live")
    assert live.stage == "awaiting_approval", live.error
    assert _thoughts(live) == [_numbered(n) for n in range(len(REPLAY_KEYS))]
    assert json.loads(recordings.read_text(encoding="utf-8")) == dict(zip(REPLAY_KEYS, _thoughts(live)))

    _, replay = _run("replay", "inv-replay")
    assert _thoughts(replay) == _thoughts(live)


def test_partial_live_run_records_only_what_succeeded(monkeypatch, recordings, live_config, record_on):
    def reply(n):
        if n >= 3:
            raise httpx.ConnectError("provider went away")
        return _numbered(n)

    _provider(monkeypatch, reply)
    _, live = _run("live")
    assert live.stage == "awaiting_approval", live.error
    expected = {**GOLDEN, **{k: _numbered(n) for n, k in enumerate(REPLAY_KEYS[:3])}}
    assert recordings.read_bytes() == _canonical(expected)
    assert _thoughts(live) == list(expected.values())  # 3 live, then 4 replayed after the fallback

    _, replay = _run("replay", "inv-replay")
    assert _thoughts(replay) == _thoughts(live)


def test_replan_after_a_recorded_run_does_not_overwrite_the_recommendation(monkeypatch, recordings, live_config,
                                                                           record_on):
    calls = _provider(monkeypatch, _numbered)
    store, live = _run("live")
    recorded = recordings.read_bytes()
    first = live.recommendation.intervention_id
    orchestrator.resume_after_approval(live.id, Approval(intervention_id=first, decision="rejected",
                                                         approver="sre-lead", note="change freeze"), store)
    replanned = store.get(live.id)
    assert replanned.stage == "awaiting_approval", replanned.error
    assert len(calls) == len(REPLAY_KEYS) + 1  # the replan really asked the live provider
    assert _thoughts(replanned)[-1] == _numbered(len(REPLAY_KEYS))
    assert recordings.read_bytes() == recorded  # ...but its narration was not recorded
