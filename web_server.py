"""Voice DNA 网页前端 — FastAPI 后端。对话式 + 逐步运行。

逐步执行：用 LangGraph interrupt_after 在每个 agent 节点后暂停，前端点「下一步」
调 /api/run {action:next} 继续。原图 _graph 不动，这里二次 compile 挂 checkpointer
+ interrupt_after（测试与 chainlit 用的 graph.app 保持原样）。

action:
  start  — 新会话，跑 trend_hunter 后暂停
  next   — 跑下一个节点后暂停
  auto   — 循环跑到 END（含 human_gate）
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, cast

import aiosqlite
from fastapi import FastAPI
from fastapi.responses import FileResponse
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from src import concierge, config, cookies
from src.mcp_client import call_tool, list_tools
from src.mcp_guard import GuardDenied
from src.orchestrator.graph import _graph, v2_app
from src.orchestrator.quality_gate import run_quality_gates
from src.schemas import SocialMediaState
from src.session_store import SessionStore
from src.tools import trend_hunter

INTERRUPT_AFTER = [
    "trend_hunter",
    "topic_planner",
    "style_mimic",
    "script_writer",
    "publish_optimizer",
    "data_analyst",
]
GATE_STAGES = ("script_writer", "data_analyst")

DB_PATH = "checkpoints.db"

store = SessionStore("sessions.db")

_graph_app: CompiledStateGraph[SocialMediaState, None, SocialMediaState, SocialMediaState] | None = None  # 编译后的图，lifespan 里挂 SqliteSaver 后赋值


@asynccontextmanager
async def _lifespan(_: FastAPI):
    global _graph_app
    conn = await aiosqlite.connect(DB_PATH)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    _graph_app = _graph.compile(checkpointer=saver, interrupt_after=INTERRUPT_AFTER)
    yield
    await conn.close()


server = FastAPI(title="Voice DNA", lifespan=_lifespan)


class RunRequest(BaseModel):
    action: str  # "start" | "next" | "auto"
    profile: str = "美妆博主"
    samples: str = ""  # md 附件文本，前置喂 style_mimic
    thread_id: str = ""
    enabled: list[str] = []  # 前端 chip 选中的数据源（trend_hunter 只跑这些）


class ToolRequest(BaseModel):
    tool: str
    kwargs: dict[str, Any] = {}


class ConciergeRequest(BaseModel):
    text: str
    thread_id: str = ""


class ConfigRequest(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    key: str = ""
    judge_provider: str = ""
    judge_base_url: str = ""
    judge_key: str = ""


class V2Request(BaseModel):
    thread_id: str
    transcripts: dict[str, str] = {}


def _cfg(tid: str) -> RunnableConfig:
    return {"configurable": {"thread_id": tid}}


async def _one_step(tid: str, payload: Any) -> tuple[dict[str, Any], bool]:
    """resume 一步；返回 (state, done)。done = 无下一节点（已到 END）。"""
    assert _graph_app is not None
    state = await _graph_app.ainvoke(payload, config=_cfg(tid))
    snap = await _graph_app.aget_state(_cfg(tid))
    return state, not snap.next


def _gates(state: dict[str, Any]) -> dict[str, str]:
    s = cast(SocialMediaState, state)
    return {
        "script_writer": run_quality_gates("script_writer", s).value,
        "data_analyst": run_quality_gates("data_analyst", s).value,
    }


def _response(tid: str, state: dict[str, Any], done: bool) -> dict[str, Any]:
    return {
        "thread_id": tid,
        "stage": state.get("current_stage"),
        "state": state,
        "gates": _gates(state),
        "halted": state.get("current_stage") == "human_gate",
        "done": done,
    }


@server.post("/api/run")
async def run(req: RunRequest) -> dict[str, Any]:
    if req.action == "start":
        tid = uuid.uuid4().hex
        state, done = await _one_step(
            tid,
            {"account_profile": req.profile, "samples": req.samples, "enabled_sources": req.enabled},
        )
        store.upsert(tid, profile=req.profile, last_stage=state.get("current_stage") or "")
    else:
        tid = req.thread_id
        state, done = await _one_step(tid, None)
        if req.action == "auto":
            while not done:
                state, done = await _one_step(tid, None)
        store.upsert(tid, last_stage=state.get("current_stage") or "")
    return _response(tid, state, done)


@server.post("/api/v2")
async def v2_reflow(req: V2Request) -> dict[str, Any]:
    """v2 回流：v1 state + 转录素材二次跑 v2_app（style→script→publish→analyst）。"""
    assert _graph_app is not None
    snap = await _graph_app.aget_state(_cfg(req.thread_id))
    state: dict[str, Any] = dict(snap.values or {})
    if not state.get("trends"):
        return {"error": "v1 未跑完（无 trends），先 /api/run action=auto 到 END"}
    state["transcripts"] = req.transcripts
    state["v1_script"] = state.get("script")
    v2 = await v2_app.ainvoke(cast(SocialMediaState, state))
    return _response(req.thread_id, v2, done=True)


@server.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return store.list()


@server.delete("/api/sessions/{sid}")
async def delete_session(sid: str) -> dict[str, Any]:
    store.delete(sid)
    return {"ok": True}


@server.get("/api/state/{tid}")
async def get_state(tid: str) -> dict[str, Any]:
    assert _graph_app is not None
    snap = await _graph_app.aget_state(_cfg(tid))
    values = snap.values or {}
    return {
        "thread_id": tid,
        "stage": values.get("current_stage"),
        "state": values,
        "gates": _gates(values),
        "halted": values.get("current_stage") == "human_gate",
        "done": not snap.next,
    }


@server.get("/api/tools")
async def tools() -> list[dict[str, Any]]:
    return await list_tools()


@server.get("/api/config")
async def get_config() -> dict[str, Any]:
    """个人账号配置读（D1）：key 只回「已配/未配」。"""
    return config.get_config()


@server.post("/api/config")
async def set_config(req: ConfigRequest) -> dict[str, Any]:
    """个人账号配置写（D1/D4）：key 只落 os.environ。"""
    config.set_config(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        key=req.key,
        judge_provider=req.judge_provider,
        judge_base_url=req.judge_base_url,
        judge_key=req.judge_key,
    )
    return config.get_config()


class CookieRequest(BaseModel):
    platform: str
    cookie: str = ""


@server.get("/api/sources")
async def sources() -> list[dict[str, Any]]:
    """数据源能力清单（A1）：前端据此渲染 chip 栏。"""
    return trend_hunter.list_sources()


@server.get("/api/cookie")
async def cookie_status(platform: str = "") -> dict[str, Any]:
    """cookie 状态检测（A4 统一入口）：单平台 or 全部。"""
    if platform:
        return {"platform": platform, "status": cookies.cookie_status(platform)}
    statuses = {s["name"]: cookies.cookie_status(s["name"]) for s in trend_hunter.list_sources()}
    return {"statuses": statuses}


@server.post("/api/cookie")
async def save_cookie(req: CookieRequest) -> dict[str, Any]:
    """V1 手动贴 cookie：只落 ~/.voice-dna/cookies.json。"""
    cookies.save_cookie(req.platform, req.cookie)
    return {"platform": req.platform, "status": "ok"}


@server.post("/api/cookie/scan")
async def scan_cookie(req: CookieRequest) -> dict[str, Any]:
    """V2 自动扫码：playwright 懒加载；未装 Chrome 返回明确反馈。"""
    login_url = ""
    for s in trend_hunter.list_sources():
        if s["name"] == req.platform:
            login_url = s.get("login_url", "")
            break
    return cookies.auto_scan(req.platform, login_url=login_url)


_concierge_guard = concierge.make_guard()


@server.post("/api/concierge")
async def concierge_turn(req: ConciergeRequest) -> dict[str, Any]:
    """Concierge 常驻主对话栏：判意 → 答疑 / 反问 / 触发 start_pipeline。"""
    state: dict[str, Any] = {}
    if req.thread_id:
        # get_state 只读 tool 过 G1 白名单；不白名单的不放行。
        d = _concierge_guard.check(agent_id="concierge", tool_name="get_state", action="read")
        if d.allowed:
            assert _graph_app is not None
            snap = await _graph_app.aget_state(_cfg(req.thread_id))
            state = snap.values or {}
    reply = concierge.handle(req.text, state=state)
    return {"kind": reply.kind, "text": reply.text, "profile": reply.profile}


@server.post("/api/tool")
async def run_tool(req: ToolRequest) -> dict[str, Any]:
    try:
        result = await call_tool(req.tool, **req.kwargs)
    except GuardDenied as exc:
        return {"allowed": False, "gate": exc.gate, "reason": exc.reason}
    return {"tool": req.tool, "result": result}


@server.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html", headers={"Cache-Control": "no-store"})
