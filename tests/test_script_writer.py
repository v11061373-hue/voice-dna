"""脚本文案 tool 测试 — 输出契约 {body, scenes, duration}。

scenes 分镜 schema 搬自 NarratoAI script_generation.py:131-152（picture→visual、
narration→narration、timestamp→duration），五段结构搬自 ai-youtube-shorts 五段式。
"""

import json

from src import llm
from src.tools import script_writer
from src.tools.script_writer import run


def test_run_returns_dict():
    result = run(style_card={"topic": "美妆"})
    assert isinstance(result, dict)


def test_body_is_non_empty_string():
    result = run()
    assert isinstance(result["body"], str)
    assert result["body"].strip() != ""


def test_scenes_is_list_of_storyboard_dicts():
    result = run()
    scenes = result["scenes"]
    assert isinstance(scenes, list)
    assert len(scenes) > 0
    for scene in scenes:
        assert set(scene.keys()) == {"visual", "narration", "duration"}
        assert isinstance(scene["visual"], str) and scene["visual"].strip()
        assert isinstance(scene["narration"], str) and scene["narration"].strip()
        assert isinstance(scene["duration"], int) and scene["duration"] > 0


def test_duration_is_int_and_matches_scenes():
    result = run()
    assert isinstance(result["duration"], int)
    assert result["duration"] == sum(s["duration"] for s in result["scenes"])


def test_llm_script_injects_source_material(monkeypatch):
    """LLM 写脚本 prompt 注入可溯源素材（热点/样本/画像），供溯源门对齐。"""
    captured = {}

    def fake_call(prompt, **kw):
        captured["prompt"] = prompt
        return json.dumps({"scenes": [{"visual": "v", "narration": "n", "duration": 3}]})

    monkeypatch.setattr(llm, "call_llm", fake_call)
    script_writer._llm_script(
        "美妆",
        trends=[{"title": "秋冬显白口红"}],
        samples="姐妹们这期",
        profile="美妆博主",
    )
    p = captured["prompt"]
    assert "秋冬显白口红" in p
    assert "姐妹们这期" in p
    assert "美妆博主" in p


def test_prompt_forbids_fabricating_specific_numbers(monkeypatch):
    """溯源约束显式禁编造「具体数字/型号」，并把约数换算成精确数（F1 根因）。"""
    captured = {}

    def fake_call(prompt, **kw):
        captured["prompt"] = prompt
        return json.dumps({"scenes": [{"visual": "v", "narration": "n", "duration": 3}]})

    monkeypatch.setattr(llm, "call_llm", fake_call)
    script_writer._llm_script("数码", trends=[{"title": "近万淘汰"}])
    p = captured["prompt"]
    assert "具体数字" in p
    assert "型号" in p
    assert "换算" in p


def test_run_forwards_source_material_to_llm(monkeypatch):
    """全开档 run 把热点/样本/画像喂进 LLM 写脚本。"""
    monkeypatch.setenv("VOICEDNA_LLM_MODE", "full")
    monkeypatch.setattr(llm, "has_key", lambda: True)
    captured = {}

    def fake_call(prompt, **kw):
        captured["prompt"] = prompt
        return json.dumps({"scenes": [{"visual": "v", "narration": "n", "duration": 3}]})

    monkeypatch.setattr(llm, "call_llm", fake_call)
    run(
        style_card={"topic": "美妆"},
        trends=[{"title": "秋冬显白口红"}],
        samples="姐妹们这期",
        profile="美妆博主",
    )
    assert "秋冬显白口红" in captured["prompt"]
