"""风格模仿 tool — 步骤 6 结构化抽取（LLM 抽 7 字段风格卡）。

占位返回 persona。不搬现成风格迁移开源（C 无货，见 搬运标签清单.md）。
素材：stylellm_chat 中文 prompt 范例 + lobe-chat-agents 文案配方。
"""

import json
from typing import Any

from src import llm, llm_mode
from src.schemas import STYLE_CARD_FIELDS  # 单一真相源（C3 schema 硬门共用）

__all__ = [
    "FALLBACK_STYLE_CARD",
    "STYLE_CARD_FIELDS",
    "STYLE_CARD_PROMPT_TEMPLATE",
    "parse_style_card",
    "run",
]

# 抽取 prompt 模板（借 stylellm_chat 中文文风 prompt 范例 + lobe-chat-agents
# 文案配方）。{profile}/{topics}/{samples} 是 .format() 占位符；输出 JSON。
STYLE_CARD_PROMPT_TEMPLATE = """\
# Role: 内容风格抽取器
## 任务
读入博主的文案样本，抽取其表达 DNA，输出结构化风格卡（JSON）。
## 输入
- 账号画像: {profile}
- 目标选题: {topics}
- 文案样本: {samples}
- 转录逐字稿: {transcripts}
## 抽取维度（缺样本就标注「未知」，不编造）
1. persona 人设/语气
2. voice 说话腔调
3. catchphrases 口癖/口头禅（原样摘录词表）
4. sentence_patterns 句式（开头句式/长短句/反问）
5. pacing 节奏（段落长度/停顿）
6. narrative_structure 叙事结构
7. visual_style 视觉风格
## 输出 schema（只输出 JSON）
{{"persona": "...", "voice": "...", "catchphrases": ["..."], "sentence_patterns": ["..."], "pacing": "...", "narrative_structure": "...", "visual_style": "..."}}
"""


def _fmt_transcripts(transcripts: dict[str, str] | None) -> str:
    """转录逐字稿 dict → 可读串（学真实口播风格用）；空回「（无）」。"""
    if not transcripts:
        return "（无）"
    parts = [f"{url}：{str(text).strip()[:200]}" for url, text in transcripts.items()]
    return "\n".join(parts)


def parse_style_card(text: str) -> dict[str, Any]:
    """解析 LLM 返回的 JSON 风格卡。剥 markdown 包裹，缺字段补默认。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # 去开头 ```json 或 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    data = json.loads(text)
    card: dict[str, Any] = {}
    for field in STYLE_CARD_FIELDS:
        if field in data:
            card[field] = data[field]
        elif field in ("catchphrases", "sentence_patterns"):
            card[field] = []
        else:
            card[field] = "未知"
    return card


# 无 key 降级卡（确定性，7 字段全）。有 key（llm.has_key()）时真调 LLM。
FALLBACK_STYLE_CARD: dict[str, Any] = {
    "persona": "内容创作者（未配置 DeepSeek，降级通用风格）",
    "voice": "口语化、直白",
    "catchphrases": [],
    "sentence_patterns": ["短句", "反问"],
    "pacing": "快节奏",
    "narrative_structure": "问题-分析-结论",
    "visual_style": "简洁字幕",
}


def run(**kwargs: Any) -> dict[str, Any]:
    # C0：确定性档（或开关关）零 LLM，走降级卡；有 key 且允许才真调 LLM。
    if not llm_mode.llm_enabled("style_mimic") or not llm.has_key():
        return dict(FALLBACK_STYLE_CARD)
    profile = kwargs.get("account_profile", "") or kwargs.get("profile", "")
    topics = kwargs.get("topics", [])
    samples = kwargs.get("samples", "")
    transcripts = kwargs.get("transcripts") or {}
    prompt = STYLE_CARD_PROMPT_TEMPLATE.format(
        profile=profile, topics=topics, samples=samples, transcripts=_fmt_transcripts(transcripts)
    )
    text = llm.call_llm(prompt)
    return parse_style_card(text)
