"""LLM 参与度控制测试（C0）：全局三档 + 每 agent 布尔开关。"""

from src import llm_mode


def _clean_env(monkeypatch):
    monkeypatch.delenv("VOICEDNA_LLM_MODE", raising=False)
    for agent in llm_mode.AGENTS:
        monkeypatch.delenv(f"VOICEDNA_LLM_{agent.upper()}", raising=False)


def test_default_mode_is_fallback(monkeypatch):
    _clean_env(monkeypatch)
    assert llm_mode.get_mode() == llm_mode.MODE_FALLBACK


def test_set_mode_roundtrip(monkeypatch):
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_FULL)
    assert llm_mode.get_mode() == llm_mode.MODE_FULL
    llm_mode.set_mode(llm_mode.MODE_DETERMINISTIC)
    assert llm_mode.get_mode() == llm_mode.MODE_DETERMINISTIC


def test_set_mode_invalid_falls_back(monkeypatch):
    _clean_env(monkeypatch)
    llm_mode.set_mode("bogus")
    assert llm_mode.get_mode() == llm_mode.MODE_FALLBACK


def test_agents_default_all_enabled(monkeypatch):
    _clean_env(monkeypatch)
    for agent in llm_mode.AGENTS:
        assert llm_mode.agent_enabled(agent) is True


def test_set_agent_off_disables(monkeypatch):
    _clean_env(monkeypatch)
    llm_mode.set_agent("style_mimic", False)
    assert llm_mode.agent_enabled("style_mimic") is False


def test_llm_enabled_fallback_with_switch_on(monkeypatch):
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_FALLBACK)
    assert llm_mode.llm_enabled("script_writer") is True


def test_llm_enabled_respects_agent_switch(monkeypatch):
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_FALLBACK)
    llm_mode.set_agent("script_writer", False)
    assert llm_mode.llm_enabled("script_writer") is False


def test_deterministic_mode_forces_zero_llm(monkeypatch):
    """确定性档无视开关强制零 LLM（style_mimic 等全关）。"""
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_DETERMINISTIC)
    for agent in llm_mode.AGENTS:
        assert llm_mode.llm_enabled(agent) is False


def test_should_llm_full_always_true(monkeypatch):
    """全开档：有 baseline 也调 LLM。"""
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_FULL)
    assert llm_mode.should_llm("topic_planner", has_baseline=True) is True


def test_should_llm_fallback_only_when_no_baseline(monkeypatch):
    """兜底档：无 baseline 才调 LLM。"""
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_FALLBACK)
    assert llm_mode.should_llm("topic_planner", has_baseline=True) is False
    assert llm_mode.should_llm("topic_planner", has_baseline=False) is True


def test_should_llm_deterministic_never(monkeypatch):
    """确定性档：无论如何不调 LLM。"""
    _clean_env(monkeypatch)
    llm_mode.set_mode(llm_mode.MODE_DETERMINISTIC)
    assert llm_mode.should_llm("topic_planner", has_baseline=False) is False


# ——— supplement 统一入口 ———


def test_supplement_full_mode_calls_fn(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "has_key", lambda: True)
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FULL)
    out = llm_mode.supplement(
        "script_writer", has_baseline=True, baseline={"body": "old"}, fn=lambda: {"body": "new"}
    )
    assert out == {"body": "new"}


def test_supplement_fallback_with_baseline_keeps_baseline(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "has_key", lambda: True)
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FALLBACK)
    out = llm_mode.supplement(
        "script_writer", has_baseline=True, baseline={"body": "old"}, fn=lambda: {"body": "new"}
    )
    assert out == {"body": "old"}


def test_supplement_no_baseline_tags_llm_fallback(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "has_key", lambda: True)
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FALLBACK)
    out = llm_mode.supplement("x", has_baseline=False, baseline=None, fn=lambda: {"a": 1})
    assert out == {"a": 1, "llm_fallback": True}


def test_supplement_no_key_returns_baseline(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "has_key", lambda: False)
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FULL)
    out = llm_mode.supplement("x", True, {"b": 2}, fn=lambda: {"c": 3})
    assert out == {"b": 2}


def test_supplement_exception_returns_baseline(monkeypatch):
    from src import llm

    monkeypatch.setattr(llm, "has_key", lambda: True)
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FULL)

    def boom():
        raise RuntimeError("boom")

    assert llm_mode.supplement("x", True, {"b": 2}, boom) == {"b": 2}
