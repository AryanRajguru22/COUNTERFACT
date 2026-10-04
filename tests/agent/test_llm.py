"""The LLM client defaults to replay mode and needs no key or network."""

from agent.llm import LLMClient, llm_mode


def test_replay_is_default(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert llm_mode() == "replay"
    assert LLMClient("INC-2041").complete("thought.timeline").startswith("Rebuilding the timeline")


def test_replay_missing_key_returns_empty():
    assert LLMClient("INC-2041", "replay").complete("thought.unknown") == ""
