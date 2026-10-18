"""LangGraph 编排骨架测试。

参照 BidForge 六节点 pipeline：热点猎人→选题策划→风格模仿→脚本文案→
发布优化→数据分析 + human_gate 兜底。每节点后接质量门（C3），HALT 走 human_gate。
"""

import asyncio

from src.orchestrator.graph import (
    app,
    data_analyst_node,
    route_after_analytics,
    route_after_publish,
    route_after_script,
    route_after_style,
    route_after_topic,
    route_after_trend,
    script_writer_node,
    style_mimic_node,
    topic_planner_node,
    trend_hunter_node,
    v2_app,
)
from src.tools import trend_hunter


def _script(body: str) -> dict:
    return {
        "body": body,
        "scenes": [{"visual": "v", "narration": "n", "duration": 3}],
        "duration": 3,
    }


def _analytics(report: str) -> dict:
    return {
        "report": report,
        "metrics": {"total_views": 1},
        "benchmark": {"quartile": 1},
        "anomalies": [],
    }


def test_graph_compiles_with_seven_nodes():
    """图能 compile，七节点齐全，入口 trend_hunter。"""
    graph = app.get_graph()
    nodes = set(graph.nodes.keys())
    expected = {
        "trend_hunter",
        "topic_planner",
        "style_mimic",
        "script_writer",
        "publish_optimizer",
        "data_analyst",
        "human_gate",
    }
    assert expected <= nodes


def test_linear_pipeline_runs_to_completion(monkeypatch):
    """空 profile 跑一遍，六步线性推进到 data_analyst，状态 ok。

    热点源断网时 trend_hunter 返回空，管线仍线性走完（judge 无 key 跳过）。
    """
    monkeypatch.setattr(trend_hunter, "run", lambda **kw: [])
    result = asyncio.run(app.ainvoke({"account_profile": "美妆博主"}))
    assert result["current_stage"] == "data_analyst"
    assert result["stage_status"] == "ok"


def test_script_quality_gate_halts_on_empty_script():
    """脚本质量门：schema 缺字段 / body 空 → HALT 走 human_gate。"""
    assert route_after_script({"script": {}}) == "human_gate"
    assert route_after_script({"script": _script("有效脚本")}) == "publish_optimizer"


def test_analytics_quality_gate_routes_to_end():
    """数据分析质量门：正常产出走 END，缺字段走 human_gate。"""
    assert route_after_analytics({"analytics": _analytics("正常")}) == "__end__"
    assert route_after_analytics({"analytics": {}}) == "human_gate"


def test_loop_off_by_default_stays_linear():
    """loop_rounds 缺省 0：data_analyst 不回流，仍走 END。"""
    assert route_after_analytics({"analytics": _analytics("正常"), "loop_count": 0}) == "__end__"


def test_loop_rounds_routes_back_to_topic_planner():
    """loop_count < loop_rounds：数据分析放行后回流选题策划。"""
    state = {"analytics": _analytics("正常"), "loop_count": 1, "loop_rounds": 3}
    assert route_after_analytics(state) == "topic_planner"


def test_loop_stops_when_rounds_reached():
    """已完成 loop_rounds 次额外回流（loop_count = loop_rounds+1），停止走 END。"""
    state = {"analytics": _analytics("正常"), "loop_count": 4, "loop_rounds": 3}
    assert route_after_analytics(state) == "__end__"


def test_loop_failure_precedes_loop():
    """节点失败优先于回流：即使还有轮次，失败仍走 human_gate。"""
    state = {"analytics": _analytics("正常"), "stage_status": "failed", "loop_count": 1, "loop_rounds": 3}
    assert route_after_analytics(state) == "human_gate"


def test_data_analyst_node_increments_loop_count(monkeypatch):
    """data_analyst 成功后 loop_count +1（回流计数）。"""

    async def fake_call(tool, **kw):
        return _analytics("ok")

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    out = asyncio.run(data_analyst_node({"publish_plan": {}, "loop_count": 2}))
    assert out["loop_count"] == 3


