"""Concierge 对话辅助 agent（P4-C4）：只读向导 + 启动判意。

三角色互斥：Orchestrator（LangGraph 确定性调度）/ LLM-judge（质量门评判）/
Concierge（只读 LLM + 唯一动作）。Concierge 不评判、不参与调度。

权限 = 只读 + 一个动作：G1 白名单 = 只读 tool（get_state / list_sources /
cookie_status）+ 唯一动作 start_pipeline(profile)。白名单不含任意 run/write/发帖。

启动判意：明确「启动」→ 直接触发；不确定 → 反问「要启动吗？」→ 用户确认才启动。
这是唯一「动作」，非自由工具调用（pipeline 内部仍由 Orchestrator 确定性调度）。

幻觉压两处：① G1 白名单硬约束（想调 run 直接拒，比 prompt 强）；② 回答锚定
真实 state，不锚定的部分明确说「不知道」。启动误判靠「不确定先确认」兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src import cookies, llm
from src.mcp_guard import MCPGuard
from src.tools import trend_hunter

CONCIERGE_AGENT = "concierge"

# 只读 tool + 唯一动作（白名单，G1 硬约束）。
READ_TOOLS: tuple[str, ...] = ("get_state", "list_sources", "cookie_status")
ACTION_TOOL = "start_pipeline"
CONCIERGE_TOOLS = frozenset((*READ_TOOLS, ACTION_TOOL))

# 六步顺序（答「下一步干嘛」用）。
STAGE_ORDER: tuple[str, ...] = (
    "trend_hunter",
    "topic_planner",
    "style_mimic",
    "script_writer",
    "publish_optimizer",
    "data_analyst",
)
STAGE_LABELS: dict[str, str] = {
    "trend_hunter": "热点捕捉",
    "topic_planner": "选题策划",
    "style_mimic": "风格模仿",
    "script_writer": "脚本文案",
    "publish_optimizer": "发布优化",
    "data_analyst": "数据分析",
}

# ponytail: 判意用关键词启发式（确定性主路径，零 LLM，测试无 key 可跑）。
# 误判靠「不确定先确认」兜底；要更准再上 LLM 判意（补充路径）。
_QUESTION_KWS = (
    "？", "?", "吗", "为什么", "怎么", "如何", "卡", "解释", "指引", "是什么",
    "什么意思", "哪", "谁", "登录", "cookie", "数据源", "下一步", "状态",
    "失败", "报错", "没跑", "多少", "多久", "干嘛", "该做", "你好", "嗨", "hello", "hi", "在吗",
    "什么", "产物", "结果", "进度", "看看", "看一下", "现在", "到哪",
)
_START_KWS = (
    "启动", "开始", "跑", "做一条", "写一条", "生成", "来一条", "来一篇",
    "帮我做", "帮我写", "帮我生成", "帮我搞", "给我做", "给我写",
)
_AMBIGUOUS_KWS = ("帮我", "给我", "来一个", "来点", "弄", "搞")

_PROFILE_PREFIX = (
    "帮我做", "帮我写", "帮我生成", "帮我搞", "给我做", "给我写",
    "做一条", "写一条", "来一条", "来一篇", "生成", "帮我", "给我",
)

# 答疑主题路由：登录/数据源 vs 产物 vs 卡哪（按此顺序，先登录后产物）。
_LOGIN_KWS = ("登录", "cookie", "数据源", "授权", "扫码", "接入", "没数据")
_PRODUCT_KWS = ("产物", "脚本", "选题", "热点", "趋势", "风格", "文案", "分析", "结果", "写了", "内容", "做了")

# 六步产物键 → 中文标签（解释产物用）。
_PRODUCT_FIELDS = (
    ("trends", "热点"),
    ("topics", "选题"),
    ("style_card", "风格卡"),
    ("script", "脚本"),
    ("publish_plan", "发布计划"),
    ("analytics", "分析报告"),
)

CONCIERGE_SYSTEM = "你是「表达基因 Voice DNA」的接待向导。只基于给定事实回答，禁止编造；事实里写「不知道」就照答不知道。"


@dataclass
class ConciergeReply:
    """Concierge 回复：answer（答疑）/ ask_start（反问确认）/ start_pipeline（唯一动作）。"""

    kind: str
    text: str
    profile: str = ""


def concierge_whitelist() -> dict[str, set[str]]:
    """G1 窄白名单：只读 tool + 唯一动作，不含 run/write/发帖。"""
    return {CONCIERGE_AGENT: set(CONCIERGE_TOOLS)}


def make_guard(**kwargs: Any) -> MCPGuard:
    """同一个 G1–G5 网关，白名单更窄（只读 + 单动作）。"""
    return MCPGuard(whitelist=concierge_whitelist(), **kwargs)


def classify_intent(text: str) -> str:
    """自由格式判意：'start'（明确启动）/ 'ask'（不确定，反问）/ 'answer'（答疑）。"""
    t = (text or "").strip()
    if not t:
        return "answer"
    if any(k in t for k in _QUESTION_KWS):
        return "answer"
    if any(k in t for k in _START_KWS):
        return "start"
    if any(k in t for k in _AMBIGUOUS_KWS):
        return "ask"
    return "start"  # 裸画像（如「美妆博主」）= 明确启动该画像


def extract_profile(text: str) -> str:
    """从启动句抽画像，抽不到返回空串（start_pipeline 兜默认画像）。"""
    t = (text or "").strip()
    if t in ("启动", "开始", "跑", "跑起来", "全跑", "开始跑"):
        return ""
    for kw in _PROFILE_PREFIX:
        if t.startswith(kw):
            t = t[len(kw):].strip()
            break
    for kw in ("一条", "一篇", "一个", "条", "篇", "个"):
        if t.startswith(kw):
            t = t[len(kw):].strip()
            break
    return t


def start_pipeline(profile: str = "") -> ConciergeReply:
    """唯一动作：触发 pipeline。pipeline 内部仍由 Orchestrator 确定性调度。"""
    profile = (profile or "").strip() or "美妆博主"
    return ConciergeReply(kind="start_pipeline", text=f"为「{profile}」启动六步流水线", profile=profile)


def _next_stage(stage: str) -> str | None:
    try:
        i = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    return STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None


def _ground_login() -> str:
    """登录与数据源接入指引：锚定真实数据源清单 + cookie 状态，不编造。"""
    try:
        lines = []
        for s in trend_hunter.list_sources():
            status = cookies.cookie_status(s["name"])
            if status == "ok":
                lines.append(f"{s['name']}：已登录")
            else:
                lines.append(f"{s['name']}：未登录（登录页 {s.get('login_url', '')}）")
        head = "\n".join(lines) if lines else "暂无已配置的数据源。"
        return f"数据源接入：\n{head}\n未登录的平台去设置面板贴 cookie 或扫码登录。"
    except Exception:  # noqa: BLE001 — 数据源/ cookie 读取失败回静态指引，不阻断答疑
        return "数据源接入见设置面板：贴 cookie 或扫码登录。"


def _describe(value: Any, limit: int = 3) -> str:
    """产物摘要：列表给条数+样例，字典给字段名，截断不编造。"""
    if isinstance(value, list):
        if not value:
            return "空"
        head = value[:limit]
        more = f"…共 {len(value)} 条" if len(value) > limit else f"{len(value)} 条"
        return f"{head}{more}"
    if isinstance(value, dict):
        if not value:
            return "空"
        keys = list(value)[:limit]
        more = "…" if len(value) > limit else ""
        return f"字段：{keys}{more}"
    return str(value)[:200]


def _ground_products(state: dict[str, Any]) -> str:
    """解释产物：锚定 state 里真实存在的产物，没有的明说「还没有」。"""
    found = []
    for field, label in _PRODUCT_FIELDS:
        if state.get(field):
            found.append(f"{label}：{_describe(state[field])}")
    if not found:
        return "还没有任何产物。先「启动」跑一遍流水线，或「继续」往后跑。"
    return "已生成的产物：\n" + "\n".join(found)


def _ground_answer(text: str, state: dict[str, Any]) -> str:
    """确定性主路径：按主题路由（登录/产物/卡哪），锚定真实 state。"""
    t = text or ""
    if any(k in t for k in _LOGIN_KWS):
        return _ground_login()
    if any(k in t for k in _PRODUCT_KWS):
        return _ground_products(state)
    state = state or {}
    stage = state.get("current_stage")
    if not stage:
        return (
            "不知道（当前没有流水线状态）。你可以：① 输入画像（如「美妆博主」）或「启动」开跑；"
            "② 跑起来后再问「卡在哪 / 下一步干嘛」。"
        )
    if stage == "human_gate":
        errs = state.get("errors") or []
        return f"卡在人工兜底（human_gate）；错误：{errs or '未知'}。下一步：人工介入检查产物。"
    if state.get("stage_status") == "failed":
        errs = state.get("errors") or []
        return f"卡在「{STAGE_LABELS.get(stage, stage)}」；错误：{errs}。下一步：修正后重跑该步。"
    nxt = _next_stage(stage)
    if nxt:
        return f"当前在「{STAGE_LABELS.get(stage, stage)}」，下一步是「{STAGE_LABELS.get(nxt, nxt)}」。"
    return f"六步已完成（当前「{STAGE_LABELS.get(stage, stage)}」），无下一步。"


def answer(text: str, *, state: dict[str, Any] | None = None) -> str:
    """答疑：ground 主路径 + LLM 润色（无 key 直接回 ground，不编造）。"""
    ground = _ground_answer(text, state or {})
    if not llm.has_key():
        return ground
    try:
        return llm.call_llm(
            f"用户问题：{text}\n\n可回答的事实：\n{ground}\n\n请基于事实回答，不要编造。",
            system=CONCIERGE_SYSTEM,
        ).strip()
    except Exception:  # noqa: BLE001 — LLM 不可用回 ground 主路径，不阻断答疑
        return ground


def handle(
    text: str,
    *,
    state: dict[str, Any] | None = None,
) -> ConciergeReply:
    """Concierge 统一入口：判意 → 触发 / 反问 / 答疑。"""
    intent = classify_intent(text)
    if intent == "start":
        return start_pipeline(extract_profile(text))
    if intent == "ask":
        return ConciergeReply(
            kind="ask_start",
            text="要启动流水线吗？输入画像（如「美妆博主」）或「启动」，我就开跑。",
        )
    return ConciergeReply(kind="answer", text=answer(text, state=state))
