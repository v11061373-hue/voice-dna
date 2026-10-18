"""数据分析 tool — 步骤 6 数据分析（IQR 异常检测 + benchmark）。

数据源缺真实后台，降级演示序列；核心逻辑已落：IQR 1.5 异常检测
+ 互动率 / 分层桶 / 四分位 benchmark（借 mirrormetrics/framepulse 公式）。
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from src import llm_mode

# 报告 4 字段（借 Postiz/BrightBean/ayrshare analytics 数据模型，清单：借概念）。
REPORT_FIELDS: tuple[str, ...] = (
    "report",
    "metrics",
    "benchmark",
    "anomalies",
)


def detect_anomalies(values: list[float]) -> list[dict[str, Any]]:
    """IQR 1.5 箱线异常检测。

    社媒指标重尾分布，z-score 假设正态会误判，先落 IQR（最稳健）。
    ponytail: z-score/MAD 是升级路径，需要时再加（README 方法族）。
    """
    if len(values) < 4:
        return []  # 样本太少，四分位不可靠
    q1 = float(np.percentile(values, 25))
    q3 = float(np.percentile(values, 75))
    iqr = q3 - q1
    if iqr == 0:
        return []  # 全等值，无离群
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    out: list[dict[str, Any]] = []
    for i, v in enumerate(values):
        if v < lo:
            out.append({"index": i, "value": v, "direction": "down"})
        elif v > hi:
            out.append({"index": i, "value": v, "direction": "up"})
    return out


def engagement_rate(likes: float, comments: float, views: float) -> float | None:
    """互动率 = (like+comment)/view*100（借 mirrormetrics 公式）。views=0 返回 None。"""
    if views == 0:
        return None
    return (likes + comments) / views * 100


def view_bucket(views: float) -> str:
    """播放量分层桶（借 mirrormetrics 10M/1M/100K）。"""
    if views >= 10_000_000:
        return "10M+"
    if views >= 1_000_000:
        return "1M-10M"
    if views >= 100_000:
        return "100K-1M"
    return "100K以下"


def quartile(values: list[float], current: float) -> int:
    """当前值在历史分布第几四分位（1 底 4 顶，借 framepulse 四分位）。"""
    q1, q2, q3 = np.percentile(values, [25, 50, 75])
    if current < q1:
        return 1
    if current < q2:
        return 2
    if current < q3:
        return 3
    return 4


# 演示指标序列 — 无真实 MCP 数据源时的降级种子，接 BrightBean/Postiz 时替换。
_DEMO_VIEWS = [1200, 1350, 1180, 1500, 1420, 9800, 1610]
_DEMO_LIKES = [120, 135, 118, 150, 142, 980, 161]
_DEMO_COMMENTS = [30, 33, 28, 40, 35, 210, 38]


def run(**kwargs: Any) -> dict[str, Any]:
    """读入 metrics 序列，端到端出报告：metrics + benchmark + anomalies。

    可选 v2 回流对照（previous_script 传入时）：report 追加 v1 vs v2 段。
    """
    views = [float(v) for v in (kwargs.get("views") or _DEMO_VIEWS)]
    likes = [float(v) for v in (kwargs.get("likes") or _DEMO_LIKES)]
    comments = [float(v) for v in (kwargs.get("comments") or _DEMO_COMMENTS)]

    anomalies = detect_anomalies(views)
    latest = views[-1] if views else 0.0
    metrics = {
        "views": views,
        "total_views": int(sum(views)),
        "avg_views": round(float(np.mean(views)), 1) if views else 0.0,
        "engagement_rate": engagement_rate(sum(likes), sum(comments), sum(views)),
    }
    benchmark = {
        "quartile": quartile(views, latest) if len(views) >= 4 else 0,
        "view_bucket": view_bucket(latest),
        "peer_median": round(float(np.median(views)), 1) if views else 0.0,
    }
    report = (
        f"近 {len(views)} 条内容均播 {metrics['avg_views']}，最新第 "
        f"{benchmark['quartile']} 四分位（{benchmark['view_bucket']}），"
        f"IQR 1.5 检出 {len(anomalies)} 处异常。"
    )
    result: dict[str, Any] = {
        "report": report,
        "metrics": metrics,
        "benchmark": benchmark,
        "anomalies": anomalies,
    }
    previous_script = kwargs.get("previous_script")
    if previous_script is not None:
        result["comparison"] = compare_scripts(
            previous_script,
            kwargs.get("script") or {},
            kwargs.get("transcripts") or {},
        )
    # 三段式第二段：LLM 写结论（全开档；兜底/确定性走统计主路径）。
    out = llm_mode.supplement(
        "data_analyst", has_baseline=True, baseline=result,
        fn=lambda: _llm_conclusion(result),
    )
    # 对照 verdict 挂 report 尾，放在 supplement 之后，full 档 LLM 重写 report 也不丢。
    if "comparison" in out:
        out["report"] = str(out.get("report", "")) + f" v1 vs v2 对照：{out['comparison']['verdict']}"
    return out


# ——— P5-E v1 vs v2 脚本对照 ———

# 转录「内容词」：2-4 字中文连续段 + 3+ 字母英文词。
# ponytail: 无中文分词，最长 4 字截断近似关键词；要更准上 jieba/向量召回。
_CONTENT_WORD_RE = re.compile(r"[一-鿿]{2,4}|[A-Za-z]{3,}")


def _content_words(transcripts: dict[str, str] | None) -> set[str]:
    words: set[str] = set()
    for text in (transcripts or {}).values():
        words.update(m.group(0) for m in _CONTENT_WORD_RE.finditer(str(text)))
    return words


def compare_scripts(
    v1: dict[str, Any], v2: dict[str, Any], transcripts: dict[str, str] | None
) -> dict[str, Any]:
    """v1 vs v2 脚本对照（v2 回流）。四类：更好 / 变化 / 被验证 / 未变。

    - 更好：v2 脚本变化且落地转录内容词。
    - 变化：v2 有变化但未落地转录词。
    - 被验证：未变但转录词命中（v1 脚本被真实口播验证）。
    - 未变：既无变化又无转录词命中。
    """
    b1 = str((v1 or {}).get("body", "")).strip()
    b2 = str((v2 or {}).get("body", "")).strip()
    changed = b1 != b2
    words = _content_words(transcripts)
    grounded = any(w in b2 for w in words)
    if changed and grounded:
        verdict = "更好"
    elif changed:
        verdict = "变化"
    elif grounded:
        verdict = "被验证"
    else:
        verdict = "未变"
    return {"changed": changed, "grounded": grounded, "verdict": verdict}


def _llm_conclusion(analytics: dict[str, Any]) -> dict[str, Any]:
    """LLM 基于指标/基准/异常写一句可执行结论（不编造数字）。"""
    from src import agents, llm

    prompt = (
        "根据以下数据写一句可执行结论（只依据给定数字，不编造）。\n"
        f"指标: {analytics.get('metrics')}\n"
        f"基准: {analytics.get('benchmark')}\n"
        f"异常: {analytics.get('anomalies')}"
    )
    text = llm.call_llm(prompt, system=agents.system_prompt("data_analyst")).strip()
    return {**analytics, "report": text or analytics["report"]}
