"""热点猎人 tool 契约测试。"""

import httpx

from src.tools import trend_hunter


def _fake_popular() -> dict:
    return {
        "code": 0,
        "data": {
            "list": [
                {"title": "热点A", "bvid": "BV1", "tname": "游戏", "stat": {"view": 123456}},
                {"title": "热点B", "bvid": "BV2", "tname": "科技", "stat": {"view": 888}},
            ]
        },
    }


def test_run_returns_list(monkeypatch):
    monkeypatch.setattr(trend_hunter, "_fetch_popular", _fake_popular)
    assert isinstance(trend_hunter.run(), list)


def test_bilibili_parses_real_items(monkeypatch):
    monkeypatch.setattr(trend_hunter, "_fetch_popular", _fake_popular)
    items = trend_hunter.run(platform="bilibili")
    assert len(items) == 2
    assert items[0]["platform"] == "bilibili"
    assert items[0]["title"] == "热点A"
    assert items[0]["heat"] == 123456.0
    assert items[0]["category"] == "游戏"
    assert items[0]["url"].endswith("BV1")


def test_bilibili_network_error_degrades(monkeypatch):
    def boom():
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(trend_hunter, "_fetch_popular", boom)
    assert trend_hunter.run(platform="bilibili") == []


def test_fetch_popular_sends_user_agent(monkeypatch):
    """B站 412 根因：请求须带 User-Agent，否则被拒。"""
    captured: dict = {}

    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": {"list": []}}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResp()

    monkeypatch.setattr(trend_hunter.httpx, "get", fake_get)
    trend_hunter._fetch_popular()
    assert "User-Agent" in (captured.get("headers") or {})


def test_no_keyless_source_degrades():
    assert trend_hunter.run(platform="douyin") == []
    assert trend_hunter.run(platform="weibo") == []


def test_item_has_contract_keys():
    item = trend_hunter.TrendItem(title="热点", platform="douyin", heat=1_000_000, url="https://x", category="美妆")
    d = item.to_dict()
    assert set(d) == {"title", "platform", "heat", "url", "category"}
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
