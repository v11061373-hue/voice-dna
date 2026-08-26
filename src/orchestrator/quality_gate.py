"""质量门 — 评测规则三条腿骨架。

腿① 确定性规则评测（script_quality 词表+纯函数）
腿② LLM-as-judge（ShortGPT 借概念，阈值+重试循环自己写）
腿③ 统计异常检测（IQR 在 data_analyst，此门只查非空）

MVP 只挂「非空」占位 check_fn，步骤5 填阈值+重试。
参照 BidForge src/orchestrator/quality_gate.py。
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from src.schemas import SocialMediaState


class GateResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    HALT = "HALT"


class GateAction(StrEnum):
    WARN = "WARN"
    HALT = "HALT"


@dataclass
class QualityGate:
    name: str
    description: str
    check_fn: Callable[[SocialMediaState], GateResult]
    on_failure: GateAction


_MIN_SCRIPT_LEN = 30


def _script_non_empty(state: SocialMediaState) -> GateResult:
    """腿①确定性：脚本 body 非空 HALT，过短 WARN，达标 PASS。"""
    body = ((state.get("script") or {}).get("body") or "").strip()
    if not body:
        return GateResult.HALT
    return GateResult.PASS if len(body) >= _MIN_SCRIPT_LEN else GateResult.WARN


def _analytics_non_empty(state: SocialMediaState) -> GateResult:
    """腿③统计异常：报告非空 HALT，仅报告缺指标 WARN，全字段 PASS。"""
    analytics = state.get("analytics") or {}
    if not analytics.get("report"):
        return GateResult.HALT
    if "metrics" not in analytics or "benchmark" not in analytics:
        return GateResult.WARN
    return GateResult.PASS


QUALITY_GATES: dict[str, list[QualityGate]] = {
    "script_writer": [
        QualityGate("脚本文案非空", "脚本 body 非空", _script_non_empty, GateAction.HALT),
    ],
    "data_analyst": [
        QualityGate("分析报告非空", "analytics.report 非空", _analytics_non_empty, GateAction.HALT),
    ],
}


def run_quality_gates(stage: str, state: SocialMediaState) -> GateResult:
    """跑 stage 全部门，取最坏结果 HALT > WARN > PASS。"""
    results = [g.check_fn(state) for g in QUALITY_GATES.get(stage, [])]
    for worst in (GateResult.HALT, GateResult.WARN):
        if worst in results:
            return worst
    return GateResult.PASS
