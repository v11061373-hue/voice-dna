"""数据分析 tool — 步骤 6 数据分析（IQR 异常检测 + benchmark）。

数据源缺真实后台，降级演示序列；核心逻辑已落：IQR 1.5 异常检测
+ 互动率 / 分层桶 / 四分位 benchmark（借 mirrormetrics/framepulse 公式）。
"""

from typing import Any

import numpy as np

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
    """读入 metrics 序列，端到端出报告：metrics + benchmark + anomalies。"""
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
    return {
        "report": report,
        "metrics": metrics,
        "benchmark": benchmark,
        "anomalies": anomalies,
    }
