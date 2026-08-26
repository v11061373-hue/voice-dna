"""FastMCP 服务器 — 表达基因 6 tool 统一 JSON 进出。

真接 MCP：FastMCP 注册 6 tool，mcp_client 用 in-memory Client 连本 server
（FastMCPTransport 直连 mcp 对象），不起 stdio 子进程。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from src.tools import (
    data_analyst,
    publish_optimizer,
    script_writer,
    style_mimic,
    topic_planner,
    trend_hunter,
)

mcp = FastMCP("voice-dna")


@mcp.tool(name="trend_hunter")
def _trend_hunter(profile: str = "", platform: str = "") -> list[dict[str, Any]]:
    return trend_hunter.run(profile=profile, platform=platform)


@mcp.tool(name="topic_planner")
def _topic_planner(trends: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return topic_planner.run(trends=trends or [])


@mcp.tool(name="style_mimic")
def _style_mimic(
    profile: str = "",
    topics: list[dict[str, Any]] | None = None,
    samples: str = "",
) -> dict[str, Any]:
    return style_mimic.run(profile=profile, topics=topics or [], samples=samples)


@mcp.tool(name="script_writer")
def _script_writer(style_card: dict[str, Any] | None = None) -> dict[str, Any]:
    return script_writer.run(style_card=style_card or {})


@mcp.tool(name="publish_optimizer")
def _publish_optimizer(script: dict[str, Any] | None = None) -> dict[str, Any]:
    return publish_optimizer.run(script=script or {})


@mcp.tool(name="data_analyst")
def _data_analyst(
    publish_plan: dict[str, Any] | None = None,
    views: list[float] | None = None,
) -> dict[str, Any]:
    return data_analyst.run(publish_plan=publish_plan, views=views)