def test_topic_planner_node_forwards_analytics(monkeypatch):
    """回流时 topic_planner 收到 analytics 反馈。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool, **kw):
        calls[tool] = kw
        return []

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(topic_planner_node({"trends": [], "analytics": {"report": "上轮差"}}))
    assert calls["topic_planner"]["analytics"] == {"report": "上轮差"}


def test_route_functions_forward_to_next_stage():
    """各节点质量门放行后路由到下一节点。"""
    assert route_after_trend({"trends": []}) == "topic_planner"
    assert route_after_topic({"topics": []}) == "style_mimic"
    assert route_after_style({"style_card": {"persona": "p"}}) == "human_gate"  # 7 字段不全
    assert route_after_publish({"publish_plan": {"platform": "x", "best_time": "09:00", "tags": [], "hashtags": [], "description": ""}}) == "data_analyst"


def test_injected_fabricated_trend_hits_trace_gate(monkeypatch):
    """注入一条编造热点 → 溯源门 HALT 走 human_gate（验收）。"""
    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 1.0, "pass": False, "reason": "编造热点"},
    )
    state = {"script": _script("火星移民计划今日获批，人类将迁居火星。" * 3)}
    assert route_after_script(state) == "human_gate"


def test_loop_rounds_two_revisits_topic_planner(monkeypatch):
    """loop_rounds=2：整图跑 3 遍选题（初始 + 2 轮回流）后终止，loop_count=2。"""
    calls: list[str] = []

    async def fake_call(tool, **kw):
        calls.append(tool)
        if tool == "trend_hunter":
            return [{"title": "t", "platform": "douyin", "heat": 100, "url": "u", "category": "美妆"}]
        if tool == "topic_planner":
            return [{"title": "t", "score": 8.0, "reason": "r"}]
        if tool == "style_mimic":
            return {
                "persona": "p", "voice": "v", "catchphrases": [], "sentence_patterns": [],
                "pacing": "", "narrative_structure": "", "visual_style": "",
            }
        if tool == "script_writer":
            return {"body": "b", "scenes": [{"visual": "v", "narration": "n", "duration": 3}], "duration": 3}
        if tool == "publish_optimizer":
            return {"platform": "x", "best_time": "09:00", "tags": [], "hashtags": [], "description": ""}
        if tool == "data_analyst":
            return {"report": "r", "metrics": {"total_views": 1}, "benchmark": {"quartile": 1}, "anomalies": []}
        return {}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    result = asyncio.run(app.ainvoke({"account_profile": "美妆博主", "loop_rounds": 2}))
    assert result["loop_count"] == 3
    assert calls.count("topic_planner") == 3  # 初始 + 2 轮额外回流


def test_style_mimic_node_forwards_samples(monkeypatch):
    """md 附件作为 samples 前置：style_mimic_node 把 state.samples 传给 tool。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool: str, **kw):
        calls[tool] = kw
        return {"persona": "x"}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(
        style_mimic_node(
            {"account_profile": "p", "topics": [], "samples": "md 文本样本"}
        )
    )
    assert calls["style_mimic"]["samples"] == "md 文本样本"


