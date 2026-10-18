"""质量门 5 门测试（C3）：schema / 非空+长度 / 溯源(judge) / 赛道相关(judge) / 合规。"""

from src.orchestrator.quality_gate import (
    FORBIDDEN_WORDS,
    QUALITY_GATES,
    GateResult,
    run_quality_gates,
)


def _valid_state() -> dict:
    """每步产物 schema 全合法（正常产出 PASS 用）。"""
    return {
        "account_profile": "美妆博主",
        "trends": [{"title": "秋冬口红推荐", "platform": "bilibili", "heat": 100.0, "url": "https://x"}],
        "topics": [{"title": "秋冬口红推荐", "score": 8.0, "reason": "热度突出"}],
        "style_card": {
            "persona": "美妆博主",
            "voice": "口语",
            "catchphrases": [],
            "sentence_patterns": ["短句"],
            "pacing": "快",
            "narrative_structure": "问题-分析-结论",
            "visual_style": "简洁",
        },
        "script": {
            "body": "这是一个足够长的脚本文案，讲秋冬口红怎么选。" * 3,
            "scenes": [{"visual": "v", "narration": "n", "duration": 3}],
            "duration": 3,
        },
        "publish_plan": {
            "platform": "threads",
            "best_time": "09:00",
            "tags": ["美妆"],
            "hashtags": ["秋冬口红"],
            "description": "秋冬口红推荐",
        },
        "analytics": {
            "report": "近 7 条内容均播稳定。",
            "metrics": {"total_views": 100},
            "benchmark": {"quartile": 2},
            "anomalies": [],
        },
    }


# ——— ① schema 硬门（确定性）———


def test_schema_missing_style_card_field_halts():
    """style_card 缺 6 字段 → schema 门 HALT。"""
    assert run_quality_gates("style_mimic", {"style_card": {"persona": "p"}}) == GateResult.HALT


def test_schema_missing_script_body_halts():
    """script 缺 body → schema 门 HALT。"""
    assert run_quality_gates("script_writer", {"script": {"scenes": []}}) == GateResult.HALT


def test_schema_wrong_type_halts():
    """产物字段类型错（trends 非 list）→ schema 门 HALT。"""
    assert run_quality_gates("trend_hunter", {"trends": "not-a-list"}) == GateResult.HALT


def test_schema_trend_item_missing_key_halts():
    """trends 项缺 heat → schema 门 HALT。"""
    state = {"trends": [{"title": "x", "platform": "bilibili"}]}
    assert run_quality_gates("trend_hunter", state) == GateResult.HALT


def test_schema_empty_list_passes():
    """空列表是合法产物（离线降级），schema 门 PASS（非 HALT）。"""
    assert run_quality_gates("trend_hunter", {"trends": []}) == GateResult.PASS


# ——— ② 非空+长度门（确定性）———


def test_non_empty_script_body_empty_halts():
    """脚本 body 空 → 非空门 HALT。"""
    state = {"script": {"body": "", "scenes": [], "duration": 0}}
    assert run_quality_gates("script_writer", state) == GateResult.HALT


# ——— ③ 溯源门（LLM-judge）———


def test_trace_judge_halts_on_fabrication(monkeypatch):
    """judge 判「编造」→ 溯源门 HALT。"""
    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 1.0, "pass": False, "reason": "编造热点"},
    )
    assert run_quality_gates("script_writer", _valid_state()) == GateResult.HALT


def test_trace_judge_passes_on_clean(monkeypatch):
    """judge 判「可溯源」→ 溯源门 PASS。"""
    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 9.0, "pass": True, "reason": "可溯源"},
    )
    assert run_quality_gates("script_writer", _valid_state()) == GateResult.PASS


def test_trace_judge_skips_empty_script(monkeypatch):
    """空脚本 body 无编造可言 → 溯源门跳过 judge 直接 PASS（空由非空门拦）。"""
    from src.orchestrator.quality_gate import _trace_judge_gate

    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 0.0, "pass": False, "reason": "空产出无法溯源"},
    )
    assert _trace_judge_gate("script_writer", {"script": {"body": ""}}) == GateResult.PASS


# ——— ④ 赛道相关门（LLM-judge）———


def test_trace_prompt_limits_to_hard_fabrication():
    """溯源门只拦无法溯源的「具体事实」，不拦修辞/拟人化（软演绎不 HALT）。"""
    from src.orchestrator.quality_gate import _trace_prompt

    state = {
        "account_profile": "数码测评",
        "trends": [{"title": "近万部库存被淘汰"}],
        "samples": "",
        "transcripts": {},
        "script": {"body": "近万部库存，一夜之间变成仓库角落的灰。", "scenes": [], "duration": 1},
    }
    prompt = _trace_prompt("script_writer", state)
    assert "具体事实" in prompt
    assert "拟人化" in prompt
    assert "不算编造" in prompt


def test_relevance_judge_halts_on_offtopic(monkeypatch):
    """judge 判「跑题」→ 赛道相关门 HALT。"""
    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 2.0, "pass": False, "reason": "跑题"},
    )
    assert run_quality_gates("trend_hunter", _valid_state()) == GateResult.HALT


def test_trace_prompt_analytics_includes_metrics():
    """analytics 溯源门溯源源是 metrics（非 trends/samples）：report 数字在 metrics 里。"""
    from src.orchestrator.quality_gate import _trace_prompt

    state = {
        "analytics": {
            "report": "第6条（9800 views）显著高于中位数1420。",
            "metrics": {"total_views": 11160},
            "benchmark": {"peer_median": 1420.0},
            "anomalies": [{"value": 9800.0}],
        },
        "trends": [],
        "samples": "",
        "account_profile": "美妆博主",
    }
    prompt = _trace_prompt("data_analyst", state)
    assert "11160" in prompt  # metrics 数字进溯源源
    assert "1420.0" in prompt
    assert "9800.0" in prompt


def test_relevance_judge_skips_empty_trends(monkeypatch):
    """空 trends 无「跑题」可言 → 赛道相关门跳过 judge 直接 PASS（离线降级不拦死）。"""
    monkeypatch.setattr(
        "src.orchestrator.quality_gate.judge.judge",
        lambda prompt: {"score": 0.0, "pass": False, "reason": "空产出无法判断"},
    )
    assert run_quality_gates("trend_hunter", {"trends": []}) == GateResult.PASS


# ——— ⑤ 合规门（确定性词表）———


def test_compliance_forbidden_word_halts():
    """脚本 body 含违禁词 → 合规门 HALT。"""
    state = _valid_state()
    state["script"]["body"] = "全网最低价，买到就是赚到。" * 5
    assert run_quality_gates("script_writer", state) == GateResult.HALT


def test_forbidden_words_nonempty():
    assert FORBIDDEN_WORDS


# ——— 正常产出 PASS ———


def test_valid_state_passes_all_stages():
    """正常产出（无 key，judge 跳过）5 门全过 → PASS。"""
    for stage in QUALITY_GATES:
        assert run_quality_gates(stage, _valid_state()) == GateResult.PASS, stage


def test_all_five_gates_mounted():
    """5 门全挂：每个 stage 至少挂 schema 门，且 judge 门已挂（全挂 = 池完整）。"""
    # 5 类门函数全部被 QUALITY_GATES 引用
    mounted = {fn.__name__ for fns in QUALITY_GATES.values() for fn in fns}
    assert "_schema_gate" in mounted
    assert "_non_empty_gate" in mounted
    assert "_trace_judge_gate" in mounted
    assert "_relevance_judge_gate" in mounted
    assert "_compliance_gate" in mounted
