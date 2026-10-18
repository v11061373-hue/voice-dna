"""C2 三段式 LLM 补充测试：各 agent 按 C0 档位接 llm.call_llm + persona。"""

from src import llm, llm_mode
from src.tools import (
    data_analyst,
    publish_optimizer,
    script_writer,
    topic_planner,
    trend_hunter,
)


def _full(monkeypatch):
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FULL)


def _fallback(monkeypatch):
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_FALLBACK)


def _deterministic(monkeypatch):
    monkeypatch.setattr(llm_mode, "get_mode", lambda: llm_mode.MODE_DETERMINISTIC)


def _with_key(monkeypatch, llm_return):
    monkeypatch.setattr(llm, "has_key", lambda: True)
    calls = []
    monkeypatch.setattr(llm, "call_llm", lambda prompt, **kw: calls.append(kw) or llm_return)
    return calls


def _no_key(monkeypatch):
    monkeypatch.setattr(llm, "has_key", lambda: False)
    calls = []
    monkeypatch.setattr(llm, "call_llm", lambda prompt, **kw: calls.append(1))
    return calls


# ——— trend_hunter 关键词 LLM 抽取（替代 A3 词表）———


def test_trend_hunter_full_mode_llm_keywords(monkeypatch):
    _full(monkeypatch)
    calls = _with_key(monkeypatch, '["美妆", "护肤"]')
    assert trend_hunter.extract_keywords("美妆博主") == ["美妆", "护肤"]
    assert calls


def test_trend_hunter_fallback_unknown_profile_llm(monkeypatch):
    """兜底档：词表无匹配（无 baseline）才调 LLM。"""
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, '["手作"]')
    assert trend_hunter.extract_keywords("手作博主") == ["手作"]
    assert calls


def test_trend_hunter_fallback_known_profile_no_llm(monkeypatch):
    """兜底档：词表命中（有 baseline）不调 LLM。"""
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, "[]")
    kws = trend_hunter.extract_keywords("美妆博主")
    assert "美妆" in kws
    assert not calls


def test_trend_hunter_deterministic_no_llm(monkeypatch):
    _deterministic(monkeypatch)
    calls = _with_key(monkeypatch, "[]")
    assert "美妆" in trend_hunter.extract_keywords("美妆博主")
    assert not calls


# ——— topic_planner LLM 写理由 ———


def test_topic_planner_full_mode_llm_reason(monkeypatch):
    _full(monkeypatch)
    calls = _with_key(monkeypatch, '[{"title": "A", "reason": "LLM洞察"}]')
    out = topic_planner.run(trends=[{"title": "A", "heat": 100}])
    assert out[0]["reason"] == "LLM洞察"
    assert calls


def test_topic_planner_fallback_no_llm(monkeypatch):
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, "[]")
    out = topic_planner.run(trends=[{"title": "A", "heat": 100}])
    assert out  # 确定性理由仍在
    assert not calls


def test_topic_planner_llm_passes_persona(monkeypatch):
    """LLM 调用带 system persona。"""
    _full(monkeypatch)
    calls = _with_key(monkeypatch, "[]")
    topic_planner.run(trends=[{"title": "A", "heat": 100}])
    assert calls[0]["system"]


# ——— script_writer LLM 写 body ———


def test_script_writer_full_mode_llm_body(monkeypatch):
    _full(monkeypatch)
    calls = _with_key(
        monkeypatch,
        '{"scenes": [{"visual": "v", "narration": "LLM旁白", "duration": 5}]}',
    )
    out = script_writer.run(style_card={})
    assert out["body"] == "LLM旁白"
    assert out["duration"] == 5
    assert calls


def test_script_writer_fallback_no_llm(monkeypatch):
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, "{}")
    out = script_writer.run()
    assert out["body"].strip()
    assert not calls


# ——— publish_optimizer LLM 优化标题标签 ———


def test_publish_optimizer_full_mode_llm_tags(monkeypatch):
    _full(monkeypatch)
    calls = _with_key(
        monkeypatch,
        '{"tags": ["新标签"], "hashtags": ["#新"], "description": "新描述"}',
    )
    out = publish_optimizer.run(script={"body": "x"})
    assert out["tags"] == ["新标签"]
    assert out["description"] == "新描述"
    assert calls


def test_publish_optimizer_fallback_no_llm(monkeypatch):
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, "{}")
    out = publish_optimizer.run(script={"body": "x"})
    assert "tags" in out
    assert not calls


# ——— data_analyst LLM 写结论 ———


def test_data_analyst_full_mode_llm_conclusion(monkeypatch):
    _full(monkeypatch)
    calls = _with_key(monkeypatch, "LLM结论")
    out = data_analyst.run()
    assert out["report"] == "LLM结论"
    assert calls


def test_data_analyst_fallback_no_llm(monkeypatch):
    _fallback(monkeypatch)
    calls = _with_key(monkeypatch, '"x"')
    out = data_analyst.run()
    assert out["report"]
    assert not calls


# ——— 零 LLM（确定性档 + 无 key）———


def test_deterministic_zero_llm_across_agents(monkeypatch):
    """确定性档跑全流程零 LLM（style_mimic 降级卡、其余走主路径）。"""
    _deterministic(monkeypatch)
    calls = _with_key(monkeypatch, "[]")
    topic_planner.run(trends=[{"title": "A", "heat": 1}])
    script_writer.run()
    publish_optimizer.run(script={"body": "x"})
    data_analyst.run()
    assert not calls
