"""五门安全网关 — agent 工具调用访问控制（自 bidforge-v4/src/mcp_guard/gateway.py 复制适配）。

门按序执行：
  G1 工具门 — 白名单（硬拒）
  G2 动作门 — read / draft / external_write 分类
  G3 风险门 — external_write 需人工批准（硬拒，read/draft 放行）
  G4 预算门 — 限流（滑动窗口）+ 成本 / 时间 / 重试
  G5 审计门 — JSONL + HMAC 留痕

差异（vs BidForge）：
  · BidForge 的 G4 只做限流；本次把成本/时间/重试并入 G4。
  · 单用户无鉴权，去掉 agent_tokens 预共享令牌。
  · tool 名允许 `server.tool` 外部命名（含 `.` / `-`）。
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# ── 9 本地 tool 名 + 动作分类（与 src/mcp_server.py 注册的 9 tool 一致）──
VOICE_DNA_TOOLS = frozenset(
    {
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
)

TOOL_ACTIONS = {
    "trend_hunter": "read",
    "topic_planner": "read",
    "style_mimic": "draft",
    "script_writer": "draft",
    "publish_optimizer": "draft",
    "data_analyst": "draft",
    "transcribe": "read",
    "video_download": "read",
    "video_vision": "read",
}

# ── 外部 tool 名关键字分类（本地 8 tool 已显式映射，这里兜底外部 server.tool）──
_WRITE_KWS = ("write", "delete", "update", "send", "export", "modify", "remove", "insert", "post")
_DRAFT_KWS = ("generate", "create", "build", "make", "produce", "fill", "optimize")
_CRITICAL_KWS = ("delete", "overwrite", "drop", "truncate")

# ── M2 输入校验常量 ──
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_AGENT_ID_LEN = 64
_MAX_TOOL_NAME_LEN = 128
_MAX_ACTION_LEN = 32

# ── 审计常量 ──
_MAX_AUDIT_SIZE = 10 * 1024 * 1024  # 10 MB


def default_whitelist() -> dict[str, set[str]]:
    """默认白名单：每个 agent 只准调自己的 tool；外部 `server.tool` 用 register() 追加。"""
    return {t: {t} for t in VOICE_DNA_TOOLS}


@dataclass
class GuardDecision:
    allowed: bool = True
    reason: str = ""
    gate: str = ""
    risk_level: str = "low"


class GuardDenied(Exception):
    """工具调用被网关拒绝（call_tool / web_server 用它返回结构化拒绝而非崩）。"""

    def __init__(self, gate: str, reason: str) -> None:
        self.gate = gate
        self.reason = reason
        super().__init__(f"[{gate}] {reason}")


@dataclass
class _Window:
    """滑动窗口，限流单 key 状态。"""

    timestamps: list[float] = field(default_factory=list)

    def allow(self, max_requests: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        if len(self.timestamps) >= max_requests:
            return False
        self.timestamps.append(now)
        return True


class MCPGuard:
    """五门管道，治理每次 agent 工具调用。"""

    def __init__(
        self,
        whitelist: dict[str, set[str]] | None = None,
        *,
        max_requests_per_window: int = 100,
        window_seconds: float = 60.0,
        cost_budget: float | None = None,
        time_budget: float | None = None,
        max_retries: int | None = None,
        audit_log_path: Path | None = None,
        audit_secret: str | None = None,
    ) -> None:
        self._whitelist: dict[str, set[str]] = whitelist or {}
        self._max_requests = max_requests_per_window
        self._window_seconds = window_seconds
        self._cost_budget = cost_budget
        self._time_budget = time_budget
        self._max_retries = max_retries
        self._audit_log_path = Path(audit_log_path) if audit_log_path is not None else None
        self._audit_secret = audit_secret
        self._windows: dict[str, _Window] = {}
        self._cost_spent: dict[str, float] = {}
        self._session_start: dict[str, float] = {}
        self._last_access: dict[str, float] = {}
        self._lock = Lock()

    # ── 对外 API ──

    def register(self, agent_id: str, tool_name: str) -> None:
        """把外部 `server.tool` 追加进某 agent 的白名单。"""
        self._whitelist.setdefault(agent_id, set()).add(tool_name)

    def charge(self, agent_id: str, cost: float) -> None:
        """后付费累加成本（token 数），不拒绝；下一次 check 的 cost 预算据此拒绝。"""
        with self._lock:
            self._cost_spent[agent_id] = self._cost_spent.get(agent_id, 0.0) + cost

    def check(
        self,
        *,
        agent_id: str,
        tool_name: str,
        action: str,
        cost: float = 0.0,
        retry: int = 0,
    ) -> GuardDecision:
        """跑满五门，返回决策。cost/retry 喂 G4 预算门。"""
        val_err = self._validate_input(agent_id, tool_name, action)
        if val_err is not None:
            decision = GuardDecision(allowed=False, reason=val_err, gate="G1", risk_level="low")
            self._audit(agent_id, tool_name, action, decision)
            return decision

        g1 = self._check_whitelist(agent_id, tool_name)
        if not g1.allowed:
            self._audit(agent_id, tool_name, action, g1)
            return g1

        g2 = self._classify_action(agent_id, tool_name, action)
        decisions = [g1, g2]
        decisions.append(self._assess_risk(agent_id, tool_name, g2.reason))
        decisions.append(self._check_rate_limit(agent_id, tool_name, action))
        decisions.append(self._check_budget(agent_id, tool_name, cost, retry))

        final = GuardDecision(allowed=True, risk_level="low", gate="G5")
        for d in decisions:
            if not d.allowed:
                final.allowed = False
                final.gate = d.gate
                final.reason = d.reason
            if _risk_order(d.risk_level) > _risk_order(final.risk_level):
                final.risk_level = d.risk_level

        self._audit(agent_id, tool_name, action, final)
        return final

    # ── G1 白名单 ──

    def _check_whitelist(self, agent_id: str, tool_name: str) -> GuardDecision:
        allowed_tools = self._whitelist.get(agent_id)
        if allowed_tools is None or tool_name not in allowed_tools:
            return GuardDecision(allowed=False, reason="access denied", gate="G1", risk_level="low")
        return GuardDecision(allowed=True, reason="", gate="G1", risk_level="low")

    # ── G2 动作分类 ──

    def _classify_action(self, agent_id: str, tool_name: str, action: str) -> GuardDecision:
        """本地 8 tool 走显式映射；外部 tool 按名关键字分类（默认 read）。"""
        if tool_name in TOOL_ACTIONS:
            classification = TOOL_ACTIONS[tool_name]
        elif any(kw in tool_name.lower() for kw in _WRITE_KWS):
            classification = "external_write"
        elif any(kw in tool_name.lower() for kw in _DRAFT_KWS):
            classification = "draft"
        else:
            classification = "read"
        return GuardDecision(allowed=True, reason=classification, gate="G2", risk_level="low")

    # ── G3 风险门 ──

    def _assess_risk(self, agent_id: str, tool_name: str, action: str) -> GuardDecision:
        risk = "low"
        if any(kw in tool_name.lower() for kw in _CRITICAL_KWS):
            risk = "critical"
        elif action == "external_write":
            risk = "high"
        if action == "external_write":
            return GuardDecision(
                allowed=False, reason="requires human approval", gate="G3", risk_level=risk
            )
        return GuardDecision(allowed=True, reason=f"risk={risk}", gate="G3", risk_level=risk)

    # ── G4 预算门 ──

    def _check_rate_limit(self, agent_id: str, tool_name: str, action: str) -> GuardDecision:
        key = f"{agent_id}:{tool_name}"
        with self._lock:
            if key not in self._windows:
                self._windows[key] = _Window()
            window = self._windows[key]
            allowed = window.allow(self._max_requests, self._window_seconds)
            self._last_access[key] = time.monotonic()
        if not allowed:
            return GuardDecision(
                allowed=False,
                reason=f"Rate limit exceeded for '{key}' ({self._max_requests} req / {self._window_seconds}s)",
                gate="G4",
                risk_level="low",
            )
        return GuardDecision(allowed=True, reason="", gate="G4", risk_level="low")

    def _check_budget(self, agent_id: str, tool_name: str, cost: float, retry: int) -> GuardDecision:
        now = time.monotonic()
        with self._lock:
            if self._cost_budget is not None:
                spent = self._cost_spent.get(agent_id, 0.0) + cost
                if spent > self._cost_budget:
                    return GuardDecision(
                        allowed=False,
                        reason=f"cost budget exceeded ({spent:.1f} > {self._cost_budget:.1f})",
                        gate="G4",
                        risk_level="low",
                    )
                self._cost_spent[agent_id] = spent
            if self._time_budget is not None:
                start = self._session_start.setdefault(agent_id, now)
                if now - start > self._time_budget:
                    return GuardDecision(
                        allowed=False, reason="time budget exceeded", gate="G4", risk_level="low"
                    )
            if self._max_retries is not None and retry > self._max_retries:
                return GuardDecision(
                    allowed=False,
                    reason=f"retry budget exceeded ({retry} > {self._max_retries})",
                    gate="G4",
                    risk_level="low",
                )
        return GuardDecision(allowed=True, reason="", gate="G4", risk_level="low")

    # ── G5 审计 ──

    def _audit(self, agent_id: str, tool_name: str, action: str, decision: GuardDecision) -> None:
        if self._audit_log_path is None:
            return
        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "tool_name": tool_name,
            "action": action,
            "decision": {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "gate": decision.gate,
                "risk_level": decision.risk_level,
            },
        }
        try:
            payload = json.dumps(entry, ensure_ascii=False)
            if self._audit_secret:
                sig = hmac.new(self._audit_secret.encode(), payload.encode(), sha256).hexdigest()
                payload = json.dumps({"data": entry, "hmac": sig}, ensure_ascii=False)
            self._write_audit_line(payload)
        except Exception:  # noqa: BLE001 — 审计失败不得阻断主流程
            logger.warning("audit_write_failed: agent_id=%s tool_name=%s", agent_id, tool_name)

    def _write_audit_line(self, line: str) -> None:
        assert self._audit_log_path is not None
        with suppress(Exception):
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            if self._audit_log_path.exists() and self._audit_log_path.stat().st_size >= _MAX_AUDIT_SIZE:
                self._rotate_audit_log()
        # ponytail: 无文件锁；单进程追加，多进程并发写审计时再上 fcntl/msvcrt。
        try:
            with open(self._audit_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            logger.warning("audit_write_failed: path=%s", self._audit_log_path)

    def _rotate_audit_log(self) -> None:
        assert self._audit_log_path is not None
        stamp = time.strftime("%Y-%m-%d")
        rotated = self._audit_log_path.with_name(f"audit-{stamp}.jsonl")
        with suppress(OSError):
            self._audit_log_path.rename(rotated)

    # ── M2 输入校验 ──

    @staticmethod
    def _validate_input(agent_id: str, tool_name: str, action: str) -> str | None:
        if not agent_id or len(agent_id) > _MAX_AGENT_ID_LEN or not _AGENT_ID_RE.match(agent_id):
            return f"invalid agent_id (max {_MAX_AGENT_ID_LEN} chars, must match [a-z][a-z0-9_-]*)"
        if not tool_name or len(tool_name) > _MAX_TOOL_NAME_LEN or not _TOOL_NAME_RE.match(tool_name):
            return f"invalid tool_name (max {_MAX_TOOL_NAME_LEN} chars, must match [a-z][a-z0-9_.-]*)"
        if not action or len(action) > _MAX_ACTION_LEN or not _ACTION_RE.match(action):
            return f"invalid action (max {_MAX_ACTION_LEN} chars, must match [a-z][a-z0-9_]*)"
        return None


def _risk_order(level: str) -> int:
    """风险序数值：low=0, high=1, critical=2。"""
    return {"low": 0, "high": 1, "critical": 2}.get(level, 0)
