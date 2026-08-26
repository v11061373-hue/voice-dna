"""MCP 客户端 — in-memory Client 连 FastMCP server，真走 MCP 协议。

节点经 call_tool 统一 JSON 进出；FastMCPTransport 直连 mcp server 对象，
不起 stdio 子进程。call_tool 是 async（MCP 协议异步）。
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

from src.mcp_server import mcp


async def call_tool(tool_name: str, **kwargs: Any) -> Any:
    """异步调一个 MCP tool，返回结构化值（dict / list）。

    FastMCP in-memory 传输把 list 返回值包成 {"result": [...]}，dict 原样返回；
    这里统一解包。
    """
    async with Client(FastMCPTransport(mcp=mcp)) as client:
        result = await client.call_tool(tool_name, kwargs)
    sc = result.structured_content
    if isinstance(sc, dict) and list(sc) == ["result"]:
        return sc["result"]
    return sc
