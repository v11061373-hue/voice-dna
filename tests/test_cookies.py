"""cookie 登录态测试（A4）：只落本地文件，不进 DB。"""

from src import cookies


def test_save_and_get_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(cookies, "COOKIE_PATH", tmp_path / "cookies.json")
    cookies.save_cookie("douyin", "sid=abc")
    assert cookies.get_cookie("douyin") == "sid=abc"
    assert cookies.cookie_status("douyin") == "ok"
    assert cookies.cookie_status("weibo") == "missing"


def test_cookie_persists_to_local_file_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cookies, "COOKIE_PATH", tmp_path / "cookies.json")
    cookies.save_cookie("douyin", "secret=xyz")
    assert (tmp_path / "cookies.json").is_file()
    # 本模块只依赖 json/pathlib，无 sqlite/DB 写入路径（cookie 永不进 sessions.db / checkpoints.db）
    assert "sqlite" not in " ".join(cookies.__dict__.keys())
    assert "sqlite3" not in " ".join(cookies.__dict__.keys())


def test_clear_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(cookies, "COOKIE_PATH", tmp_path / "cookies.json")
    cookies.save_cookie("douyin", "sid=abc")
    cookies.clear_cookie("douyin")
    assert cookies.cookie_status("douyin") == "missing"


def test_auto_scan_without_playwright_reports_chrome(monkeypatch):
    """V2 未装 playwright → 明确反馈「需安装 Chrome」，不抛异常。"""
    import builtins

    def boom(name, *a, **kw):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return builtins.__import__(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", boom)
    result = cookies.auto_scan("douyin", login_url="https://www.douyin.com/")
    assert result["ok"] is False
    assert "Chrome" in result["reason"]
