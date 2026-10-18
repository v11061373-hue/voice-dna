"""选题策划 tool 契约测试。"""

from src.tools import topic_planner


def test_run_returns_list():
    """run() 返回 list，不是 dict。"""
    assert isinstance(topic_planner.run(), list)


def test_empty_trends_returns_empty_list():
    """空 / None / 非 list 输入均确定性返回 []。"""
    assert topic_planner.run() == []
    assert topic_planner.run(trends=[]) == []
    assert topic_planner.run(trends=None) == []
    assert topic_planner.run(trends="not-a-list") == []


def test_items_have_contract_keys():
    """每项含 {title, score, reason} 三键。"""
    trends = [
        {"title": "热点A", "platform": "weibo", "heat": 100, "url": "https://a", "category": "科技"},
        {"title": "热点B", "platform": "douyin", "heat": 50, "url": "", "category": ""},
    ]
    out = topic_planner.run(trends=trends)
    assert len(out) == 2
    for item in out:
        assert set(item) == {"title", "score", "reason"}


def test_score_is_numeric():
    """score 是 int/float 数值。"""
    out = topic_planner.run(trends=[{"title": "X", "heat": 10}])
    assert isinstance(out[0]["score"], (int, float))


def test_scores_have_discrimination_and_are_sorted():
    """不同热度 → 不同分数，且按分数降序。"""
    trends = [
        {"title": "高热", "heat": 1000, "category": "科技", "url": "https://x", "platform": "weibo"},
        {"title": "低热", "heat": 10},
    ]
    out = topic_planner.run(trends=trends)
    scores = [item["score"] for item in out]
    assert scores[0] != scores[1]
    assert scores == sorted(scores, reverse=True)
    assert out[0]["title"] == "高热"


def test_run_analytics_shifts_ranking_to_explore():
    """回流（低四分位）：抬差异化权重，独特选题压过热门选题。"""
    trends = [
        {"title": "热门A", "heat": 100, "category": "", "url": "", "platform": "douyin"},
        {"title": "独特B", "heat": 70, "category": "", "url": "https://x", "platform": "douyin"},
    ]
    base = topic_planner.run(trends=trends)
    assert base[0]["title"] == "热门A"  # 无回流：热度优先
    looped = topic_planner.run(trends=trends, analytics={"benchmark": {"quartile": 1}})
    assert looped[0]["title"] == "独特B"  # 低四分位：差异化优先
