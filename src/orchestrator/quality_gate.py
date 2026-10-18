"""质量门 — 5 门（3 确定性 + 2 LLM-judge）。

① schema 硬门（确定性）：字段必填 + 类型，最强第一道。
② 非空+长度门（确定性）：文本非空 + 长度阈值。
③ 溯源门（LLM-judge）：产出热点/数据必须能溯源到输入，编造 HALT。
④ 赛道相关门（LLM-judge）：产出语义命中 profile，跑题 HALT。
⑤ 合规门（确定性词表）：广告法违禁词 / 虚假宣传词。

每 agent 必填字段 schema 存 src/schemas.py，schema 硬门读它。
LLM-judge 走 src/orchestrator/judge.py（独立 provider，config.judge_settings()）。
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, cast

from src.orchestrator import judge
from src.schemas import (
    ITEM_KEYS,
    OUTPUT_FIELD,
    OUTPUT_TYPE,
    REQUIRED_KEYS,
    SocialMediaState,
)


class GateResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    HALT = "HALT"


CheckFn = Callable[[str, SocialMediaState], GateResult]

_MIN_SCRIPT_LEN = 30

# 合规门词表（广告法违禁词 / 虚假宣传词，确定性子串扫描）。
FORBIDDEN_WORDS: tuple[str, ...] = (
    "全网最低", "全网首发", "国家级", "世界级", "最高级",
    "顶级", "最佳", "首选", "唯一", "独家", "纯天然",
    "药到病除", "包治", "根治", "神效", "绝对安全",
)


# ——— ① schema 硬门 ———


def _schema_gate(stage: str, state: SocialMediaState) -> GateResult:
    """字段必填 + 类型；dict 产物查必填子键，list 产物查每项必填键。"""
    field = OUTPUT_FIELD[stage]
    out = state.get(field)
    typ = OUTPUT_TYPE[field]
    if out is None or not isinstance(out, typ):
        return GateResult.HALT
    if typ is dict:
        data = cast(dict[str, Any], out)
        for key in REQUIRED_KEYS.get(field, ()):
            if key not in data:
                return GateResult.HALT
    else:  # list
        items = cast(list[Any], out)
        for item in items:
            if not isinstance(item, dict):
                return GateResult.HALT
            for key in ITEM_KEYS.get(field, ()):
                if key not in item:
                    return GateResult.HALT
    return GateResult.PASS


# ——— ② 非空+长度门 ———


def _non_empty_gate(stage: str, state: SocialMediaState) -> GateResult:
    """文本产物非空 HALT；脚本过短 WARN，达标 PASS。"""
    field = OUTPUT_FIELD[stage]
    out: Any = state.get(field) or {}
    if field == "script":
        body = (out.get("body") or "").strip()
        if not body:
            return GateResult.HALT
        return GateResult.PASS if len(body) >= _MIN_SCRIPT_LEN else GateResult.WARN
    if field == "analytics":
        return GateResult.HALT if not (out.get("report") or "").strip() else GateResult.PASS
    return GateResult.PASS


# ——— ⑤ 合规门 ———


def _compliance_gate(stage: str, state: SocialMediaState) -> GateResult:
    """违禁词子串扫描（script body / publish_plan 描述+标签）。"""
    field = OUTPUT_FIELD[stage]
    out: Any = state.get(field) or {}
    if field == "script":
        text = str(out.get("body") or "")
    elif field == "publish_plan":
        text = " ".join(
            [str(out.get("description") or "")]
            + [str(t) for t in (out.get("tags") or [])]
            + [str(h) for h in (out.get("hashtags") or [])]
        )
    else:
        return GateResult.PASS
    for word in FORBIDDEN_WORDS:
        if word in text:
            return GateResult.HALT
    return GateResult.PASS


# ——— LLM-judge 门 ———


def _judge_gate(prompt: str) -> GateResult:
    verdict = judge.judge(prompt)
    return GateResult.HALT if not verdict["pass"] else GateResult.PASS


def _trace_prompt(stage: str, state: SocialMediaState) -> str:
    """溯源门：产出里的热点/数据必须能溯源到输入（热点/样本/画像；analytics 溯源到 metrics）。"""
    field = OUTPUT_FIELD[stage]
    out: Any = state.get(field) or {}
    content = out.get("body") if field == "script" else out.get("report") if field == "analytics" else out
    if field == "analytics":
        source = (
            "输入（可溯源数据）:\n"
            f"- 指标: {out.get('metrics')}\n"
            f"- 基准: {out.get('benchmark')}\n"
            f"- 异常: {out.get('anomalies')}"
        )
    else:
        trends = [str(t.get("title", "")) for t in (state.get("trends") or [])]
        transcripts = [str(t) for t in (state.get("transcripts") or {}).values()]
        source = (
            "输入（可溯源素材）:\n"
            f"- 热点: {trends}\n"
            f"- 样本: {state.get('samples', '')}\n"
            f"- 转录逐字稿: {transcripts}\n"
            f"- 画像: {state.get('account_profile', '')}"
        )
    return (
        "判断产出中的具体事实（具体数字/品牌/型号/人名/价格/事件）是否都能溯源到输入。\n"
        "只有无法溯源的「具体事实」才算编造（pass=false）；修辞润色、文学化表达、拟人化、\n"
        "比喻、过渡语不算编造。\n"
        f"{source}\n\n产出（待溯源）:\n{content}"
    )


def _relevance_prompt(stage: str, state: SocialMediaState) -> str:
    """赛道相关门：产出语义命中画像赛道，跑题返回 pass=false。"""
    field = OUTPUT_FIELD[stage]
    out: Any = state.get(field) or []
    if isinstance(out, list):
        content = [str(t.get("title", "")) for t in out]
    else:
        content = out
    return (
        "判断产出是否命中账号画像的赛道，跑题返回 pass=false。\n"
        f"画像: {state.get('account_profile', '')}\n\n产出: {content}"
    )


def _content_empty(stage: str, state: SocialMediaState) -> bool:
    """产出内容是否为空。空 = 无可溯源/无跑题，judge 跳过（空由非空门/下游兜）。"""
    field = OUTPUT_FIELD[stage]
    out: Any = state.get(field)
    if isinstance(out, list):
        return not out
    if isinstance(out, dict):
        if field == "script":
            return not (out.get("body") or "").strip()
        if field == "analytics":
            return not (out.get("report") or "").strip()
        return not out
    return not str(out or "").strip()


def _trace_judge_gate(stage: str, state: SocialMediaState) -> GateResult:
    if _content_empty(stage, state):
        return GateResult.PASS
    return _judge_gate(_trace_prompt(stage, state))


def _relevance_judge_gate(stage: str, state: SocialMediaState) -> GateResult:
    if _content_empty(stage, state):
        return GateResult.PASS
    return _judge_gate(_relevance_prompt(stage, state))


# 每 stage 跑的门（顺序 = 强度：schema 最强第一道）。5 门全挂。
QUALITY_GATES: dict[str, list[CheckFn]] = {
    "trend_hunter": [_schema_gate, _relevance_judge_gate],
    "topic_planner": [_schema_gate, _relevance_judge_gate],
    "style_mimic": [_schema_gate],
    "script_writer": [_schema_gate, _non_empty_gate, _trace_judge_gate, _compliance_gate],
    "publish_optimizer": [_schema_gate, _compliance_gate],
    "data_analyst": [_schema_gate, _non_empty_gate, _trace_judge_gate],
}


def run_quality_gates(stage: str, state: SocialMediaState) -> GateResult:
    """跑 stage 全部门，取最坏结果 HALT > WARN > PASS。"""
    results = [fn(stage, state) for fn in QUALITY_GATES.get(stage, [])]
    for worst in (GateResult.HALT, GateResult.WARN):
        if worst in results:
            return worst
    return GateResult.PASS
