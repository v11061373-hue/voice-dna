"""MCP 客户端真接测试 — call_tool 走 FastMCP in-memory 协议（非 dict 查表）。"""

import asyncio
import json
import os
import tempfile

import pytest
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

from src import mcp_client
from src.mcp_guard import GuardDenied, MCPGuard, default_whitelist


def test_call_tool_is_async_and_returns_parsed_json_via_mcp(monkeypatch):
    """call_tool 经 MCP 协议调 trend_hunter，返回解析后的 list。"""
    monkeypatch.setattr("src.tools.trend_hunter.run", lambda **kw: [])
    out = asyncio.run(mcp_client.call_tool("trend_hunter", platform="douyin"))
    assert isinstance(out, list)


def test_mcp_server_exposes_nine_tools():
    """FastMCP server 经 MCP 工具发现协议暴露 9 tool，名字与 graph 节点一致。"""

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
        "transcribe",
        "video_download",
        "video_vision",
    }


def test_list_tools_returns_nine_with_input_schema(monkeypatch):
    """mcp_client.list_tools 返回 9 本地 tool，各带 inputSchema（隔离外部 server）。"""
    monkeypatch.setattr(mcp_client, "_servers_loaded", True)
    monkeypatch.setattr(mcp_client, "_servers", {})
    tools = asyncio.run(mcp_client.list_tools())
    assert {t["name"] for t in tools} == {
        "trend_hunter",
        "topic_planner",
        "style_mimic",
        "script_writer",
        "publish_optimizer",
        "data_analyst",
        "transcribe",
        "video_download",
        "video_vision",
    }
    assert all("inputSchema" in t for t in tools)


def test_call_tool_charges_token_delta(monkeypatch):
    """call_tool 后付费：量 call 前后 token 差，charge 进 G4 成本预算。"""
    from src import llm

    g = MCPGuard(whitelist=default_whitelist())
    monkeypatch.setattr(mcp_client, "_guard", g)
    spent = {"t": 0}

    def fake_total():
        spent["t"] += 7
        return spent["t"]

    monkeypatch.setattr(llm, "total_tokens", fake_total)
    monkeypatch.setattr("src.tools.trend_hunter.run", lambda **kw: [])
    asyncio.run(mcp_client.call_tool("trend_hunter", platform="douyin"))
    assert g._cost_spent.get("trend_hunter", 0.0) == 7.0


def test_call_tool_denies_when_token_budget_exceeded(monkeypatch):
    """成本预算超限后，call_tool 下一次调用被 G4 拒绝。"""
    g = MCPGuard(whitelist=default_whitelist(), cost_budget=5.0)
    monkeypatch.setattr(mcp_client, "_guard", g)
    g.charge("trend_hunter", 100.0)
    with pytest.raises(GuardDenied) as e:
        asyncio.run(mcp_client.call_tool("trend_hunter", platform="douyin"))
    assert e.value.gate == "G4"


def test_call_tool_audits_local_call(monkeypatch):
    """call_tool 真接 G5 审计：本地 tool 调用落 JSONL + HMAC。"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "audit.jsonl")
        g = MCPGuard(whitelist=default_whitelist(), audit_log_path=path, audit_secret="s3cret")
        monkeypatch.setattr(mcp_client, "_guard", g)
        monkeypatch.setattr("src.tools.trend_hunter.run", lambda **kw: [])
        asyncio.run(mcp_client.call_tool("trend_hunter", platform="douyin"))
        with open(path, encoding="utf-8") as f:
            entry = json.loads(f.read().strip())
        assert "hmac" in entry
        assert entry["data"]["tool_name"] == "trend_hunter"
