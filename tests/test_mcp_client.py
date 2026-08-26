"""MCP 客户端真接测试 — call_tool 走 FastMCP in-memory 协议（非 dict 查表）。"""

import asyncio

from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

from src import mcp_client


def test_call_tool_is_async_and_returns_parsed_json_via_mcp():
    """call_tool 经 MCP 协议调 trend_hunter，返回解析后的 list（douyin 登录态源→[]）。"""
    out = asyncio.run(mcp_client.call_tool("trend_hunter", platform="douyin"))
    assert isinstance(out, list)


def test_mcp_server_exposes_six_tools():
    """FastMCP server 经 MCP 工具发现协议暴露 6 tool，名字与 graph 节点一致。"""

    async def _names() -> set[str]:
        from src.mcp_server import mcp

        async with Client(FastMCPTransport(mcp=mcp)) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(_names()) == {
        "trend_hunter",
        "topic_planner",
        "style_mimic",
        "script_writer",
        "publish_optimizer",
        "data_analyst",
    }
