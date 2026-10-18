"""多 server 路由测试 — 外部 MCP skill（P2）。"""

import asyncio

import pytest
from fastmcp.client.transports import (
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)

from src import mcp_client
from src.mcp_guard import GuardDenied


def test_transport_for_stdio():
    t = mcp_client._transport_for({"transport": "stdio", "command": "python", "args": ["-m", "x"]})
    assert isinstance(t, StdioTransport)


def test_transport_for_http():
    t = mcp_client._transport_for({"transport": "http", "url": "http://x/mcp"})
    assert isinstance(t, StreamableHttpTransport)


def test_transport_for_sse():
    t = mcp_client._transport_for({"transport": "sse", "url": "http://x/mcp"})
    assert isinstance(t, SSETransport)


def test_bare_name_routes_local(monkeypatch):
    monkeypatch.setattr(mcp_client, "_servers_loaded", True)
    monkeypatch.setattr(mcp_client, "_servers", {})
    calls = []

    async def fake_call(transport, tool, kwargs):
        calls.append(tool)
        return {"ok": True}

    monkeypatch.setattr(mcp_client, "_call", fake_call)
    out = asyncio.run(mcp_client.call_tool("trend_hunter", platform="bilibili"))
    assert out == {"ok": True}
    assert calls == ["trend_hunter"]  # 裸名不 split


def test_dotted_name_routes_external(monkeypatch):
    monkeypatch.setattr(mcp_client, "_servers_loaded", True)
    monkeypatch.setattr(mcp_client, "_servers", {"ext": {"transport": "http", "url": "http://x"}})
    calls = []

    async def fake_call(transport, tool, kwargs):
        calls.append((tool, kwargs))
        return "result"

    monkeypatch.setattr(mcp_client, "_call", fake_call)
    out = asyncio.run(mcp_client.call_tool("ext.greet", name="hi"))
    assert out == "result"
    assert calls == [("greet", {"name": "hi"})]  # 拆成 (tool, kwargs)


def test_unknown_external_raises(monkeypatch):
    monkeypatch.setattr(mcp_client, "_servers_loaded", True)
    monkeypatch.setattr(mcp_client, "_servers", {})
    with pytest.raises(GuardDenied) as exc:
        asyncio.run(mcp_client.call_tool("nope.tool"))
    assert exc.value.gate == "G1"
