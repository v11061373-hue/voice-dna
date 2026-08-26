"""选题策划 tool — 步骤 4：热点列表 → 选题 + 评分 + 理由。

搬运来源（file:line）：
- 打分 rubric：marketingskills `skills/content-strategy/SKILL.md:306-340`
  （Prioritizing Content Ideas）4 因子加权 40/30/20/10，每因子 1-10 分 × 权重
  求和，按总分降序取 top（SKILL.md:340「Score 1-10 per factor, multiply by
  the weight, sum for the total. Rank the list」）。
- 分工 + prompt 结构（借概念，当前用确定性规则替代 LLM）：AIWriteX
  （iniwap/AIWriteX，CrewAI 研究员→作家→审核员→设计师）
  - `src/ai_write_x/tools/hotnews.py:168-200` select_platform_topic：
    按排名加权选热点（weights = 1/(rank+1)^2，排名越前权重越高）。
  - `src/ai_write_x/core/unified_workflow.py:88-102`：选题分析→写作分工
    （role/goal/backstory + context=["analyze_topic"]），选题产物带评分+理由。
- content-ideation-engine：全网搜索无结果，未搬运（不编造来源）。

改了什么（适配点）：
- 无 LLM 管线：选题 prompt 不落死串（防死代码），接 LLM 时只换 `_score`
  的实现、签名不变。
- 4 因子映射到趋势 dict 可确定取值的字段（无 account_profile/搜索量输入，
  非热度因子退化为元数据有无的启发式，ponytail: 有真实数据源时替换）：
  热度(40%) ← heat 批内 min-max 归一化 0-10；
  相关度(30%) ← category 有无（已分类更贴近赛道）；
  差异化(20%) ← url 有无（带来源 = 可验证的独特角度）；
  可执行性(10%) ← platform 有无（已知平台 = 发布形态可执行）。
- 输出 {title, score, reason}，score 按总分降序。
"""

from __future__ import annotations

from typing import Any

# 搬自 marketingskills content-strategy/SKILL.md:310-328：因子 → 权重。
_WEIGHTS: list[tuple[str, float]] = [
    ("热度", 0.4),
    ("相关度", 0.3),
    ("差异化", 0.2),
    ("可执行性", 0.1),
]


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _score(trend: dict[str, Any], max_heat: float) -> tuple[float, str]:
    """确定性 4 因子加权打分，返回 (总分 0-10, 理由)。"""
    heat = _to_float(trend.get("heat"))
    factors: dict[str, float] = {
        "热度": 10 * heat / max_heat if max_heat > 0 else 0.0,
        "相关度": 10.0 if str(trend.get("category") or "").strip() else 5.0,
        "差异化": 10.0 if str(trend.get("url") or "").strip() else 5.0,
        "可执行性": 10.0 if str(trend.get("platform") or "").strip() else 5.0,
    }
    total = sum(weight * factors[name] for name, weight in _WEIGHTS)
    top = max(factors, key=factors.__getitem__)
    reason = f"{top}突出({factors[top]:.1f}/10)；热度 {heat:.0f}"
    return round(total, 1), reason


def run(**kwargs: Any) -> list[dict[str, Any]]:
    """读入 trends 热点列表，确定性加权打分排序，返回选题 list。

    每项 {title, score, reason}。空输入 / 异常返回 []（非 dict）。
    """
    trends = kwargs.get("trends") or []
    if not isinstance(trends, list):
        return []
    trends = [t for t in trends if isinstance(t, dict)]
    if not trends:
        return []

    max_heat = max(_to_float(t.get("heat")) for t in trends)
    out: list[dict[str, Any]] = []
    for t in trends:
        title = str(t.get("title") or "").strip()
        if not title:
            continue
        score, reason = _score(t, max_heat)
        out.append({"title": title, "score": score, "reason": reason})
    out.sort(key=lambda item: item["score"], reverse=True)
    return out
