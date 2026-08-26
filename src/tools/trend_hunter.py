"""热点猎人 tool — 步骤 4 搬 snscrape 接口结构实现。

搬运来源（搬接口设计，不搬失效爬虫代码）：
- snscrape/base.py:108-117  Item 抽象基类（类型化 item + __str__）→ 本文件 TrendItem
- snscrape/base.py:172-173  ScraperException
- snscrape/base.py:180-195  Scraper 基类（name 类属性 + get_items() 迭代器）
- snscrape/_cli.py:252-262  按 name 分派注册表（__subclasses__ 自动发现）
- MediaCrawler media_platform/weibo/client.py:25-36 每平台一包 client.py 组织方式
  （仅参考结构，其实现依赖 httpx+playwright+tenacity+登录态，不搬）

改了什么（适配点）：
- 去 requests/httpx/playwright 依赖，全部 stdlib（dataclasses）。
- 无 key/无登录：抖音/TikTok/微博热点在 snscrape（requests + 已失效）与
  MediaCrawler（playwright + 登录态）均无现成无 key 源可搬 → 登录态源契约预留，返回空。
- Item 字段改成项目契约 {title, platform, heat, url, category}。
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from typing import Any

import httpx


class ScraperException(Exception):
    """搬自 snscrape/base.py:172。"""


@dataclasses.dataclass
class TrendItem:
    """类型化热点 item，搬自 snscrape/base.py:108-117 的 Item 基类思路。"""

    title: str
    platform: str
    heat: float
    url: str
    category: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class Scraper:
    """搬自 snscrape/base.py:180-195：name 类属性 + get_items() 迭代器。"""

    name: str = ""

    def get_items(self) -> Iterator[TrendItem]:
        raise ScraperException(f"{self.name}: 登录态源，契约预留（keyless 未开放）")


class DouyinTrendScraper(Scraper):
    """抖音热点。snscrape 无抖音模块，MediaCrawler 需 playwright 登录态。"""

    name = "douyin"


class WeiboTrendScraper(Scraper):
    """微博热搜。snscrape 仅 user 时间线（requests+登录），MediaCrawler 需登录态。"""

    name = "weibo"


BILIBILI_POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular"

# B站 API 无 User-Agent 返回 412 Precondition Failed，须带 UA。
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _fetch_popular() -> dict[str, Any]:
    """B站热门 keyless API（已验证带 UA 200 可用），返回解析后的 JSON dict。"""
    resp = httpx.get(
        BILIBILI_POPULAR_URL,
        params={"ps": 20, "pn": 1},
        headers={"User-Agent": _BROWSER_UA},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


class BilibiliTrendScraper(Scraper):
    """B站热门。keyless API 可用（微博 403/知乎 401 需登录，故用 B站）。"""

    name = "bilibili"

    def get_items(self) -> Iterator[TrendItem]:
        try:
            data = _fetch_popular()
        except Exception as exc:
            raise ScraperException(f"bilibili: {exc}") from exc
        if data.get("code") != 0:
            raise ScraperException(f"bilibili: code={data.get('code')}")
        for v in (data.get("data") or {}).get("list") or []:
            stat = v.get("stat") or {}
            yield TrendItem(
                title=str(v.get("title") or ""),
                platform="bilibili",
                heat=float(stat.get("view") or 0),
                url=f"https://www.bilibili.com/video/{v.get('bvid', '')}",
                category=str(v.get("tname") or ""),
            )


# ——— YouTube ———
# 搬自 snscrape/modules/youtube.py 的 keyless 思路：不调 API，直接抓
# /feed/trending 页面内嵌的 `var ytInitialData = {...}` JSON，递归找
# videoRenderer。比写死 6 层路径稳（YouTube 结构常改）。

YOUTUBE_TRENDING_URL = "https://www.youtube.com/feed/trending"
_YT_INITIAL_DATA_RE = re.compile(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)


def _fetch_trending() -> dict[str, Any]:
    """抓 YouTube Trending 页面，抽出 ytInitialData 解析为 dict。"""
    resp = httpx.get(
        YOUTUBE_TRENDING_URL,
        params={"gl": "US", "hl": "en"},
        headers={"User-Agent": _BROWSER_UA},
        timeout=10,
    )
    resp.raise_for_status()
    m = _YT_INITIAL_DATA_RE.search(resp.text)
    if not m:
        raise ScraperException("youtube: ytInitialData 未找到")
    return json.loads(m.group(1))


def _walk_video_renderers(obj: Any, out: list[dict[str, Any]]) -> None:
    """递归收集所有 videoRenderer（任意嵌套深度）。"""
    if isinstance(obj, dict):
        if "videoRenderer" in obj:
            out.append(obj["videoRenderer"])
        for v in obj.values():
            _walk_video_renderers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_video_renderers(v, out)


def _parse_view_count(text: str) -> float:
    return float("".join(ch for ch in text if ch.isdigit()) or 0)


def _parse_yt_trending(data: dict[str, Any]) -> list[TrendItem]:
    """ytInitialData → TrendItem 列表。viewCountText 抽数字当 heat，category 留空。"""
    renderers: list[dict[str, Any]] = []
    _walk_video_renderers(data, renderers)
    out: list[TrendItem] = []
    for vr in renderers:
        title_runs = (vr.get("title") or {}).get("runs") or [{}]
        title = str((title_runs[0].get("text") or "") if title_runs else "")
        vc = vr.get("viewCountText") or {}
        vc_text = vc.get("simpleText") or ""
        if not vc_text:
            vc_text = ((vc.get("runs") or [{}])[0].get("text") or "")
        out.append(
            TrendItem(
                title=title,
                platform="youtube",
                heat=_parse_view_count(str(vc_text)),
                url=f"https://www.youtube.com/watch?v={vr.get('videoId', '')}",
                category="",
            )
        )
    return out


class YouTubeTrendScraper(Scraper):
    """YouTube Trending。keyless 抓页面 ytInitialData（海外网络可用）。"""

    name = "youtube"

    def get_items(self) -> Iterator[TrendItem]:
        try:
            data = _fetch_trending()
        except Exception as exc:
            raise ScraperException(f"youtube: {exc}") from exc
        yield from _parse_yt_trending(data)


# 按平台分派注册表 — 搬自 snscrape/_cli.py:252-262 的 name→class 映射。
_SCRAPERS = {cls.name: cls for cls in Scraper.__subclasses__() if cls.name}


def run(**kwargs: Any) -> list[dict[str, Any]]:
    """统一入口 — 按 platform 分派（缺省聚合全部平台），返回热点 dict 列表。

    签名不变；空输入 / 登录态源 / 异常均优雅返回空（非 dict）。
    """
    platform = str(kwargs.get("platform") or "")
    scrapers = [_SCRAPERS[platform]] if platform in _SCRAPERS else list(_SCRAPERS.values())
    out: list[dict[str, Any]] = []
    for cls in scrapers:
        try:
            out.extend(item.to_dict() for item in cls().get_items())
        except ScraperException:
            continue
    return out
