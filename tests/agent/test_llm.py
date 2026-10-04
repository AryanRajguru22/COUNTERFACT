"""The LLM client defaults to replay mode and needs no key or network."""

import httpx
import pytest

from agent import llm
from agent.llm import LLMClient, llm_mode

REPLAY_TIMELINE = "Rebuilding the timeline"


def test_replay_is_default(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert llm_mode() == "replay"
    assert LLMClient("INC-2041").complete("thought.timeline").startswith(REPLAY_TIMELINE)


def test_replay_missing_key_returns_empty():
    assert LLMClient("INC-2041", "replay").complete("thought.unknown") == ""


# ---------------------------------------------------------------- H6: live falls back to replay


@pytest.fixture
def live_config(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")


def _fake_post(monkeypatch, respond):
    """Stand in for httpx.post so no test touches the network; returns the list of URLs called."""
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return respond(httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    return calls


def _connect_error(request):
    raise httpx.ConnectError("connection refused", request=request)


def _timeout(request):
    raise httpx.ReadTimeout("timed out", request=request)


def test_live_without_config_falls_back_to_replay(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    calls = _fake_post(monkeypatch, _connect_error)
    client = LLMClient("INC-2041", "live")
    assert client.complete("thought.timeline").startswith(REPLAY_TIMELINE)
    assert client.mode == "live"
    assert "LLM_BASE_URL" in client.fallback_reason
    assert calls == []


@pytest.mark.parametrize("respond", [
    _connect_error,
    _timeout,
    lambda request: httpx.Response(500, request=request),
    lambda request: httpx.Response(200, json={"unexpected": True}, request=request),
], ids=["connect_error", "timeout", "http_500", "malformed_body"])
def test_live_failure_falls_back_and_stays_on_replay(monkeypatch, live_config, respond):
    calls = _fake_post(monkeypatch, respond)
    client = LLMClient("INC-2041", "live")
    assert client.complete("thought.timeline").startswith(REPLAY_TIMELINE)
    assert client.fallback_reason
    assert client.mode == "live"
    assert client.complete("thought.hypotheses").startswith("Four explanations")
    assert len(calls) == 1  # no second live attempt once the client has fallen back


def test_live_success_does_not_fall_back(monkeypatch, live_config):
    _fake_post(monkeypatch, lambda request: httpx.Response(
        200, json={"choices": [{"message": {"content": "live narration"}}]}, request=request))
    client = LLMClient("INC-2041", "live")
    assert client.complete("thought.timeline") == "live narration"
    assert client.fallback_reason is None
