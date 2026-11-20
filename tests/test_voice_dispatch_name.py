import pytest

from veteran_access_bridge.voice.dispatch_name import voice_agent_name


def test_default_and_isolated_dispatch(monkeypatch):
    monkeypatch.delenv("VAB_VOICE_AGENT_NAME", raising=False)
    assert voice_agent_name() == "vab-avery"
    monkeypatch.setenv("VAB_VOICE_AGENT_NAME", "vab-avery-latency-eval")
    assert voice_agent_name() == "vab-avery-latency-eval"


@pytest.mark.parametrize(
    "name", ["", "other-agent", "vab-avery\n", "vab-avery-" + "a" * 41]
)
def test_invalid_dispatch_fails_closed(monkeypatch, name):
    monkeypatch.setenv("VAB_VOICE_AGENT_NAME", name)
    with pytest.raises(ValueError):
        voice_agent_name()
