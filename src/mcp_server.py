"""FastMCP 服务器 — 表达基因 8 tool 统一 JSON 进出。

真接 MCP：FastMCP 注册 8 tool，mcp_client 用 in-memory Client 连本 server
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
    transcribe,
    trend_hunter,
    video_download,
    video_vision,
)

mcp = FastMCP("voice-dna")


@mcp.tool(name="trend_hunter")
def _trend_hunter(
    profile: str = "",
    platform: str = "",
    enabled: list[str] | None = None,
) -> list[dict[str, Any]]:
    return trend_hunter.run(profile=profile, platform=platform, enabled=enabled)


@mcp.tool(name="topic_planner")
def _topic_planner(
    trends: list[dict[str, Any]] | None = None,
    analytics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return topic_planner.run(trends=trends or [], analytics=analytics)


@mcp.tool(name="style_mimic")
def _style_mimic(
    profile: str = "",
    topics: list[dict[str, Any]] | None = None,
    samples: str = "",
    transcripts: dict[str, str] | None = None,
) -> dict[str, Any]:
    return style_mimic.run(profile=profile, topics=topics or [], samples=samples, transcripts=transcripts or {})


@mcp.tool(name="script_writer")
def _script_writer(
    style_card: dict[str, Any] | None = None,
    trends: list[dict[str, Any]] | None = None,
    samples: str = "",
    profile: str = "",
    transcripts: dict[str, str] | None = None,
) -> dict[str, Any]:
    return script_writer.run(
        style_card=style_card or {}, trends=trends or [], samples=samples, profile=profile, transcripts=transcripts or {}
    )


@mcp.tool(name="publish_optimizer")
def _publish_optimizer(script: dict[str, Any] | None = None) -> dict[str, Any]:
    return publish_optimizer.run(script=script or {})


@mcp.tool(name="data_analyst")
def _data_analyst(
    publish_plan: dict[str, Any] | None = None,
    views: list[float] | None = None,
    script: dict[str, Any] | None = None,
    previous_script: dict[str, Any] | None = None,
    transcripts: dict[str, str] | None = None,
) -> dict[str, Any]:
    return data_analyst.run(
        publish_plan=publish_plan, views=views, script=script, previous_script=previous_script, transcripts=transcripts
    )


@mcp.tool(name="transcribe")
def _transcribe(source: str = "", backend: str = "local") -> dict[str, Any]:
    return transcribe.run(source=source, backend=backend)


@mcp.tool(name="video_download")
def _video_download(url: str = "") -> dict[str, Any]:
    return video_download.run(url=url)


@mcp.tool(name="video_vision")
def _video_vision(path: str = "", fps: float = 1 / 3) -> dict[str, Any]:
    return video_vision.run(path=path, fps=fps)
