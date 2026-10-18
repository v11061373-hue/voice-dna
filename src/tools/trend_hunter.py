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
- 抖音/微博/小红书/B站 接 cn-scraper MCP（stdio）走 search 契约，不自写 scraper
  （铁律：检索型源走 stdio MCP）。YouTube 保留 keyless 页面抓取。
- Item 字段改成项目契约 {title, platform, heat, url, category}。
"""

from __future__ import annotations

import asyncio
import dataclasses
import difflib
import importlib.util
import json
import math
import re
import sys
import time as _time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from src import llm, llm_mode


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
    time: float = 0.0  # 时间戳（unix 秒）；0=未知，排序时不衰减

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class Scraper:
    """搬自 snscrape/base.py:180-195：name 类属性 + get_items() 迭代器。"""

    name: str = ""

    def get_items(self) -> Iterator[TrendItem]:
        raise ScraperException(f"{self.name}: 登录态源，契约预留（keyless 未开放）")


# 通用浏览器 UA（YouTube 页面 + HTTP 契约源共用）。
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
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
# 内置 4 平台在此快照；load_plugins() 重算（纳入外部插件）。
_SCRAPERS = {cls.name: cls for cls in Scraper.__subclasses__() if cls.name}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_DIR = _REPO_ROOT / "plugins" / "scrapers"
SOURCES_FILE = _REPO_ROOT / "plugins" / "sources.json"

# sources.json 能力声明（A1）：name → {kind, requires_auth, auth, auth_hint, ...}
# kind: scraper（进程内 Scraper）/ http（URL 契约）/ search（MCP 检索召回）。
_SOURCES: dict[str, dict[str, Any]] = {}
_HTTP_SOURCES: dict[str, str] = {}
_plugins_loaded = False


def load_plugins() -> None:
    """加载外部数据源插件（幂等，改插件后重启生效）。

    1. 进程内：plugins/scrapers/*.py 各定义一个 Scraper 子类，import 后进 __subclasses__。
    2. 能力声明：plugins/sources.json 形如 {name: {kind, requires_auth, ...}}；
       字符串值向后兼容旧 {平台: url} 契约（等同 {kind:http, url}）。
    """
    global _SCRAPERS, _SOURCES, _HTTP_SOURCES, _plugins_loaded
    if _plugins_loaded:
        return
    if PLUGIN_DIR.is_dir():
        for f in sorted(PLUGIN_DIR.glob("*.py")):
            modname = f"voice_dna_plugin_{f.stem}"
            spec = importlib.util.spec_from_file_location(modname, f)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[modname] = module
            try:
                spec.loader.exec_module(module)
            except Exception:  # noqa: BLE001, S110 — 单个插件报错不阻断其余
                pass
    _SOURCES = {}
    _HTTP_SOURCES = {}
    if SOURCES_FILE.is_file():
        try:
            data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    name = str(k)
                    if isinstance(v, str):
                        cfg = {"kind": "http", "url": v}
                    elif isinstance(v, dict):
                        cfg = dict(v)
                    else:
                        continue
                    _SOURCES[name] = cfg
                    if cfg.get("kind") == "http" and "url" in cfg:
                        _HTTP_SOURCES[name] = str(cfg["url"])
        except Exception:  # noqa: BLE001, S110 — sources.json 损坏/缺失不得阻断
            pass
    _SCRAPERS = {cls.name: cls for cls in Scraper.__subclasses__() if cls.name}
    _plugins_loaded = True


def _source_info(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """能力声明 → 前端 chip 渲染字段。default_enabled = 无需登录即默认亮。"""
    requires_auth = bool(cfg.get("requires_auth", False))
    return {
        "name": name,
        "kind": cfg.get("kind", "http" if "url" in cfg else "scraper"),
        "requires_auth": requires_auth,
        "auth": cfg.get("auth", ""),
        "auth_hint": cfg.get("auth_hint", ""),
        "login_url": cfg.get("login_url", ""),
        "default_enabled": not requires_auth,
    }


def list_sources() -> list[dict[str, Any]]:
    """全部数据源能力清单（sources.json 声明 + 未声明的插件 scraper 兜底）。"""
    load_plugins()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, cfg in _SOURCES.items():
        out.append(_source_info(name, cfg))
        seen.add(name)
    for name in _SCRAPERS:
        if name not in seen:
            out.append(
                {
                    "name": name,
                    "kind": "scraper",
                    "requires_auth": False,
                    "auth": "",
                    "auth_hint": "",
                    "login_url": "",
                    "default_enabled": True,
                }
            )
            seen.add(name)
    return out


# ——— A3 关键词召回 / 排序 / 去重 ———

# 赛道关键词词表（零 LLM 兜底；LLM 抽取随 P4-C/D 落地，走 src/llm.py + key）。
_TRACK_KEYWORDS: dict[str, list[str]] = {
    "美妆": ["美妆", "护肤", "彩妆", "口红", "粉底", "眼影", "化妆", "面膜", "美容", "底妆", "腮红", "防晒"],
    "数码": ["数码", "手机", "电脑", "笔记本", "耳机", "相机", "芯片", "硬件", "测评", "显卡", "平板"],
    "职场": ["职场", "工作", "面试", "升职", "简历", "薪资", "副业", "效率", "跳槽", "管理"],
    "美食": ["美食", "探店", "食谱", "做饭", "餐厅", "食材", "烘焙", "小吃", "奶茶"],
    "健身": ["健身", "运动", "减肥", "增肌", "瑜伽", "跑步", "减脂"],
    "旅游": ["旅游", "旅行", "景点", "攻略", "民宿", "自驾"],
    "宠物": ["宠物", "猫", "狗", "养宠", "萌宠"],
    "游戏": ["游戏", "电竞", "手游", "主机", "3A"],
    "汽车": ["汽车", "新能源", "电动车", "驾驶", "试驾"],
    "母婴": ["母婴", "育儿", "宝宝", "奶粉", "早教"],
}


def extract_keywords(profile: str) -> list[str]:
    """从 profile 抽赛道关键词。词表命中返回词表；未知走 LLM 抽取（C2）。

    确定性档：零 LLM，只词表；兜底档：词表无匹配才 LLM；全开档：总是 LLM。
    无 key → 退回词表（可能为空）。
    """
    p = str(profile or "").strip()
    if not p:
        return []
    vocab = _vocab_keywords(p)
    if not llm_mode.should_llm("trend_hunter", has_baseline=bool(vocab)):
        return vocab
    if not llm.has_key():
        return vocab
    try:
        kws = _llm_keywords(p)
        return kws if kws else vocab
    except Exception:  # noqa: BLE001 — LLM 关键词抽取失败回落词表
        return vocab


def _vocab_keywords(p: str) -> list[str]:
    """词表子串命中返回词表；未知返回空。"""
    for track, kws in _TRACK_KEYWORDS.items():
        if track in p:
            return list(kws)
    return []


def _llm_keywords(profile: str) -> list[str]:
    """LLM 抽取赛道关键词（替代 A3 词表，无 baseline 时兜底）。"""
    from src import agents, llm

    prompt = (
        "从账号画像抽取 3-6 个赛道关键词，只输出 JSON 数组（字符串）。\n"
        f"画像: {profile}"
    )
    text = llm.call_llm(prompt, system=agents.system_prompt("trend_hunter"))
    data = llm.parse_json(text)
    if not isinstance(data, list):
        return []
    return [str(k).strip() for k in data if str(k).strip()][:6]


def _filter_by_keywords(items: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    """标题 + 分类命中任一关键词才保留；无关键词不过滤。"""
    if not keywords:
        return items
    kws = [k.lower() for k in keywords]
    out: list[dict[str, Any]] = []
    for item in items:
        text = (str(item.get("title", "")) + " " + str(item.get("category", ""))).lower()
        if any(k in text for k in kws):
            out.append(item)
    return out


_DECAY_HALF_LIFE = 6 * 3600.0  # 热度半衰期 6 小时


def _decay(time_val: float, now: float) -> float:
    if time_val <= 0:
        return 1.0
    age = max(0.0, now - time_val)
    return math.exp(-age * math.log(2) / _DECAY_HALF_LIFE)


def _sort_by_heat_time(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """heat × 时间衰减降序。time=0（未知）不衰减，退化为纯热度排序。"""
    now = _time.time()
    return sorted(
        items,
        key=lambda d: float(d.get("heat") or 0) * _decay(float(d.get("time") or 0), now),
        reverse=True,
    )


def _normalize_title(t: str) -> str:
    return re.sub(r"\W+", "", str(t or ""), flags=re.UNICODE).lower()


def _dedup_by_title(items: list[dict[str, Any]], threshold: float = 0.85) -> list[dict[str, Any]]:
    """标题相似度归组，同类保留最高热度一条（不 embedding）。

    ponytail: O(n²) 贪心归组，n<100 够用；量大再上向量/哈希分桶。
    """
    groups: list[list[dict[str, Any]]] = []
    for item in items:
        norm = _normalize_title(item.get("title", ""))
        placed = False
        for g in groups:
            rep = _normalize_title(g[0].get("title", ""))
            if not norm or not rep:
                continue
            if difflib.SequenceMatcher(None, norm, rep).ratio() >= threshold:
                g.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return [max(g, key=lambda d: float(d.get("heat") or 0)) for g in groups]


# 视频平台（有 url 可转录的源）。weibo/baidu/bing 等非视频平台不进候选。
_VIDEO_PLATFORMS = frozenset({"bilibili", "douyin", "youtube", "xiaohongshu", "xhs"})


def select_candidate_videos(
    items: list[dict[str, Any]], max_count: int = 3
) -> list[dict[str, Any]]:
    """从热点里选代表性视频（最高热度、platform 为视频平台、有 url）入候选。

    P5-E：trend_hunter 抓完顺手记，END 后调用层据此问「转录哪个」。返回
    [{title, platform, url, heat}]，heat 归一为 float。
    """
    cands: list[dict[str, Any]] = [
        {
            "title": str(i.get("title", "")),
            "platform": str(i.get("platform", "")),
            "url": str(i.get("url", "")),
            "heat": float(i.get("heat") or 0),
        }
        for i in items
        if isinstance(i, dict)
        and str(i.get("url", "")).strip()
        and str(i.get("platform", "")) in _VIDEO_PLATFORMS
    ]
    cands.sort(key=lambda c: float(c["heat"]), reverse=True)
    return cands[:max_count]


_MD_TITLE_RE = re.compile(r"^\s*\d+\.\s*\*\*(.+?)\*\*")
_MD_URL_RE = re.compile(r"🔗\s*(\S+)")


def _normalize_search_results(raw: Any, platform: str) -> list[dict[str, Any]]:
    """检索源返回（list / dict / JSON 字符串 / markdown 文本）归一化为 TrendItem dict。"""
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        items = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        for key in ("results", "items", "data", "list"):
            v = raw.get(key)
            if isinstance(v, list):
                items = [r for r in v if isinstance(r, dict)]
                break
        if not items and ("title" in raw or "url" in raw or "link" in raw):
            items = [raw]
    elif isinstance(raw, str):
        try:
            return _normalize_search_results(json.loads(raw), platform)
        except Exception:  # noqa: BLE001 — JSON 解析失败回退 markdown 解析
            items = _parse_markdown_search(raw)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(items):
        title = str(r.get("title") or r.get("name") or r.get("text") or "").strip()
        if not title:
            continue
        url = str(r.get("url") or r.get("link") or r.get("page_url") or r.get("href") or "")
        out.append(
            {
                "title": title,
                "platform": platform,
                "heat": float(len(items) - i),  # 排名合成热度：靠前更高
                "url": url,
                "category": "",
                "time": _time.time(),
            }
        )
    return out


def _parse_markdown_search(text: str) -> list[dict[str, Any]]:
    """解析 baidu-search-mcp 的 markdown 输出（`N. **标题**` + `🔗 url`）。"""
    items: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in text.splitlines():
        m = _MD_TITLE_RE.match(line)
        if m:
            cur = {"title": m.group(1).strip()}
            items.append(cur)
            continue
        m = _MD_URL_RE.search(line)
        if m and cur is not None:
            cur["url"] = m.group(1)
    return items


async def _search_one(
    server: str, tool: str, query: str, arg: str = "query", platform: str = ""
) -> list[dict[str, Any]]:
    from src import mcp_client  # 懒加载，避循环 import

    try:
        raw = await mcp_client.call_tool(f"{server}.{tool}", **{arg: query})
    except Exception:  # noqa: BLE001 — 检索源不可达 / 未知 tool 优雅降级为空
        return []
    return _normalize_search_results(raw, platform or server)


def _search_sources(
    servers: list[dict[str, Any]], query: str, platform: str = ""
) -> list[dict[str, Any]]:
    """检索源关键词召回（同步封装）。每 server spawn 一次子进程（~1-2s，可接受）。

    running loop 内（E2E 全图 async 链）asyncio.run 会嵌套冲突，起线程跑 stdio
    阻塞 IO，避免静默降级为空。
    """

    async def _all() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in servers:
            out.extend(
                await _search_one(
                    str(s.get("server", "")),
                    str(s.get("tool", "")),
                    query,
                    str(s.get("arg", "query")),
                    platform,
                )
            )
        return out

    def _blocking() -> list[dict[str, Any]]:
        try:
            return asyncio.run(_all())
        except Exception:  # noqa: BLE001 — 线程内检索失败降级为空
            return []

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _blocking()  # 无 running loop：脚本顶层 / 单源直调
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_blocking).result()


def _fetch_http(url: str) -> list[dict[str, Any]]:
    """HTTP 数据源契约：GET url 返回 TrendItem 形状 list，失败返回空。"""
    try:
        resp = httpx.get(url, headers={"User-Agent": _BROWSER_UA}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — HTTP 源失败返回空
        return []


def _run_scraper(scraper_cls: type[Scraper]) -> list[dict[str, Any]]:
    try:
        return [item.to_dict() for item in scraper_cls().get_items()]
    except ScraperException:
        return []


def _gather_source(name: str, query: str) -> list[dict[str, Any]]:
    """按源名分派：search→检索召回，http→URL 契约，scraper→进程内 Scraper。"""
    cfg = _SOURCES.get(name)
    if cfg is not None:
        kind = cfg.get("kind", "http" if "url" in cfg else "scraper")
        if kind == "search":
            return _search_sources(list(cfg.get("servers") or []), query, platform=name)
        if kind == "http" and "url" in cfg:
            return _fetch_http(str(cfg["url"]))
        if name in _SCRAPERS:
            return _run_scraper(_SCRAPERS[name])
        return []
    # 未在 sources.json 声明：退回插件 scraper / 旧 HTTP 契约
    if name in _SCRAPERS:
        return _run_scraper(_SCRAPERS[name])
    if name in _HTTP_SOURCES:
        return _fetch_http(_HTTP_SOURCES[name])
    return []


def run(profile: str = "", platform: str = "", enabled: list[str] | None = None) -> list[dict[str, Any]]:
    """统一入口：选源 → 召回 → 关键词过滤 → heat×时间排序 → 标题去重。

    - platform 指定：只跑该源。
    - enabled 指定（前端 chip 选中集合）：只跑这些源；含 "search" 走检索召回。
    - 均缺省：跑全部 scraper + http 源（不触发检索源，避免子进程 spawn）。
    关键词抽取走词表（LLM 抽取随 P4-C/D 落地）。
    """
    load_plugins()
    keywords = extract_keywords(profile)
    query = (keywords[0] if keywords else profile).strip() or "热点"

    if platform:
        items = _gather_source(platform, query)
    else:
        if enabled is not None:
            names = list(enabled)
        else:
            names = [n for n in _SCRAPERS] + [
                n for n in _SOURCES if n not in _SCRAPERS and _SOURCES[n].get("kind") != "search"
            ]
        items = []
        for name in names:
            items.extend(_gather_source(name, query))

    items = _filter_by_keywords(items, keywords)
    items = _sort_by_heat_time(items)
    return _dedup_by_title(items)
