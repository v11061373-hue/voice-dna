"""6 agent 专家 persona 测试（C1）：role/goal/backstory + system prompt。"""

from src import agents


def test_six_agents_have_personas():
    """6 agent 各一 persona，含 role/goal/backstory 三字段非空。"""
    assert set(agents.PERSONAS) == {
        "trend_hunter",
        "topic_planner",
        "style_mimic",
        "script_writer",
        "publish_optimizer",
        "data_analyst",
    }
    for name, p in agents.PERSONAS.items():
        for field in ("role", "goal", "backstory"):
            assert str(p.get(field, "")).strip(), f"{name} 缺 {field}"


def test_system_prompt_contains_identity():
    """system prompt 含 role/goal/backstory，喂 llm.call_llm 的 system 参数。"""
    p = agents.PERSONAS["script_writer"]
    text = agents.system_prompt("script_writer")
    assert p["role"] in text
    assert p["goal"] in text
    assert p["backstory"] in text


def test_system_prompt_unknown_agent_empty():
    """未知 agent 返回空串（不崩）。"""
    assert agents.system_prompt("nonexistent") == ""
