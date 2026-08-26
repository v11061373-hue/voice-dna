"""LangGraph 编排 — 表达基因（Voice DNA）社媒 Agent 线性 pipeline。

trend_hunter → topic_planner → style_mimic → script_writer →
  [脚本质量门] → publish_optimizer → data_analyst → [分析质量门] → END
门 HALT / 节点失败 → human_gate。循环边（数据分析→选题策划回流）留步骤5。

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
    r = await _run_tool("trend_hunter", profile=state.get("account_profile", ""))
    return _ok("trend_hunter", "trends", r["data"]) if r["status"] == "ok" else _fail("trend_hunter", r["error"])


async def topic_planner_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("topic_planner", trends=state.get("trends", []))
    return _ok("topic_planner", "topics", r["data"]) if r["status"] == "ok" else _fail("topic_planner", r["error"])


async def style_mimic_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("style_mimic", profile=state.get("account_profile", ""), topics=state.get("topics", []))
    return _ok("style_mimic", "style_card", r["data"]) if r["status"] == "ok" else _fail("style_mimic", r["error"])


async def script_writer_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("script_writer", style_card=state.get("style_card", {}))
    return _ok("script_writer", "script", r["data"]) if r["status"] == "ok" else _fail("script_writer", r["error"])


async def publish_optimizer_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("publish_optimizer", script=state.get("script", {}))
    return _ok("publish_optimizer", "publish_plan", r["data"]) if r["status"] == "ok" else _fail("publish_optimizer", r["error"])


async def data_analyst_node(state: SocialMediaState) -> dict[str, Any]:
    r = await _run_tool("data_analyst", publish_plan=state.get("publish_plan", {}))
    return _ok("data_analyst", "analytics", r["data"]) if r["status"] == "ok" else _fail("data_analyst", r["error"])


def human_gate_node(state: SocialMediaState) -> dict[str, Any]:
    return {"current_stage": "human_gate", "stage_status": state.get("stage_status", "ok")}


def route_after_script(state: SocialMediaState) -> str:
    """脚本质量门：失败或 HALT 走 human_gate，否则 publish_optimizer。"""
    if state.get("stage_status") == "failed":
        return "human_gate"
    if run_quality_gates("script_writer", state) == GateResult.HALT:
        return "human_gate"
    return "publish_optimizer"


def route_after_analytics(state: SocialMediaState) -> str:
    """分析质量门：失败或 HALT 走 human_gate，否则 END。"""
    if state.get("stage_status") == "failed":
        return "human_gate"
    if run_quality_gates("data_analyst", state) == GateResult.HALT:
        return "human_gate"
    return "__end__"


_graph = StateGraph(SocialMediaState)
_graph.add_node("trend_hunter", trend_hunter_node)
_graph.add_node("topic_planner", topic_planner_node)
_graph.add_node("style_mimic", style_mimic_node)
_graph.add_node("script_writer", script_writer_node)
_graph.add_node("publish_optimizer", publish_optimizer_node)
_graph.add_node("data_analyst", data_analyst_node)
_graph.add_node("human_gate", human_gate_node)

_graph.set_entry_point("trend_hunter")

_graph.add_edge("trend_hunter", "topic_planner")
_graph.add_edge("topic_planner", "style_mimic")
_graph.add_edge("style_mimic", "script_writer")
_graph.add_conditional_edges(
    "script_writer",
    route_after_script,
    {"publish_optimizer": "publish_optimizer", "human_gate": "human_gate"},
)
_graph.add_edge("publish_optimizer", "data_analyst")
_graph.add_conditional_edges(
    "data_analyst",
    route_after_analytics,
    {"human_gate": "human_gate", "__end__": END},
)
_graph.add_edge("human_gate", END)

# ponytail: MVP 线性无循环，不挂 checkpointer；步骤5 加循环边时再挂 InMemorySaver。
app = _graph.compile()
