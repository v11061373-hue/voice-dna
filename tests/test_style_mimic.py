"""风格模仿 tool 契约测试（占位骨架）。

占位 run() 不接 LLM；本测试锁契约：风格卡字段 + 抽取 prompt 模板，
接 LLM（步骤 5）时改 run() 用模板喂模型，字段签名不变。
"""

import pytest

from src.tools import style_mimic


def test_run_returns_style_card_dict(monkeypatch):
    """有 key 时 run() 组装 prompt 喂 LLM 解析风格卡，返回 dict 含 persona。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(style_mimic, "_call_deepseek", lambda _: '{"persona": "p"}')
    out = style_mimic.run()
    assert isinstance(out, dict)
    assert out["persona"] == "p"


def test_run_without_api_key_degrades(monkeypatch):
    """无 DEEPSEEK_API_KEY 时降级确定性风格卡（7 字段），不崩。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out = style_mimic.run()
    assert set(out) == set(style_mimic.STYLE_CARD_FIELDS)
    assert out["persona"]


def test_style_card_schema_has_seven_fields():
    """风格卡 schema 定 7 字段（借 StyleLLM models 风格维度）。"""
    assert set(style_mimic.STYLE_CARD_FIELDS) == {
        "persona",
        "voice",
        "catchphrases",
        "sentence_patterns",
        "pacing",
        "narrative_structure",
        "visual_style",
    }


def test_prompt_template_names_all_dimensions():
    """抽取 prompt 模板覆盖 7 个抽取维度（借 stylellm_chat/lobe-chat-agents 配方）。"""
    tpl = style_mimic.STYLE_CARD_PROMPT_TEMPLATE
    for dim in style_mimic.STYLE_CARD_FIELDS:
        assert dim in tpl


def test_parse_style_card_plain_json():
    """LLM 返回纯 JSON → 7 字段 dict。"""
    text = '{"persona":"毒舌","voice":"短句","catchphrases":["笑死"],"sentence_patterns":["反问"],"pacing":"快","narrative_structure":"hook","visual_style":"暗色"}'
    card = style_mimic.parse_style_card(text)
    assert card["persona"] == "毒舌"
    assert card["catchphrases"] == ["笑死"]


def test_parse_style_card_strips_markdown_fence():
    """LLM 常把 JSON 包 ```json 里，剥掉再解析。"""
    text = '```json\n{"persona":"p","voice":"v","catchphrases":[],"sentence_patterns":[],"pacing":"x","narrative_structure":"y","visual_style":"z"}\n```'
    card = style_mimic.parse_style_card(text)
    assert card["persona"] == "p"


def test_parse_style_card_fills_missing_fields():
    """LLM 缺字段 → 列表补 []，其余补「未知」，不崩。"""
    card = style_mimic.parse_style_card('{"persona":"p"}')
    assert card["voice"] == "未知"
    assert card["catchphrases"] == []


def test_parse_style_card_invalid_json_raises():
    """非 JSON → ValueError（调用方重试）。"""
    with pytest.raises(ValueError):
        style_mimic.parse_style_card("not json")