def test_script_writer_node_forwards_source_material(monkeypatch):
    """script_writer_node 把 trends/samples/profile 传给 script_writer tool。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool: str, **kw):
        calls[tool] = kw
        return {"body": "b", "scenes": [{"visual": "v", "narration": "n", "duration": 3}], "duration": 3}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(
        script_writer_node(
            {
                "style_card": {"topic": "美妆"},
                "trends": [{"title": "秋冬显白口红"}],
                "samples": "姐妹们这期",
                "account_profile": "美妆博主",
            }
        )
    )
    kw = calls["script_writer"]
    assert kw["trends"] == [{"title": "秋冬显白口红"}]
    assert kw["samples"] == "姐妹们这期"
    assert kw["profile"] == "美妆博主"


# ——— P5-E candidate_videos / transcripts 转发 / v2 回流 ———


def test_trend_hunter_node_records_candidate_videos(monkeypatch):
    """trend_hunter_node 抓完 trends 后记代表性视频入 candidate_videos。"""

    async def fake_call(tool: str, **kw):
        return [
            {"title": "t", "platform": "bilibili", "heat": 10, "url": "https://bilibili.com/BV1", "category": ""}
        ]

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    out = asyncio.run(trend_hunter_node({"account_profile": "美妆"}))
    assert out["candidate_videos"] == [
        {"title": "t", "platform": "bilibili", "url": "https://bilibili.com/BV1", "heat": 10.0}
    ]


def test_style_mimic_node_forwards_transcripts(monkeypatch):
    """style_mimic_node 把 transcripts（转录逐字稿）转发给 style_mimic tool。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool: str, **kw):
        calls[tool] = kw
        return {"persona": "x"}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(
        style_mimic_node(
            {"account_profile": "p", "topics": [], "samples": "", "transcripts": {"u": "text"}}
        )
    )
    assert calls["style_mimic"]["transcripts"] == {"u": "text"}


def test_script_writer_node_forwards_transcripts(monkeypatch):
    """script_writer_node 把 transcripts 转发给 script_writer tool（并入可溯源素材）。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool: str, **kw):
        calls[tool] = kw
        return {"body": "b", "scenes": [{"visual": "v", "narration": "n", "duration": 3}], "duration": 3}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(
        script_writer_node(
            {
                "style_card": {"topic": "美妆"},
                "trends": [],
                "samples": "",
                "account_profile": "p",
                "transcripts": {"u": "text"},
            }
        )
    )
    assert calls["script_writer"]["transcripts"] == {"u": "text"}


def test_data_analyst_node_forwards_previous_script(monkeypatch):
    """data_analyst_node 把 v1_script/script/transcripts 传给 data_analyst（v1 vs v2 对照）。"""
    calls: dict[str, dict] = {}

    async def fake_call(tool: str, **kw):
        calls[tool] = kw
        return {"report": "r", "metrics": {"total_views": 1}, "benchmark": {"quartile": 1}, "anomalies": []}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    asyncio.run(
        data_analyst_node(
            {
                "publish_plan": {},
                "script": {"body": "v2"},
                "v1_script": {"body": "v1"},
                "transcripts": {"u": "text"},
            }
        )
    )
    kw = calls["data_analyst"]
    assert kw["previous_script"] == {"body": "v1"}
    assert kw["script"] == {"body": "v2"}
    assert kw["transcripts"] == {"u": "text"}


def test_v2_app_runs_tail_only(monkeypatch):
    """v2 回流：从 style_mimic 起步，不复跑 trend_hunter/topic_planner。"""
    calls: list[str] = []

    async def fake_call(tool: str, **kw):
        calls.append(tool)
        if tool == "style_mimic":
            return {
                "persona": "p", "voice": "v", "catchphrases": [], "sentence_patterns": [],
                "pacing": "", "narrative_structure": "", "visual_style": "",
            }
        if tool == "script_writer":
            return {"body": "b", "scenes": [{"visual": "v", "narration": "n", "duration": 3}], "duration": 3}
        if tool == "publish_optimizer":
            return {"platform": "x", "best_time": "09:00", "tags": [], "hashtags": [], "description": ""}
        if tool == "data_analyst":
            return {"report": "r", "metrics": {"total_views": 1}, "benchmark": {"quartile": 1}, "anomalies": []}
        return {}

    monkeypatch.setattr("src.orchestrator.graph.call_tool", fake_call)
    result = asyncio.run(
        v2_app.ainvoke(
            {"account_profile": "美妆", "trends": [], "topics": [], "transcripts": {"u": "text"}}
        )
    )
    assert calls == ["style_mimic", "script_writer", "publish_optimizer", "data_analyst"]
    assert result["current_stage"] == "data_analyst"
