"""数据分析 tool 契约测试（占位骨架）。

占位 run() 不接 MCP；本测试锁契约：报告字段，
接 BrightBean/Postiz（步骤 5）时填 metrics/benchmark/anomalies，字段签名不变。
"""

from src.tools import data_analyst


def test_run_returns_report_dict():
    """run() 返回 dict，含 report 非空（质量门腿③依赖）。"""
    out = data_analyst.run()
    assert isinstance(out, dict)
    assert out.get("report")


def test_report_schema_has_four_fields():
    """报告 schema 定 4 字段（借 Postiz/BrightBean analytics 数据模型）。"""
    assert set(data_analyst.REPORT_FIELDS) == {
        "report",
        "metrics",
        "benchmark",
        "anomalies",
    }


def test_detect_anomalies_flat_series_returns_empty():
    """指标序列平稳（无离群）→ 空列表。"""
    vals = [100, 101, 99, 100, 102, 100, 101]
    assert data_analyst.detect_anomalies(vals) == []


def test_detect_anomalies_flags_extreme_high():
    """单点远高上界 → 标记 index + up。"""
    vals = [100, 101, 99, 100, 102, 100, 1000]
    out = data_analyst.detect_anomalies(vals)
    assert len(out) == 1
    assert out[0]["index"] == 6
    assert out[0]["direction"] == "up"


def test_detect_anomalies_flags_extreme_low():
    """单点远低下界 → 标记 index + down。"""
    vals = [100, 101, 99, 100, 102, 100, 1]
    out = data_analyst.detect_anomalies(vals)
    assert len(out) == 1
    assert out[0]["index"] == 6
    assert out[0]["direction"] == "down"


def test_engagement_rate_percent():
    """互动率 = (like+comment)/view*100（mirrormetrics 公式）。"""
    assert data_analyst.engagement_rate(50, 50, 1000) == 10.0


def test_engagement_rate_zero_views():
    """views=0 除零 → None。"""
    assert data_analyst.engagement_rate(0, 0, 0) is None


def test_view_bucket_four_tiers():
    """mirrormetrics 播放量分层桶 10M/1M/100K。"""
    assert data_analyst.view_bucket(12_000_000) == "10M+"
    assert data_analyst.view_bucket(5_000_000) == "1M-10M"
    assert data_analyst.view_bucket(500_000) == "100K-1M"
    assert data_analyst.view_bucket(50_000) == "100K以下"


def test_quartile_ranks_against_distribution():
    """当前值在历史分布第几四分位（1 底 4 顶，framepulse 四分位）。"""
    vals = [10, 20, 30, 40, 50, 60, 70, 80]
    assert data_analyst.quartile(vals, 15) == 1
    assert data_analyst.quartile(vals, 75) == 4


def test_run_computes_anomalies_and_benchmark():
    """run() 接 detect_anomalies + quartile benchmark，端到端真出报告（非占位）。"""
    views = [100, 101, 99, 100, 102, 100, 1000]
    out = data_analyst.run(views=views)
    assert out["anomalies"] == [{"index": 6, "value": 1000.0, "direction": "up"}]
    assert out["benchmark"]["quartile"] == 4
    assert out["benchmark"]["view_bucket"] == "100K以下"
    assert out["metrics"]["total_views"] == 1602
