"""五门安全网关测试 — G1 白名单 / G2·G3 动作风险 / G4 预算 / G5 审计 / 接线。"""

import asyncio
import json
import os
import tempfile

import pytest

from src.mcp_guard import GuardDenied, MCPGuard, default_whitelist


def _guard(**kw) -> MCPGuard:
    return MCPGuard(whitelist=default_whitelist(), **kw)


def test_g1_rejects_unknown_tool():
    d = _guard().check(agent_id="trend_hunter", tool_name="secret_delete", action="read")
    assert not d.allowed
    assert d.gate == "G1"


def test_read_and_draft_allow():
    g = _guard()
    assert g.check(agent_id="trend_hunter", tool_name="trend_hunter", action="read").allowed
    assert g.check(agent_id="style_mimic", tool_name="style_mimic", action="draft").allowed


def test_external_write_requires_approval():
    g = _guard()
    g.register("trend_hunter", "weibo_post")
    d = g.check(agent_id="trend_hunter", tool_name="weibo_post", action="external_write")
    assert not d.allowed
    assert d.gate == "G3"


def test_budget_exceeded_rejects():
    g = _guard(cost_budget=10.0)
    assert g.check(agent_id="trend_hunter", tool_name="trend_hunter", action="read", cost=6.0).allowed
    d = g.check(agent_id="trend_hunter", tool_name="trend_hunter", action="read", cost=5.0)
    assert not d.allowed
    assert d.gate == "G4"


def test_retry_budget_exceeded_rejects():
    g = _guard(max_retries=2)
    d = g.check(agent_id="topic_planner", tool_name="topic_planner", action="read", retry=3)
    assert not d.allowed
    assert d.gate == "G4"


def test_charge_then_budget_denies_next():
    """charge 后付费累加 cost，下一次 check 的成本预算据此拒绝。"""
    g = _guard(cost_budget=100.0)
    g.charge("trend_hunter", 120.0)
    d = g.check(agent_id="trend_hunter", tool_name="trend_hunter", action="read", cost=0.0)
    assert not d.allowed
    assert d.gate == "G4"


def test_audit_writes_jsonl_with_hmac():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "audit.jsonl")
        g = _guard(audit_log_path=path, audit_secret="s3cret")
        g.check(agent_id="trend_hunter", tool_name="trend_hunter", action="read")
        with open(path, encoding="utf-8") as f:
            entry = json.loads(f.read().strip())
        assert "hmac" in entry
        assert entry["data"]["agent_id"] == "trend_hunter"


def test_call_tool_rejects_unknown_server_and_tool():
    from src import mcp_client

    with pytest.raises(GuardDenied) as e1:
        asyncio.run(mcp_client.call_tool("nope.tool"))
    assert e1.value.gate == "G1"

    with pytest.raises(GuardDenied) as e2:
        asyncio.run(mcp_client.call_tool("secret_delete"))
    assert e2.value.gate == "G1"
