"""质量门 3 条腿测试：确定性阈值 + WARN/HALT 分级。"""

from src.orchestrator.quality_gate import (
    GateResult,
    _analytics_non_empty,
    _script_non_empty,
)


def test_script_gate_halt_empty():
    assert _script_non_empty({"script": {}}) == GateResult.HALT


def test_script_gate_warn_short():
    assert _script_non_empty({"script": {"body": "短"}}) == GateResult.WARN


def test_script_gate_pass_long():
    body = "这是一个足够长的脚本文案" * 5
    assert _script_non_empty({"script": {"body": body}}) == GateResult.PASS


def test_analytics_gate_halt_empty():
    assert _analytics_non_empty({"analytics": {}}) == GateResult.HALT


def test_analytics_gate_warn_report_only():
    assert _analytics_non_empty({"analytics": {"report": "正常"}}) == GateResult.WARN


def test_analytics_gate_pass_full():
    assert (
        _analytics_non_empty({"analytics": {"report": "正常", "metrics": {}, "benchmark": {}}})
        == GateResult.PASS
    )
