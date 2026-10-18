"""数据源登录态 cookie（A4）。

铁律：
- cookie 只落 ~/.voice-dna/cookies.json（本地文件），永不进 sessions.db / checkpoints.db。
- key 只 os.environ（内存），不落盘。
- V2 自动扫码 playwright 懒加载（仅触发时 import + 起浏览器），V1 手动贴不依赖它。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COOKIE_PATH = Path.home() / ".voice-dna" / "cookies.json"


def load_cookies() -> dict[str, str]:
    """读本地 cookie 文件，坏文件/缺失优雅返回空 dict。"""
    try:
        if COOKIE_PATH.is_file():
            data = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001, S110 — 本地文件损坏不得阻断
        pass
    return {}


def save_cookie(platform: str, cookie: str) -> None:
    """保存某平台 cookie 到本地文件（唯一落点）。"""
    data = load_cookies()
    data[str(platform)] = str(cookie)
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cookie(platform: str) -> str | None:
    return load_cookies().get(str(platform))


def cookie_status(platform: str) -> str:
    """统一入口状态：ok=有本地 cookie，missing=无。"""
    return "ok" if get_cookie(platform) else "missing"


def clear_cookie(platform: str) -> None:
    data = load_cookies()
    data.pop(str(platform), None)
    COOKIE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def auto_scan(platform: str, login_url: str = "") -> dict[str, Any]:
    """V2 自动扫码抓 cookie（playwright 懒加载）。

    ponytail: 完整扫码流程（开 Chrome → 跳登录页 → 等扫码 → 抓 cookie）依赖真实
    浏览器 + 登录页，此处只做依赖检测 + 明确反馈；真实联调留后续。未装 playwright
    返回「需安装 Chrome」而非报错。
    """
    try:
        from playwright.sync_api import (  # type: ignore[import-not-found]  # 懒加载，仅 V2 触发
            sync_playwright,
        )
    except ImportError:
        return {"ok": False, "reason": "需安装 Chrome：pip install playwright && playwright install chromium"}
    if not login_url:
        return {"ok": False, "reason": "该平台未配置 login_url，无法自动跳转"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url)
            # 等待用户扫码登录：轮询 cookie 变化，最多 120s（真实联调校准超时）
            import time

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if any(c["name"].lower() in ("sessionid", "sid", "passport") for c in context.cookies()):
                    break
                time.sleep(2)
            jar = context.cookies()
            browser.close()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in jar)
        save_cookie(platform, cookie_str)
        return {"ok": True, "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — 浏览器/网络异常优雅反馈
        return {"ok": False, "reason": str(exc)}
