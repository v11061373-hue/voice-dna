"""数据源注册表测试（A1 能力声明 + A2 选用过滤）。"""

import json

from src.tools import trend_hunter


def _isolate_sources(monkeypatch, tmp_path):
    """隔离 sources.json 加载状态：路径 + 状态全走 monkeypatch，pytest 自动还原。"""
    monkeypatch.setattr(trend_hunter, "SOURCES_FILE", tmp_path / "sources.json")
    monkeypatch.setattr(trend_hunter, "PLUGIN_DIR", tmp_path / "scrapers")
    monkeypatch.setattr(trend_hunter, "_SOURCES", {})
    monkeypatch.setattr(trend_hunter, "_HTTP_SOURCES", {})
    monkeypatch.setattr(trend_hunter, "_plugins_loaded", False)


def test_sources_capability_declaration(monkeypatch, tmp_path):
    """A1：sources.json 从 URL 契约扩成能力声明（requires_auth/auth/auth_hint）。"""
    _isolate_sources(monkeypatch, tmp_path)
    (tmp_path / "sources.json").write_text(
        json.dumps(
            {
                "douyin": {"kind": "scraper", "requires_auth": True, "auth": "cookie", "auth_hint": "提示"},
                "myapi": {"kind": "http", "url": "http://x/trends", "requires_auth": False},
            }
        ),
        encoding="utf-8",
    )
    trend_hunter.load_plugins()
    infos = {s["name"]: s for s in trend_hunter.list_sources()}
    assert infos["douyin"]["requires_auth"] is True
    assert infos["douyin"]["auth"] == "cookie"
    assert infos["douyin"]["auth_hint"] == "提示"
    assert infos["myapi"]["kind"] == "http"
    assert infos["myapi"]["default_enabled"] is True


def test_sources_backward_compat_string_url(monkeypatch, tmp_path):
    """旧契约 {平台: url} 仍识别为 http 源（字符串值 = {kind:http, url}）。"""
    _isolate_sources(monkeypatch, tmp_path)
    (tmp_path / "sources.json").write_text(json.dumps({"myapi": "http://x/trends"}), encoding="utf-8")
    trend_hunter.load_plugins()
    assert trend_hunter._HTTP_SOURCES == {"myapi": "http://x/trends"}


def test_search_source_declares_servers(monkeypatch, tmp_path):
    """A3：search 源声明 retrieval server + tool，供关键词召回分派。"""
    _isolate_sources(monkeypatch, tmp_path)
    (tmp_path / "sources.json").write_text(
        json.dumps(
            {"search": {"kind": "search", "servers": [{"server": "baidu-search", "tool": "baidu_search"}]}}
        ),
        encoding="utf-8",
    )
    trend_hunter.load_plugins()
    infos = {s["name"]: s for s in trend_hunter.list_sources()}
    assert infos["search"]["kind"] == "search"
