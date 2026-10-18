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

from src import llm_mode

# 以后接 LLM 的口子：system prompt（搬自 MoneyPrinterTurbo，改中文化+scenes schema）。
# ponytail: 步骤5 接 LLM 时 .format(subject=..., scene_count=...) 后喂模型，
# 解析返回的 scenes；当前用下方 _SCENE_PLAN 确定性填充同结构。
SCRIPT_PROMPT_TEMPLATE = """\
# Role: 短视频脚本文案生成器
## 约束
1. 只输出脚本文案正文：不要标题、不要 Markdown、不要 "旁白/画外音" 指示词。
2. 直入主题，禁止 "欢迎来到本视频" 式开场。
3. 使用与主题相同的语言；不引用本 prompt。
4. 只基于「可溯源素材」写，禁止编造素材里没有出现的具体数字/品牌/型号/人名/价格；涉及数量或型号时只复述素材原词，不得把约数换算成精确数。
# 可溯源素材
- 账号画像: {profile}
- 热点标题: {trends}
- 文案样本: {samples}
- 转录逐字稿: {transcripts}
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


def _fmt_trends(trends: list[dict[str, Any]]) -> str:
    """热点标题列表 → 顿号串（可溯源素材行）。空回「（无）」。"""
    titles = [
        str(t.get("title", "")).strip()
        for t in trends
        if isinstance(t, dict) and str(t.get("title", "")).strip()
    ]
    return "、".join(titles) if titles else "（无）"


def _fmt_transcripts(transcripts: dict[str, str] | None) -> str:
    """转录逐字稿 dict → 可读串（可溯源素材行）；空回「（无）」。"""
    if not transcripts:
        return "（无）"
    parts = [f"{url}：{str(text).strip()[:200]}" for url, text in transcripts.items()]
    return "\n".join(parts)


def _build_scenes(subject: str) -> list[dict[str, Any]]:
    """确定性模板填充：五段式骨架 → 分镜 list。"""
    return [
        {"visual": visual.format(subject=subject), "narration": narration.format(subject=subject), "duration": duration}
        for narration, visual, duration in _SCENE_PLAN
    ]


def _build_script(subject: str) -> dict[str, Any]:
    """确定性主路径：模板填充五段式分镜 → {body, scenes, duration}。"""
    scenes = _build_scenes(subject)
    body = "\n\n".join(scene["narration"] for scene in scenes)
    return {"body": body, "scenes": scenes, "duration": sum(s["duration"] for s in scenes)}


def _llm_script(
    subject: str,
    trends: list[dict[str, Any]] | None = None,
    samples: str = "",
    profile: str = "",
    transcripts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """LLM 写脚本 body（全开档）。SCRIPT_PROMPT_TEMPLATE 是接 LLM 的口子。"""
    from src import agents, llm

    prompt = SCRIPT_PROMPT_TEMPLATE.format(
        subject=subject,
        scene_count=5,
        profile=profile,
        trends=_fmt_trends(trends or []),
        samples=samples,
        transcripts=_fmt_transcripts(transcripts),
    )
    text = llm.call_llm(prompt, system=agents.system_prompt("script_writer"))
    data = llm.parse_json(text)
    scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("LLM 脚本缺 scenes")
    body = "\n\n".join(str(s.get("narration", "")) for s in scenes if isinstance(s, dict))
    if not body.strip():
        raise ValueError("LLM 脚本 body 空")
    duration = sum(int(s.get("duration", 0) or 0) for s in scenes if isinstance(s, dict))
    return {"body": body, "scenes": scenes, "duration": duration}


def run(**kwargs: Any) -> dict[str, Any]:
    subject = _subject(kwargs.get("style_card") or {})
    trends = kwargs.get("trends") or []
    samples = kwargs.get("samples") or ""
    profile = kwargs.get("profile") or kwargs.get("account_profile") or ""
    transcripts = kwargs.get("transcripts") or {}
    result = _build_script(subject)
    # 三段式第二段：LLM 写 body（全开档；兜底/确定性走模板主路径）。
    return llm_mode.supplement(
        "script_writer",
        has_baseline=True,
        baseline=result,
        fn=lambda: _llm_script(subject, trends=trends, samples=samples, profile=profile, transcripts=transcripts),
    )
