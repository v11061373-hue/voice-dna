"""LLM-judge 测试（C3）：结构化打分 {score, pass, reason}，与主 LLM 解耦。"""

from src.orchestrator import judge


def test_parse_judge_plain_json():
    text = '{"score": 8.5, "pass": true, "reason": "正常"}'
    out = judge.parse_judge(text)
    assert out == {"score": 8.5, "pass": True, "reason": "正常"}


def test_parse_judge_strips_markdown_fence():
    text = '```json\n{"score": 2, "pass": false, "reason": "编造"}\n```'
    out = judge.parse_judge(text)
    assert out["pass"] is False
    assert out["score"] == 2.0


def test_parse_judge_fills_defaults():
    out = judge.parse_judge("{}")
    assert out == {"score": 0.0, "pass": True, "reason": ""}


def test_judge_skips_without_key(monkeypatch):
    monkeypatch.setattr(judge.config, "judge_settings", lambda: ("", "", ""))
    out = judge.judge("prompt")
    assert out["pass"] is True


def test_judge_skips_in_deterministic_mode(monkeypatch):
    monkeypatch.setattr(judge.llm_mode, "get_mode", lambda: judge.llm_mode.MODE_DETERMINISTIC)
    out = judge.judge("prompt")
    assert out["pass"] is True


def test_judge_calls_llm_with_judge_settings(monkeypatch):
    """judge 走 config.judge_settings() 的独立 provider，返回结构化判决。"""
    monkeypatch.setattr(judge.llm_mode, "get_mode", lambda: judge.llm_mode.MODE_FALLBACK)
    monkeypatch.setattr(
        judge.config,
        "judge_settings",
        lambda: ("https://judge.example.com", "judge-model", "judge-key"),
    )
    captured = {}

    def fake_call(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return '{"score": 3, "pass": false, "reason": "编造"}'

    monkeypatch.setattr(judge.llm, "call_llm", fake_call)
    out = judge.judge("待溯源内容")
    assert out["pass"] is False
    assert captured["kwargs"]["base_url"] == "https://judge.example.com"
    assert captured["kwargs"]["model"] == "judge-model"
    assert captured["kwargs"]["key"] == "judge-key"
