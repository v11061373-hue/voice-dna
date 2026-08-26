"""脚本文案 tool 测试 — 输出契约 {body, scenes, duration}。

scenes 分镜 schema 搬自 NarratoAI script_generation.py:131-152（picture→visual、
narration→narration、timestamp→duration），五段结构搬自 ai-youtube-shorts 五段式。
"""

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
