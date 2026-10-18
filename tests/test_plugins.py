"""外部数据源插件测试 — 进程内 Scraper 目录 + HTTP 契约。"""

import json
import sys

from src.tools import trend_hunter


def _isolate(monkeypatch, tmp_path):
    """隔离插件加载状态：路径 + 状态全走 monkeypatch，pytest 自动还原。"""
    monkeypatch.setattr(trend_hunter, "PLUGIN_DIR", tmp_path / "scrapers")
    monkeypatch.setattr(trend_hunter, "SOURCES_FILE", tmp_path / "sources.json")
    monkeypatch.setattr(trend_hunter, "_HTTP_SOURCES", {})
    monkeypatch.setattr(trend_hunter, "_SOURCES", {})
    monkeypatch.setattr(trend_hunter, "_plugins_loaded", False)


def test_http_source_contract(monkeypatch, tmp_path):
    """HTTP 契约：sources.json {平台:url}，GET url 返回 TrendItem 形状 list。"""
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "sources.json").write_text(
        json.dumps({"myapi": "http://example.com/trends"}), encoding="utf-8"
    )

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "热点X", "platform": "myapi", "heat": 100, "url": "", "category": "美妆"}]

    monkeypatch.setattr(trend_hunter.httpx, "get", lambda url, **kw: _Resp())
    assert trend_hunter.run(platform="myapi") == [
        {"title": "热点X", "platform": "myapi", "heat": 100, "url": "", "category": "美妆"}
    ]


def test_http_source_error_degrades(monkeypatch, tmp_path):
    """HTTP 源网络失败优雅降级为空列表。"""
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "sources.json").write_text(json.dumps({"bad": "http://x"}), encoding="utf-8")

    def boom(url, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(trend_hunter.httpx, "get", boom)
    assert trend_hunter.run(platform="bad") == []


def test_plugin_dir_discovery(monkeypatch, tmp_path):
    """进程内目录：plugins/scrapers/*.py 定义 Scraper 子类，run() 按 name 分派。"""
    _isolate(monkeypatch, tmp_path)
    orig_scrapers = dict(trend_hunter._SCRAPERS)
    orig_loaded = trend_hunter._plugins_loaded
    d = tmp_path / "scrapers"
    d.mkdir()
    (d / "myplug.py").write_text(
        "from src.tools.trend_hunter import Scraper, TrendItem\n"
        "class MyPluginScraper(Scraper):\n"
        "    name = 'myplug'\n"
        "    def get_items(self):\n"
        "        yield TrendItem(title='t', platform='myplug', heat=1, url='', category='')\n",
        encoding="utf-8",
    )
    try:
        items = trend_hunter.run(platform="myplug")
        assert len(items) == 1
        assert items[0]["platform"] == "myplug"
        assert items[0]["title"] == "t"
    finally:
        # 清理：恢复注册表/加载态，摘除导入的插件模块，避免污染其它测试
        trend_hunter._SCRAPERS = orig_scrapers
        trend_hunter._plugins_loaded = orig_loaded
        sys.modules.pop("voice_dna_plugin_myplug", None)
