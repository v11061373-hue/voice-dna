"""LangGraph 编排 — 表达基因（Voice DNA）社媒 Agent 线性 pipeline。

trend_hunter → topic_planner → style_mimic → script_writer →
  [脚本质量门] → publish_optimizer → data_analyst → [分析质量门] → END
门 HALT / 节点失败 → human_gate。循环边（数据分析→选题策划回流）可选，
loop_rounds=0 默认关（线性一次跑完）。

参照 BidForge src/orchestrator/graph.py：节点返回 partial dict、条件边 +
路由函数、质量门独立文件、InMemorySaver checkpoint。
差异：节点调 MCP tool（JSON 进出）非 import 内部函数。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from src.mcp_client import call_tool
from src.orchestrator.quality_gate import GateResult, run_quality_gates
from src.schemas import SocialMediaState
from src.tools import trend_hunter


async def _run_tool(tool_name: str, **kwargs: Any) -> dict[str, Any]:
    """调 MCP tool；失败返回 failed 状态，不抛异常。"""
    try:
        return {"status": "ok", "data": await call_tool(tool_name, **kwargs)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc)}


def _ok(stage: str, field: str, data: Any) -> dict[str, Any]:
    return {"current_stage": stage, "stage_status": "ok", field: data}


def _fail(stage: str, err: str) -> dict[str, Any]:
    return {"current_stage": stage, "stage_status": "failed", "errors": [err]}


async def trend_hunter_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool(
        "trend_hunter",
        profile=state.get("account_profile", ""),
        enabled=state.get("enabled_sources"),
    )
    if r["status"] != "ok":
        return _fail("trend_hunter", r["error"])
    trends = r["data"]
    return {
        "current_stage": "trend_hunter",
        "stage_status": "ok",
        "trends": trends,
        "candidate_videos": trend_hunter.select_candidate_videos(trends),
    }


async def topic_planner_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool(
        "topic_planner",
        trends=state.get("trends", []),
        analytics=state.get("analytics", {}),
    )
    return _ok("topic_planner", "topics", r["data"]) if r["status"] == "ok" else _fail("topic_planner", r["error"])


async def style_mimic_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool(
        "style_mimic",
        profile=state.get("account_profile", ""),
        topics=state.get("topics", []),
        samples=state.get("samples", ""),
        transcripts=state.get("transcripts", {}),
    )
    return _ok("style_mimic", "style_card", r["data"]) if r["status"] == "ok" else _fail("style_mimic", r["error"])


async def script_writer_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool(
        "script_writer",
        style_card=state.get("style_card", {}),
        trends=state.get("trends", []),
        samples=state.get("samples", ""),
        profile=state.get("account_profile", ""),
        transcripts=state.get("transcripts", {}),
    )
    return _ok("script_writer", "script", r["data"]) if r["status"] == "ok" else _fail("script_writer", r["error"])


async def publish_optimizer_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("publish_optimizer", script=state.get("script", {}))
    return _ok("publish_optimizer", "publish_plan", r["data"]) if r["status"] == "ok" else _fail("publish_optimizer", r["error"])


async def data_analyst_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool(
        "data_analyst",
        publish_plan=state.get("publish_plan", {}),
        script=state.get("script", {}),
        previous_script=state.get("v1_script"),
        transcripts=state.get("transcripts", {}),
    )
    if r["status"] != "ok":
        return _fail("data_analyst", r["error"])
    return {
        "current_stage": "data_analyst",
        "stage_status": "ok",
        "analytics": r["data"],
        "loop_count": state.get("loop_count", 0) + 1,
    }


def human_gate_node(state: SocialMediaState) -> dict[str, Any]:
    return {"current_stage": "human_gate", "stage_status": state.get("stage_status", "ok")}


def _route(stage: str, next_node: str, state: SocialMediaState) -> str:
    """质量门路由：节点失败或 5 门 HALT 走 human_gate，否则下一节点。"""
    if state.get("stage_status") == "failed":
        return "human_gate"
    if run_quality_gates(stage, state) == GateResult.HALT:
        return "human_gate"
    return next_node


def route_after_trend(state: SocialMediaState) -> str:
    return _route("trend_hunter", "topic_planner", state)


def route_after_topic(state: SocialMediaState) -> str:
    return _route("topic_planner", "style_mimic", state)


def route_after_style(state: SocialMediaState) -> str:
    return _route("style_mimic", "script_writer", state)


def route_after_script(state: SocialMediaState) -> str:
    return _route("script_writer", "publish_optimizer", state)


def route_after_publish(state: SocialMediaState) -> str:
    return _route("publish_optimizer", "data_analyst", state)


def route_after_analytics(state: SocialMediaState) -> str:
    # 回流（可选）：loop_rounds 是额外回流次数。loop_count 是已完成分析遍数，
    # 额外回流数 = loop_count - 1，未达 loop_rounds 则回选题策划。
    if state.get("loop_rounds", 0) > 0 and state.get("loop_count", 0) <= state.get("loop_rounds", 0):
        return _route("data_analyst", "topic_planner", state)
    return _route("data_analyst", "__end__", state)


_graph = StateGraph(SocialMediaState)
_graph.add_node("trend_hunter", trend_hunter_node)
_graph.add_node("topic_planner", topic_planner_node)
_graph.add_node("style_mimic", style_mimic_node)
_graph.add_node("script_writer", script_writer_node)
_graph.add_node("publish_optimizer", publish_optimizer_node)
_graph.add_node("data_analyst", data_analyst_node)
_graph.add_node("human_gate", human_gate_node)

_graph.set_entry_point("trend_hunter")

_graph.add_conditional_edges(
    "trend_hunter",
    route_after_trend,
    {"topic_planner": "topic_planner", "human_gate": "human_gate"},
)
_graph.add_conditional_edges(
    "topic_planner",
    route_after_topic,
    {"style_mimic": "style_mimic", "human_gate": "human_gate"},
)
_graph.add_conditional_edges(
    "style_mimic",
    route_after_style,
    {"script_writer": "script_writer", "human_gate": "human_gate"},
)
_graph.add_conditional_edges(
    "script_writer",
    route_after_script,
    {"publish_optimizer": "publish_optimizer", "human_gate": "human_gate"},
)
_graph.add_conditional_edges(
    "publish_optimizer",
    route_after_publish,
    {"data_analyst": "data_analyst", "human_gate": "human_gate"},
)
_graph.add_conditional_edges(
    "data_analyst",
    route_after_analytics,
    {"human_gate": "human_gate", "__end__": END, "topic_planner": "topic_planner"},
)
_graph.add_edge("human_gate", END)

# ponytail: 不挂 checkpointer（单次 ainvoke 内循环用 state 计数即可终止）。
app = _graph.compile()


# ——— v2 回流（P5-E）：带 transcripts 素材二次跑，只重跑 style→script→publish→analyst ———

# v2 不复跑 trend_hunter/topic_planner（复用 v1 trends/topics），故入口 style_mimic，
# 且 analytics 不回流（无 topic_planner 节点）。route_after_analytics 的 topic_planner
# 分支只在 loop_rounds>0 触发，v2 不设 loop_rounds，故不会命中。
def _route_after_analytics_v2(state: SocialMediaState) -> str:
    return _route("data_analyst", "__end__", state)


_v2_graph = StateGraph(SocialMediaState)
_v2_graph.add_node("style_mimic", style_mimic_node)
_v2_graph.add_node("script_writer", script_writer_node)
_v2_graph.add_node("publish_optimizer", publish_optimizer_node)
_v2_graph.add_node("data_analyst", data_analyst_node)
_v2_graph.add_node("human_gate", human_gate_node)

_v2_graph.set_entry_point("style_mimic")
_v2_graph.add_conditional_edges(
    "style_mimic", route_after_style, {"script_writer": "script_writer", "human_gate": "human_gate"}
)
_v2_graph.add_conditional_edges(
    "script_writer", route_after_script, {"publish_optimizer": "publish_optimizer", "human_gate": "human_gate"}
)
_v2_graph.add_conditional_edges(
    "publish_optimizer", route_after_publish, {"data_analyst": "data_analyst", "human_gate": "human_gate"}
)
_v2_graph.add_conditional_edges(
    "data_analyst", _route_after_analytics_v2, {"human_gate": "human_gate", "__end__": END}
)
_v2_graph.add_edge("human_gate", END)

v2_app = _v2_graph.compile()
