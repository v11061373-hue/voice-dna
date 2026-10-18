"""download_video tool — 视频 url → 本地临时媒体文件（P5-C）。

平台：
- bilibili：直下（无登录）。解析 bvid → view API 拿 cid → playurl API（fnval=0）拿
  mp4 durl → 带 UA/Referer 抓字节（403 先查 header，参考 dy_transcribe.py fetch()）。
- douyin/xhs：需登录态，复用 dy_transcribe.py CDP :9222 抓媒体流法（本机 Chrome 已
  登录）；voice-dna 未列 websockets 依赖，P5-C 只给指引：贴 cookie 到
  ~/.voice-dna/cookies.json（src/cookies.py 单路径）。

铁律：下载落 tempfile 临时目录（不落 repo），进程退出 cleanup 删；cookie 只
~/.voice-dna/cookies.json；key 只 os.environ。
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urlparse

import httpx

from src.cookies import COOKIE_PATH, get_cookie

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA, "Referer": "https://www.bilibili.com/"}

_BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")

_VIDEO_HOSTS = (
    "bilibili.com",
    "douyin.com",
    "xiaohongshu.com",
    "xhslink.com",
    "youtube.com",
    "youtu.be",
)


class VideoDownloadError(Exception):
    """视频下载失败（平台不支持 / 需登录态 / 解析失败）。"""


def is_video_url(text: str) -> str | None:
    """从文本抽第一个视频平台链接；非视频回 None（甩链接模式入口判定）。"""
    for m in re.finditer(r"https?://[^\s]+", text):
        u = m.group(0)
        if any(h in urlparse(u).netloc for h in _VIDEO_HOSTS):
            return u
    return None



def _platform(url: str) -> str:
    if "bilibili.com" in url:
        return "bilibili"
    if "douyin.com" in url:
        return "douyin"
    if "xiaohongshu.com" in url or "xhslink.com" in url:
        return "xhs"
    return "unknown"


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.get(url, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_bytes(url: str) -> bytes:
    resp = httpx.get(url, headers=_HEADERS, timeout=600, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _bvid(url: str) -> str:
    m = _BVID_RE.search(url)
    if not m:
        raise VideoDownloadError(f"无法从 url 解析 bvid：{url}")
    return m.group(0)


def _suffix(url: str) -> str:
    return os.path.splitext(urlparse(url).path)[1] or ".mp4"


def _download_bilibili(url: str, outdir: str) -> str:
    bvid = _bvid(url)
    view = _get_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
    cid = (view.get("data") or {}).get("cid")
    if not cid:
        raise VideoDownloadError(
            f"bilibili view 无 cid（bvid={bvid}）：{view.get('code')} {view.get('message')}"
        )
    play = _get_json(
        "https://api.bilibili.com/x/player/playurl",
        {"bvid": bvid, "cid": cid, "fnval": 0, "qn": 64},
    )
    durl = (play.get("data") or {}).get("durl") or []
    if not durl or not durl[0].get("url"):
        raise VideoDownloadError(
            f"bilibili playurl 无 durl（bvid={bvid}）：{play.get('code')} {play.get('message')}"
        )
    media_url = str(durl[0]["url"])
    path = os.path.join(outdir, f"{bvid}{_suffix(media_url)}")
    with open(path, "wb") as f:
        f.write(_fetch_bytes(media_url))
    return path


def _download_douyin_or_xhs(url: str, outdir: str) -> str:
    """douyin/xhs 下载需登录态。P5-C 只给指引，下载接线留后补。

    已验证路径 dy_transcribe.py（agent-senses）用 CDP :9222 + websockets 抓媒体流；
    voice-dna 未列 websockets 依赖，故 P5-C 不接入。用户可贴 cookie 到 cookies.json。
    """
    platform = "xhs" if ("xiaohongshu.com" in url or "xhslink.com" in url) else "douyin"
    if get_cookie(platform):
        raise VideoDownloadError(
            f"{platform} 已存 cookie（{COOKIE_PATH}）但下载未接线："
            f"复用 dy_transcribe.py CDP :9222 抓流法，P5-C 后补"
        )
    raise VideoDownloadError(
        f"{platform} 下载需登录态：本机 Chrome 以 --remote-debugging-port=9222 启动并登录"
        f"（复用 dy_transcribe.py CDP 抓流法），或贴 cookie 到 {COOKIE_PATH}"
    )


_dl_dir_path: str | None = None


def _dl_dir() -> str:
    global _dl_dir_path
    if _dl_dir_path is None:
        _dl_dir_path = tempfile.mkdtemp(prefix="voice-dna-download-")
        atexit.register(cleanup)
    return _dl_dir_path


def cleanup() -> None:
    global _dl_dir_path
    if _dl_dir_path is not None:
        shutil.rmtree(_dl_dir_path, ignore_errors=True)
        _dl_dir_path = None


def run(url: str = "", **kwargs: Any) -> dict[str, Any]:
    """视频 url → {"path": 本地临时媒体文件绝对路径}。"""
    if not url:
        raise ValueError("download_video 需要 url（视频链接）")
    platform = _platform(url)
    if platform == "bilibili":
        path = _download_bilibili(url, _dl_dir())
    elif platform in ("douyin", "xhs"):
        path = _download_douyin_or_xhs(url, _dl_dir())
    else:
        raise VideoDownloadError(f"不支持该平台下载（bilibili/douyin/xhs）：{url}")
    return {"path": path}
