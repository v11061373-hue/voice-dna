"""热点猎人 tool 契约测试。"""

import asyncio
import time

import httpx

from src.tools import trend_hunter


def test_item_has_contract_keys():
    item = trend_hunter.TrendItem(title="热点", platform="douyin", heat=1_000_000, url="https://x", category="美妆")
    d = item.to_dict()
    assert set(d) == {"title", "platform", "heat", "url", "category", "time"}
    assert d["heat"] == 1_000_000


# ——— YouTube ———


def _vr(video_id: str, title: str, view: str) -> dict:
    return {
        "videoRenderer": {
            "videoId": video_id,
            "title": {"runs": [{"text": title}]},
            "viewCountText": {"simpleText": view},
        }
    }


def _fake_yt_data() -> dict:
    # 递归查找 videoRenderer，任意嵌套深度均可命中。
    return {"any": {"nested": [_vr("vid1", "标题A", "1,234 views"), _vr("vid2", "标题B", "567 views")]}}


def test_youtube_parses_trending_items():
    items = trend_hunter._parse_yt_trending(_fake_yt_data())
    assert len(items) == 2
    assert items[0].platform == "youtube"
    assert items[0].title == "标题A"
    assert items[0].heat == 1234.0
    assert items[0].url.endswith("vid1")
    assert items[0].category == ""


def test_youtube_network_error_degrades(monkeypatch):
    def boom():
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(trend_hunter, "_fetch_trending", boom)
    assert trend_hunter.run(platform="youtube") == []


# ——— A3 关键词召回 / 排序 / 去重 ———


def test_extract_keywords_known_track():
    """词表版关键词抽取：赛道命中返回词表，未知/空返回空（不过滤）。"""
    assert "美妆" in trend_hunter.extract_keywords("美妆博主")
    assert trend_hunter.extract_keywords("") == []
    assert trend_hunter.extract_keywords("随机陌生赛道") == []


def test_filter_by_keywords():
    items = [
        {"title": "秋冬口红推荐", "category": "美妆"},
        {"title": "显卡跑分", "category": "数码"},
    ]
    out = trend_hunter._filter_by_keywords(items, ["美妆", "口红", "彩妆"])
    assert [i["title"] for i in out] == ["秋冬口红推荐"]


def test_filter_by_keywords_empty_keeps_all():
    items = [{"title": "任意", "category": ""}]
    assert trend_hunter._filter_by_keywords(items, []) == items


def test_sort_by_heat_desc_with_uniform_time():
    items = [
        {"title": "低", "heat": 10, "time": 0},
        {"title": "高", "heat": 100, "time": 0},
        {"title": "中", "heat": 50, "time": 0},
    ]
    assert [i["title"] for i in trend_hunter._sort_by_heat_time(items)] == ["高", "中", "低"]


def test_sort_time_decay_demotes_stale():
    """heat × 时间衰减：旧热点高热但衰减后低于新鲜低热。"""
    now = time.time()
    stale = {"title": "旧", "heat": 1000, "time": now - 86400}
    fresh = {"title": "新", "heat": 100, "time": now}
    out = trend_hunter._sort_by_heat_time([stale, fresh])
    assert out[0]["title"] == "新"


def test_dedup_near_duplicate_titles():
    items = [
        {"title": "美妆教程", "heat": 100},
        {"title": "美妆教程！", "heat": 90},
        {"title": "显卡评测", "heat": 50},
    ]
    out = trend_hunter._dedup_by_title(items)
    assert len(out) == 2
    titles = {i["title"] for i in out}
    assert "显卡评测" in titles
    assert any(t.startswith("美妆教程") for t in titles)


def test_search_sources_normalizes_results(monkeypatch):
    """检索源经 mcp_client 召回，结果归一化为 TrendItem dict。"""

    async def fake_call(tool, **kw):
        assert kw.get("query")
        return [{"title": "美妆新品发布", "url": "https://x"}]

    monkeypatch.setattr("src.mcp_client.call_tool", fake_call)
    items = trend_hunter._search_sources([{"server": "baidu-search", "tool": "baidu_search"}], "美妆")
    assert len(items) == 1
    assert items[0]["platform"] == "baidu-search"
    assert items[0]["title"] == "美妆新品发布"


