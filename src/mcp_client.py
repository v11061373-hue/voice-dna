"""MCP 客户端 — 多 server 按 tool name 路由。

本地 voice-dna 走 in-memory（FastMCPTransport 直连 mcp 对象）；外部 skill 走
plugins/mcp_servers.json 配置的 stdio / http / sse server。tool 命名：
  裸名           → 本地 voice-dna（trend_hunter …）
  "server.tool"  → 外部 server 的 tool
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import (
    FastMCPTransport,
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)

from src import llm
from src.mcp_guard import TOOL_ACTIONS, GuardDenied, MCPGuard, default_whitelist
from src.mcp_server import mcp

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVERS_FILE = _REPO_ROOT / "plugins" / "mcp_servers.json"

_servers: dict[str, dict[str, Any]] = {}
_servers_loaded = False

# 五门网关（G1–G5）单例，治理每次本地 tool 调用。
# G4 成本预算 = token 预算（VOICEDNA_TOKEN_BUDGET，空=不限）：call_tool 量调用前后
# token 差后 charge，下一次调用超限即 G4 拒绝。cost/time/retry 预算暂不设。
_AUDIT_LOG = _REPO_ROOT / "logs" / "audit.jsonl"
_AUDIT_SECRET = os.environ.get("VOICEDNA_AUDIT_SECRET", "voice-dna-dev")
_TOKEN_BUDGET = os.environ.get("VOICEDNA_TOKEN_BUDGET", "")
_guard = MCPGuard(
    whitelist=default_whitelist(),
    cost_budget=float(_TOKEN_BUDGET) if _TOKEN_BUDGET else None,
    audit_log_path=_AUDIT_LOG,
    audit_secret=_AUDIT_SECRET,
)


def load_servers() -> None:
    """加载外部 MCP server 配置（幂等，改配置后重启生效）。"""
    global _servers_loaded
    if _servers_loaded:
        return
    if SERVERS_FILE.is_file():
        try:
            data = json.loads(SERVERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for s in data:
                    name = str(s.get("name") or "")
                    if name:
                        _servers[name] = s
        except Exception:  # noqa: BLE001, S110 — servers.json 损坏/缺失不得阻断
            pass
    _servers_loaded = True


def _transport_for(server: dict[str, Any]) -> Any:
    """按配置构造 transport：stdio（command+args）/ http / sse（url）。"""
    kind = server.get("transport", "stdio")
    if kind == "http":
        return StreamableHttpTransport(url=server["url"])
    if kind == "sse":
        return SSETransport(url=server["url"])
    return StdioTransport(
        command=server["command"],
        args=list(server.get("args") or []),
        env=server.get("env"),
    )


async def _call(client_transport: Any, tool_name: str, kwargs: dict[str, Any]) -> Any:
    async with Client(client_transport) as client:
        result = await client.call_tool(tool_name, kwargs)
    sc = result.structured_content
    if isinstance(sc, dict) and list(sc) == ["result"]:
        return sc["result"]
    return sc


async def call_tool(tool_name: str, **kwargs: Any) -> Any:
    """按 tool name 路由：裸名 → 本地，`server.tool` → 外部 server。

    本地 tool 走 G1–G5 五门（白名单 / 动作分类 / 风险 / 预算限流 / 审计）。
    G4 成本预算 = token 预算：调用前后量 `llm.total_tokens()` 差，charge 后付费，
    累计超限则下一次调用被 G4 拒绝。外部 server.tool 只走 G1 server 注册检查
    （pipeline 不调外部 tool，审计/预算暂不覆盖）。
    """
    load_servers()
    if "." in tool_name:
        server_name, tool = tool_name.split(".", 1)
        if server_name not in _servers:
            raise GuardDenied("G1", f"未注册的 MCP server: {server_name}")
        return await _call(_transport_for(_servers[server_name]), tool, kwargs)
    d = _guard.check(
        agent_id=tool_name,
        tool_name=tool_name,
        action=TOOL_ACTIONS.get(tool_name, "read"),
        cost=0.0,
        retry=0,
    )
    if not d.allowed:
        raise GuardDenied(d.gate, d.reason)
    before = llm.total_tokens()
    result = await _call(FastMCPTransport(mcp=mcp), tool_name, kwargs)
    _guard.charge(tool_name, float(llm.total_tokens() - before))
    return result


async def list_tools() -> list[dict[str, Any]]:
    """列出本地 + 外部 server 的全部 tool。外部命名 `server.tool`。"""
    load_servers()
    tools: list[dict[str, Any]] = []
    async with Client(FastMCPTransport(mcp=mcp)) as client:
        for t in await client.list_tools():
            tools.append({"name": t.name, "inputSchema": t.inputSchema, "server": "voice-dna"})
    for name, cfg in _servers.items():
        try:
            async with Client(_transport_for(cfg)) as client:
                for t in await client.list_tools():
                    tools.append(
                        {"name": f"{name}.{t.name}", "inputSchema": t.inputSchema, "server": name}
                    )
        except Exception:  # noqa: BLE001, S112 — 外部 server 不可达则跳过
            continue
    return tools
