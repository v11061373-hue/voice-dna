"""LangGraph 编排骨架测试。

参照 BidForge 六节点 pipeline：热点猎人→选题策划→风格模仿→脚本文案→
发布优化→数据分析 + human_gate 兜底。MVP 线性边（循环边留步骤5）。
"""

import asyncio

import httpx

from src.orchestrator.graph import app, route_after_analytics, route_after_script
from src.tools import trend_hunter


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

    热点源断网时 trend_hunter 返回空，管线仍线性走完。
    """
    def _offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(trend_hunter, "_fetch_popular", _offline)
    result = asyncio.run(app.ainvoke({"account_profile": "美妆博主"}))
    assert result["current_stage"] == "data_analyst"
    assert result["stage_status"] == "ok"


def test_script_quality_gate_halts_on_empty_script():
    """脚本质量门（腿①确定性+腿②LLM-as-judge 骨架）：空脚本 HALT 走 human_gate。"""
    assert route_after_script({"script": {}}) == "human_gate"
    assert route_after_script({"script": {"body": "有效脚本"}}) == "publish_optimizer"


def test_analytics_quality_gate_routes_to_end():
    """数据分析质量门（腿③统计异常骨架）：正常产出走 END。"""
    assert route_after_analytics({"analytics": {"report": "正常"}}) == "__end__"
    assert route_after_analytics({"analytics": {}}) == "human_gate"