def test_search_sources_passes_keyword_arg(monkeypatch):
    """cn-scraper 检索源参数名 keyword（非 query），arg 字段覆盖默认 query。"""
    captured = {}

    async def fake_call(tool, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr("src.mcp_client.call_tool", fake_call)
    trend_hunter._search_sources(
        [{"server": "cn-scraper", "tool": "douyin_search", "arg": "keyword"}], "美妆"
    )
    assert captured.get("keyword") == "美妆"
    assert "query" not in captured


def test_search_sources_uses_source_name_as_platform(monkeypatch):
    """cn-scraper 单 server 多平台：platform 用源名（douyin）非 server 名（cn-scraper）。"""

    async def fake_call(tool, **kw):
        return [{"title": "x", "url": "https://x"}]

    monkeypatch.setattr("src.mcp_client.call_tool", fake_call)
    items = trend_hunter._search_sources(
        [{"server": "cn-scraper", "tool": "douyin_search", "arg": "keyword"}], "美妆", platform="douyin"
    )
    assert items[0]["platform"] == "douyin"


def test_normalize_search_handles_cn_scraper_shapes():
    """cn-scraper 平台字段异构：weibo=text、douyin=page_url、xhs=href 均归一化。"""
    weibo = trend_hunter._normalize_search_results(
        {"items": [{"text": "微博正文", "url": "https://weibo.com/x"}]}, "weibo"
    )
    assert weibo[0]["title"] == "微博正文"
    douyin = trend_hunter._normalize_search_results(
        {"items": [{"title": "抖音标题", "page_url": "https://douyin.com/x"}]}, "douyin"
    )
    assert douyin[0]["url"] == "https://douyin.com/x"
    xhs = trend_hunter._normalize_search_results(
        {"items": [{"title": "小红书标题", "href": "/explore/1"}]}, "xiaohongshu"
    )
    assert xhs[0]["url"] == "/explore/1"


def test_search_sources_works_inside_running_loop(monkeypatch):
    """running loop 内（E2E 全图 async 链）_search_sources 不静默降级为空。"""

    async def fake_call(tool, **kw):
        return [{"title": "x", "url": "https://x"}]

    monkeypatch.setattr("src.mcp_client.call_tool", fake_call)

    async def _inner():
        return trend_hunter._search_sources(
            [{"server": "cn-scraper", "tool": "douyin_search", "arg": "keyword"}],
            "美妆",
            platform="douyin",
        )

    items = asyncio.run(_inner())
    assert len(items) == 1
    assert items[0]["platform"] == "douyin"


# ——— A2 选用源过滤 ———


def test_run_respects_enabled_sources(monkeypatch):
    """enabled 指定后只跑亮起源；bilibili 已切 search 契约，走 _search_sources。"""
    monkeypatch.setattr(trend_hunter, "_fetch_trending", lambda: _fake_yt_data())
    called = []

    def fake_search(servers, q, platform=""):
        called.append(platform)
        return []

    monkeypatch.setattr(trend_hunter, "_search_sources", fake_search)
    trend_hunter.run(enabled=["bilibili"])
    assert called == ["bilibili"]


def test_run_default_excludes_search(monkeypatch):
    """enabled 缺省（chainlit/单测路径）不触发检索源，避免子进程 spawn。"""
    monkeypatch.setattr(trend_hunter, "_fetch_trending", lambda: _fake_yt_data())
    called = []
    monkeypatch.setattr(
        trend_hunter, "_search_sources", lambda servers, q, platform="": called.append(1) or []
    )
    assert isinstance(trend_hunter.run(), list)
    assert called == []


def test_run_search_uses_primary_keyword(monkeypatch):
    """检索源召回用 profile 抽取的主关键词作 query。"""
    monkeypatch.setattr(trend_hunter, "_fetch_trending", lambda: {"x": []})
    captured = {}

    def fake_search(servers, q, platform=""):
        captured["q"] = q
        return []

    monkeypatch.setattr(trend_hunter, "_search_sources", fake_search)
    trend_hunter.run(profile="美妆博主", enabled=["search"])
    assert captured.get("q") == "美妆"


# ——— P5-E candidate_videos 记代表性视频 ———


def test_select_candidate_videos_filters_and_ranks():
    """只留视频平台 + 有 url，按 heat 降序；非视频平台 / 无链接剔除。"""
    items = [
        {"title": "抖音热", "platform": "douyin", "heat": 100, "url": "https://douyin.com/a", "category": ""},
        {"title": "B站热", "platform": "bilibili", "heat": 300, "url": "https://bilibili.com/BV1", "category": ""},
        {"title": "微博热", "platform": "weibo", "heat": 500, "url": "https://weibo.com/x", "category": ""},
        {"title": "无链接", "platform": "douyin", "heat": 999, "url": "", "category": ""},
    ]
    out = trend_hunter.select_candidate_videos(items)
    assert [c["platform"] for c in out] == ["bilibili", "douyin"]
    assert out[0]["url"] == "https://bilibili.com/BV1"
    assert all(set(c) == {"title", "platform", "url", "heat"} for c in out)


def test_select_candidate_videos_caps_at_three():
    """最多 3 条，且截断最高热度。"""
    items = [
        {"title": f"v{i}", "platform": "youtube", "heat": i, "url": f"https://youtu.be/{i}"}
        for i in range(1, 6)
    ]
    out = trend_hunter.select_candidate_videos(items)
    assert len(out) == 3
    assert [c["heat"] for c in out] == [5.0, 4.0, 3.0]

