"""五门安全网关（G1–G5）—— 自 bidforge-v4/src/mcp_guard 复制适配。

对外：
  MCPGuard        五门管道（库，供 P4-C agent 编排调用）
  GuardDenied     工具调用被拒的结构化异常（call_tool 抛出）
  VOICE_DNA_TOOLS 9 本地 tool 名（call_tool 白名单判定）
  default_whitelist / TOOL_ACTIONS
"""

from src.mcp_guard.gateway import (
    TOOL_ACTIONS,
    VOICE_DNA_TOOLS,
    GuardDecision,
    GuardDenied,
    MCPGuard,
    default_whitelist,
)

__all__ = [
    "TOOL_ACTIONS",
    "VOICE_DNA_TOOLS",
    "GuardDecision",
    "GuardDenied",
    "MCPGuard",
    "default_whitelist",
]
