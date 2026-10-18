"""Chainlit 前端 — 表达基因（Voice DNA）社媒 Agent 六步流水线。

trend_hunter → topic_planner → style_mimic → script_writer → [脚本质量门]
→ publish_optimizer → data_analyst → [分析质量门] → END；门 HALT / 失败 → human_gate。

每步经 graph.astream 流式渲染成一张 cl.Step 卡，产物按类型格式化（非 JSON 裸 dump）；
两个质量门就地显示 PASS/WARN/HALT。收尾给摘要 + 可展开原始 JSON 供核对。

架构对应 src/orchestrator/graph.py 的 7 节点 + 2 条件边。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, cast

import chainlit as cl

from src.orchestrator.graph import app, v2_app
from src.orchestrator.quality_gate import GateResult, run_quality_gates
from src.schemas import SocialMediaState
from src.tools import transcribe, video_download, video_vision
from src.tools.video_download import is_video_url

# ——— 六步产物 → 可读 Markdown ———


def _fmt_trends(trends: Any) -> str:
    items = trends if isinstance(trends, list) else []
    if not items:
        return "（未抓到热点：平台源不可达或登录态未接）"
    lines = []
    for t in items[:10]:
        heat = t.get("heat", 0)
        platform = t.get("platform", "")
        category = t.get("category", "")
        lines.append(
            f"- **{t.get('title', '')}** · `{platform}` · 热度 {heat:,.0f}"
            + (f" · {category}" if category else "")
        )
    if len(items) > 10:
        lines.append(f"… 共 {len(items)} 条")
    return "\n".join(lines)


def _fmt_topics(topics: Any) -> str:
    items = topics if isinstance(topics, list) else []
    if not items:
        return "（无选题：上游无热点输入）"
    return "\n".join(
        f"{i}. **{t.get('title', '')}** — 评分 `{t.get('score', 0)}` · {t.get('reason', '')}"
        for i, t in enumerate(items[:8], 1)
    )


_STYLE_LABELS = (
    ("persona", "人设"),
    ("voice", "腔调"),
    ("catchphrases", "口癖"),
    ("sentence_patterns", "句式"),
    ("pacing", "节奏"),
    ("narrative_structure", "叙事结构"),
    ("visual_style", "视觉风格"),
)


def _fmt_style_card(card: Any) -> str:
    card = card if isinstance(card, dict) else {}
    lines = []
    for key, label in _STYLE_LABELS:
        v = card.get(key, "未知")
        if isinstance(v, list):
            v = "、".join(v) if v else "（无）"
        lines.append(f"- **{label}**：{v}")
    return "\n".join(lines)


def _fmt_script(script: Any) -> str:
    script = script if isinstance(script, dict) else {}
    scenes = script.get("scenes") or []
    body = script.get("body", "")
    lines = [f"**正文**（{script.get('duration', 0)}s · {len(scenes)} 镜）：\n\n{body}"]
    if scenes:
        lines.append("\n**分镜**：")
        lines += [
            f"{i}. `{s.get('duration', 0)}s` {s.get('visual', '')} — {s.get('narration', '')}"
            for i, s in enumerate(scenes, 1)
        ]
    return "\n".join(lines)


def _fmt_publish(plan: Any) -> str:
    plan = plan if isinstance(plan, dict) else {}
    tags = plan.get("tags") or []
    hashtags = plan.get("hashtags") or []
    return "\n".join(
        [
            f"- **平台**：{plan.get('platform', '')}",
            f"- **最佳时间**：{plan.get('best_time', '')}",
            f"- **标签**：{'、'.join(tags) if tags else '（无）'}",
            f"- **话题**：{'、'.join(hashtags) if hashtags else '（无）'}",
        ]
    )


def _fmt_analytics(analytics: Any) -> str:
    a = analytics if isinstance(analytics, dict) else {}
    m = a.get("metrics") or {}
    b = a.get("benchmark") or {}
    anomalies = a.get("anomalies") or []
    lines = [
        f"**报告**：{a.get('report', '')}",
        f"- 总播放 {m.get('total_views', 0):,} · 均播 {m.get('avg_views', 0)}"
        f" · 互动率 {m.get('engagement_rate', 0)}%",
        f"- 最新第 {b.get('quartile', 0)} 四分位 · 层级 `{b.get('view_bucket', '')}`"
        f" · 同行中位 {b.get('peer_median', 0)}",
    ]
    if anomalies:
        lines.append(f"- ⚠️ IQR 1.5 检出 {len(anomalies)} 处异常：{anomalies}")
    return "\n".join(lines)


# ——— 节点名 → (卡片标题, 产物字段, 格式化器) ———
_STAGES: tuple[tuple[str, str, str, Callable[[Any], str]], ...] = (
    ("trend_hunter", "🔥 热点捕捉", "trends", _fmt_trends),
    ("topic_planner", "🎯 选题策划", "topics", _fmt_topics),
    ("style_mimic", "🎭 风格模仿", "style_card", _fmt_style_card),
    ("script_writer", "✍️ 脚本文案", "script", _fmt_script),
    ("publish_optimizer", "📅 发布优化", "publish_plan", _fmt_publish),
    ("data_analyst", "📊 数据分析", "analytics", _fmt_analytics),
)

_STAGE_BY_NODE = {node: (title, field, fmt) for node, title, field, fmt in _STAGES}

_GATE_ICON = {GateResult.PASS: "✅", GateResult.WARN: "⚠️", GateResult.HALT: "🛑"}

_PROFILES = ["美妆博主", "数码测评", "职场成长", "美食探店"]


async def _stream_and_render(graph_app: Any, state: dict[str, Any]) -> None:
    """流式跑图，每节点渲染成 cl.Step 卡，产物并入 state（就地更新）。"""
    async for chunk in graph_app.astream(state, stream_mode="updates"):
        for node, update in chunk.items():
            state.update(update)
            if node == "human_gate":
                await cl.Message(
                    content="🛑 **质量门 HALT / 节点失败**，进入人工兜底（human_gate）。"
                ).send()
                continue
            meta = _STAGE_BY_NODE.get(node)
            if meta is None:
                continue
            title, field, fmt = meta
            data = update.get(field)
            output = fmt(data) if data is not None else "（该步未产出数据）"
            if node in ("script_writer", "data_analyst"):
                gate = run_quality_gates(node, cast(SocialMediaState, state))
                output += f"\n\n**质量门**：{_GATE_ICON[gate]} {gate.value}"
            async with cl.Step(name=title, type="tool") as step:
                step.output = output


async def _send_json(state: dict[str, Any], label: str, name: str) -> None:
    await cl.Message(
        content=label,
        elements=[
            cl.Text(
                name=name,
                content=json.dumps(state, ensure_ascii=False, indent=2),
                display="inline",
            )
        ],
    ).send()


async def _ingest_video(url: str) -> tuple[str, dict[str, Any]]:
    """下载 + 转录 + 视觉（成本门默认关，VOICEDNA_VISION≠1 回空）→ (text, video_visual)。"""
    path = str((video_download.run(url=url) or {}).get("path", ""))
    r = await asyncio.to_thread(transcribe.run, source=path)
    text = str((r or {}).get("text", ""))
    vis = await asyncio.to_thread(video_vision.run, path=path)
    return text, vis


async def _ask_transcribe(state: dict[str, Any]) -> None:
    """END 后：候选视频非空则问「转录哪个」，转录完带素材二次跑 v2。"""
    cands = state.get("candidate_videos") or []
    if not cands:
        return

    actions = [
        cl.Action(name="skip", payload={}, label="跳过（保留 v1）"),
        cl.Action(name="all", payload={}, label=f"全部转录（{len(cands)} 条）"),
    ]
    actions += [
        cl.Action(name="one", payload={"url": c["url"], "title": c["title"]}, label=f"转录：{c['title'][:24]}")
        for c in cands
    ]
    res = await cl.AskActionMessage(
        content="🔥 发现候选视频，要转录哪个？（转录逐字稿后二次跑，脚本更贴真实口播）",
        actions=actions,
        timeout=600,
    ).send()
    if res is None or res["name"] == "skip":
        return

    selected = cands if res["name"] == "all" else [
        c for c in cands if c["url"] == (res["payload"] or {}).get("url")
    ]
    transcripts: dict[str, str] = {}
    for c in selected:
        await cl.Message(content=f"🎙️ 转录中：{c['title']}").send()
        try:
            text, vis = await _ingest_video(c["url"])
            transcripts[c["url"]] = text
            if vis:
                state["video_visual"] = vis
                await cl.Message(
                    content=(
                        f"🎞️ **分镜卡**：节奏「{vis.get('shot_rhythm', '')}」"
                        f" · 风格「{vis.get('visual_style', '')}」"
                    )
                ).send()
        except Exception as exc:  # noqa: BLE001 — 单条失败不阻断其余
            await cl.Message(content=f"⚠️ 转录失败 {c['title']}：{exc}").send()

    if not transcripts:
        await cl.Message(content="无成功转录，跳过 v2 回流。").send()
        return

    state["transcripts"] = transcripts
    state["v1_script"] = state.get("script")
    await cl.Message(content="♻️ 带转录素材二次跑（style→script→publish→analyst）").send()
    await _stream_and_render(v2_app, state)
    await cl.Message(content=_summary(state)).send()
    await _send_json(state, "原始产物 JSON（v2，核对用）：", "result-v2.json")


async def _run_link_mode(url: str) -> None:
    """甩链接模式：下载 + 转录 + 视觉，再带转录素材二次跑 v2 生成脚本。"""
    await cl.Message(content=f"🎬 甩链接模式：{url}").send()
    try:
        text, vis = await _ingest_video(url)
    except Exception as exc:  # noqa: BLE001 — 下载/转录失败给明确提示
        await cl.Message(content=f"⚠️ 转录失败：{exc}").send()
        return
    if not text:
        await cl.Message(content="⚠️ 转录为空（视频可能无口播，或源需登录态）。").send()
        return

    state: dict[str, Any] = {
        "account_profile": "热点",
        "transcripts": {url: text},
    }
    if vis:
        state["video_visual"] = vis
        await cl.Message(
            content=f"🎞️ **分镜卡**：节奏「{vis.get('shot_rhythm', '')}」 · 风格「{vis.get('visual_style', '')}」"
        ).send()
    await cl.Message(content=f"🎙️ **转录逐字稿**（{len(text)} 字）：\n\n{text}").send()
    await cl.Message(content="♻️ 带转录素材生成脚本（style→script→publish→analyst）").send()
    await _stream_and_render(v2_app, state)
    await cl.Message(content=_summary(state)).send()
    await _send_json(state, "原始产物 JSON（甩链接，核对用）：", "result-link.json")


async def _run_pipeline(profile: str) -> None:
    await cl.Message(content=f"为 **{profile}** 启动六步流水线").send()

    state: dict[str, Any] = {"account_profile": profile}
    await _stream_and_render(app, state)
    await cl.Message(content=_summary(state)).send()
    await _send_json(state, "原始产物 JSON（核对用）：", "result.json")

    await _ask_transcribe(state)


def _summary(state: dict[str, Any]) -> str:
    topics = state.get("topics") or []
    script = state.get("script") or {}
    analytics = state.get("analytics") or {}
    lines = [
        "### ✅ 六步完成",
        f"- **最优选题**：{topics[0].get('title', '') if topics else '（无选题）'}",
        f"- **脚本**：{script.get('duration', 0)}s · {len(script.get('scenes') or [])} 镜",
        f"- **分析**：{analytics.get('report', '')}",
    ]
    if state.get("stage_status") != "ok":
        lines.append(f"- ⚠️ 状态：{state.get('stage_status')} · {state.get('errors', [])}")
    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.Message(
        content=(
            "**表达基因（Voice DNA）** 就绪。\n\n"
            "输入账号画像（如「美妆博主」），或点下方示例，启动六步流水线：\n"
            "🔥 热点捕捉 → 🎯 选题策划 → 🎭 风格模仿 → ✍️ 脚本文案"
            " → 📅 发布优化 → 📊 数据分析"
        ),
        actions=[cl.Action(name="pick_profile", payload={"profile": p}, label=p) for p in _PROFILES],
    ).send()


@cl.action_callback("pick_profile")
async def on_pick_profile(action: cl.Action) -> None:
    await _run_pipeline(str(action.payload.get("profile", "美妆博主")))


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = message.content.strip()
    url = is_video_url(text)
    if url:
        await _run_link_mode(url)
        return
    await _run_pipeline(text or "美妆博主")
