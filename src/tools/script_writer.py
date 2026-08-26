"""脚本文案 tool — 步骤 4 搬 MoneyPrinterTurbo prompt + NarratoAI 分镜 schema。

搬运源（手术式，见 README「脚本文案输出契约」）：
- 脚本生成 prompt 搬 MoneyPrinterTurbo `app/services/llm.py:29-44`
  (`DEFAULT_SCRIPT_SYSTEM_PROMPT`) + `llm.py:467-500` (`build_script_prompt`
  运行上下文：主题/段落数/语言)。改：中文化 + 约束收敛为「直入主题/无 Markdown/
  无旁白指示词/同语言」。
- 分镜 scene schema 搬 NarratoAI `app/services/prompts/film_tv_narration/
  script_generation.py:131-152`（picture→visual、narration→narration、
  timestamp→duration）。
- 五段式 HOOK/CURIOSITY/BODY/TWIST/CTA 搬 ai-youtube-shorts
  `ai_engine.py:105-119`（时间轴）。

MVP 无 LLM 管线：确定性「模板填充」生成可用脚本作降级。SCRIPT_PROMPT_TEMPLATE
是以后接 LLM 的 system prompt 口子（步骤5 接线），`_SCENE_PLAN` 与其输出的
scenes schema 同构，接 LLM 时只换 `_build_scenes` 的实现、签名不变。
输出契约：{"body": str, "scenes": [{"visual","narration","duration"}], "duration": int}
"""

from typing import Any

# 以后接 LLM 的口子：system prompt（搬自 MoneyPrinterTurbo，改中文化+scenes schema）。
# ponytail: 步骤5 接 LLM 时 .format(subject=..., scene_count=...) 后喂模型，
# 解析返回的 scenes；当前用下方 _SCENE_PLAN 确定性填充同结构。
SCRIPT_PROMPT_TEMPLATE = """\
# Role: 短视频脚本文案生成器
## 约束
1. 只输出脚本文案正文：不要标题、不要 Markdown、不要 "旁白/画外音" 指示词。
2. 直入主题，禁止 "欢迎来到本视频" 式开场。
3. 使用与主题相同的语言；不引用本 prompt。
# 运行上下文
- 主题: {subject}
- 分镜数: {scene_count}
# 输出 schema（每镜 = 画面描述 + 旁白 + 时长秒数）
{{"scenes": [{{"visual": "...", "narration": "...", "duration": 3}}]}}
"""

_DEFAULT_SUBJECT = "爆款内容"

# 五段式分镜骨架：(旁白模板, 画面描述模板, 时长秒)。首镜旁白+画面带 {subject} 槽。
_SCENE_PLAN = [
    ("为什么「{subject}」看起来简单，真正能做好的却屈指可数？", "「{subject}」主题特写 + 悬念字幕", 3),
    ("其实差的不是努力，而是大多数人都忽略了一个反常识的细节。", "对比画面：普通做法 vs 高手做法", 4),
    ("先抓住核心矛盾，再用最小动作验证，最后只保留被验证有效的部分。", "步骤演示特写，关键点放大强调", 6),
    ("而那个最不起眼的细节，恰恰是拉开差距的关键。", "画面反转：被忽视的细节成为焦点", 4),
    ("觉得有用就点个关注，下一条讲透怎么落地。", "结尾定格 + 关注引导", 3),
]


def _subject(style_card: dict[str, Any]) -> str:
    """从风格卡取主题；占位/空值回落默认。"""
    for key in ("topic", "subject", "title", "persona"):
        val = (style_card or {}).get(key)
        if val and "占位" not in str(val):
            return str(val).strip()
    return _DEFAULT_SUBJECT


def _build_scenes(subject: str) -> list[dict[str, Any]]:
    """确定性模板填充：五段式骨架 → 分镜 list。"""
    return [
        {"visual": visual.format(subject=subject), "narration": narration.format(subject=subject), "duration": duration}
        for narration, visual, duration in _SCENE_PLAN
    ]


def run(**kwargs: Any) -> dict[str, Any]:
    subject = _subject(kwargs.get("style_card") or {})
    scenes = _build_scenes(subject)
    body = "\n\n".join(scene["narration"] for scene in scenes)
    return {"body": body, "scenes": scenes, "duration": sum(s["duration"] for s in scenes)}
