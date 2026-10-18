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


# ——— P5-E v1 vs v2 脚本对照 ———


def test_compare_scripts_better_when_changed_and_grounded():
    """v2 脚本变化且落地转录词 → 更好。"""
    v1 = {"body": "为什么美妆看起来简单"}
    v2 = {"body": "秋冬显白口红才是关键"}
    cmp = data_analyst.compare_scripts(v1, v2, {"u": "秋冬显白口红"})
    assert cmp["changed"] is True
    assert cmp["grounded"] is True
    assert cmp["verdict"] == "更好"


def test_compare_scripts_verified_when_same_and_grounded():
    """v2 未变但转录词命中 → 被验证。"""
    body = {"body": "秋冬显白口红"}
    cmp = data_analyst.compare_scripts(body, body, {"u": "秋冬显白口红"})
    assert cmp["changed"] is False
    assert cmp["grounded"] is True
    assert cmp["verdict"] == "被验证"


def test_compare_scripts_unchanged_when_same_and_ungrounded():
    """v2 未变且无转录词 → 未变。"""
    body = {"body": "内容"}
    cmp = data_analyst.compare_scripts(body, body, {"u": "完全无关的转录"})
    assert cmp["verdict"] == "未变"


def test_run_appends_comparison_when_previous_script():
    """previous_script 传入时 report 追加 v1 vs v2 对照段，含 verdict。"""
    out = data_analyst.run(
        previous_script={"body": "旧"},
        script={"body": "秋冬显白口红"},
        transcripts={"u": "秋冬显白口红"},
    )
    assert out["comparison"]["verdict"] == "更好"
    assert "对照" in out["report"]


def test_run_keeps_comparison_verdict_when_llm_rewrites(monkeypatch):
    """full 档 LLM 重写 report 后，v1 vs v2 对照 verdict 仍保留在 report 尾。"""
    monkeypatch.setattr(data_analyst.llm_mode, "get_mode", lambda: "full")
    monkeypatch.setattr("src.llm.has_key", lambda: True)
    monkeypatch.setattr("src.llm.call_llm", lambda *a, **k: "LLM 重写的结论")
    out = data_analyst.run(
        previous_script={"body": "旧"},
        script={"body": "秋冬显白口红"},
        transcripts={"u": "秋冬显白口红"},
    )
    assert out["comparison"]["verdict"] == "更好"
    assert out["report"] == "LLM 重写的结论 v1 vs v2 对照：更好"
