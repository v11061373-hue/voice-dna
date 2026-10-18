"""Concierge（P4-C4）测试 — 只读白名单 / 启动判意 / 锚定 state 回答。"""

from src import concierge


def test_read_tools_allowed_and_write_rejected():
    g = concierge.make_guard()
    for t in ("get_state", "list_sources", "cookie_status", "start_pipeline"):
        assert g.check(agent_id="concierge", tool_name=t, action="read").allowed
    for t in ("run", "write_file", "post", "trend_hunter", "script_writer", "delete"):
        d = g.check(agent_id="concierge", tool_name=t, action="read")
        assert not d.allowed
        assert d.gate == "G1"


def test_explicit_start_triggers_pipeline():
    for t in ("启动", "帮我做一条美妆视频", "帮我写一篇数码测评"):
        r = concierge.handle(t)
        assert r.kind == "start_pipeline"
        assert r.profile


def test_ambiguous_ask_does_not_trigger():
    assert concierge.handle("帮我").kind == "ask_start"


def test_answer_grounded_in_state():
    r = concierge.handle(
        "帮我看看卡在哪",
        state={"current_stage": "topic_planner", "stage_status": "ok"},
    )
    assert r.kind == "answer"
    assert "topic_planner" in r.text or "选题策划" in r.text
    assert "style_mimic" in r.text or "风格模仿" in r.text


def test_answer_says_unknown_when_state_empty():
    r = concierge.handle("帮我看看卡在哪", state={})
    assert r.kind == "answer"
    assert "不知道" in r.text


def test_login_question_grounded():
    r = concierge.handle("数据源怎么登录", state={})
    assert r.kind == "answer"
    assert "数据源" in r.text
    assert "登录" in r.text


def test_product_question_grounded():
    r = concierge.handle(
        "脚本写了什么",
        state={"current_stage": "script_writer", "script": {"title": "口红开箱"}},
    )
    assert r.kind == "answer"
    assert "脚本" in r.text


def test_product_question_says_none_when_empty():
    r = concierge.handle("看一下产物", state={})
    assert r.kind == "answer"
    assert "还没有" in r.text
