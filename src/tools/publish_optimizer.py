"""发布优化 tool — 步骤 5 搬 BrightBean Studio MCP + postpilot + Wechatsync。

只借 schema 形状 + 启发式规则，不搬实现、不真调发布 API（项目无发布账号）。
输出契约: {"platform", "best_time", "tags", "hashtags", "description"}。

来源（file:line）:
- 发布计划字段 schema: brightbeanxyz/brightbean-studio
  apps/composer/models.py:216 Post.caption(描述)/tags(JSONField list)/
  scheduled_at/proposed_publish_at(时间)；
  apps/mcp/handlers.py:190 _list_accounts 每平台 char_limit(字段差异)。
- 最佳发布时间规则: postpilot scripts/threads_generate_daily.py:20
  DEFAULT_SLOTS="09-00,...,22-00"（白天时段槽位）；
  strategy/06-operations/01-best-posting-times.md:时间次要、白天即可。
- 多平台适配 schema: wechatsync/Wechatsync packages/core/src/types.ts:8
  Article{title,markdown,tags?,...} + :50 PlatformCapability('tags'|'schedule')。
适配: best_time 取 postpilot 白天槽位按平台确定性取一条；tags/hashtags
先读 script 已有字段，缺则从正文确定性提取 #hashtag / 关键词。
"""

import re
from typing import Any

_DEFAULT_PLATFORM = "threads"
# postpilot DEFAULT_SLOTS 的白天时段（09:00—22:00）。
_SLOTS = ["09:00", "10:30", "12:00", "13:30", "15:00",
          "16:30", "18:00", "19:30", "21:00", "22:00"]
# ponytail: 平台→白天槽位，值取自 _SLOTS（postpilot 白天档），非逐平台调研；
# 时间次要（postpilot 策略文档原话），要精确到平台再加数据源。
_BEST_TIMES = {
    "threads": "09:00",
    "instagram": "12:00",
    "tiktok": "19:30",
    "youtube": "18:00",
    "linkedin": "09:00",
    "twitter": "09:00",
    "xiaohongshu": "12:00",
    "douyin": "19:30",
    "bilibili": "18:00",
}
_TEXT_KEYS = ("body", "title", "hook", "summary", "caption")
_STOPWORDS = frozenset((
    "the", "a", "an", "is", "are", "and", "or", "to", "of", "in", "for",
    "with", "on", "this", "that", "it", "you", "your", "we", "my", "i",
    "at", "as", "be", "by", "not", "ai", "social", "media",
))


def _best_time(platform: str) -> str:
    return _BEST_TIMES.get(platform, _SLOTS[0])


def _extract(text: str) -> tuple[list[str], list[str]]:
    """从正文确定性提取 (tags, hashtags)：#标签 + 词频关键词。"""
    hashtags = [t[1:] for t in re.findall(r"#[\w一-鿿-]+", text)]
    words = [w for w in re.findall(r"[A-Za-z][\w-]{2,}|[一-鿿]{2,}", text.lower())
             if w not in _STOPWORDS]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq, key=lambda w: (-freq[w], w))
    tags = [w for w in ranked if w not in hashtags][:5]
    return tags, hashtags


def run(**kwargs: Any) -> dict[str, Any]:
    script = kwargs.get("script") or {}
    platform = script.get("platform") or _DEFAULT_PLATFORM
    text = " ".join(str(v) for k, v in script.items()
                    if k in _TEXT_KEYS and isinstance(v, str))
    tags = script.get("tags") if isinstance(script.get("tags"), list) else script.get("keywords")
    hashtags = script.get("hashtags")
    if not isinstance(tags, list) or not isinstance(hashtags, list):
        t, h = _extract(text)
        tags = tags if isinstance(tags, list) else t
        hashtags = hashtags if isinstance(hashtags, list) else h
    return {
        "platform": platform,
        "best_time": _best_time(platform),
        "tags": tags,
        "hashtags": hashtags,
        "description": str(script.get("body") or script.get("caption")
                           or script.get("summary") or ""),
    }
