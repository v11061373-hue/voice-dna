# HANDOFF-P5-G — 全仓 lint/mypy 清理（收尾，E3/E4 达标）

状态：✅ 完成 · 2026-10-19

## 交付内容

`ruff check src tests` 0 告警、`mypy src web_server.py app.py` 0 告警、全量 `python -m pytest -q` **216 passed**。

基线（本阶段实测，非 P5-B 旧数）：ruff **25** 告警、mypy **16** 告警（app.py 3 + web_server.py 13）。

### ruff 25 → 0

- **自动修（ruff --fix）3 条**：I001×2（cookies.py 懒加载 playwright / test_mcp_servers.py）、UP037×1（session_store.py 引号注解）。
- **刻意降级加 `# noqa` 带注释（不删功能）16 条**：
  - BLE001×10（llm_mode 1 + mcp_client 2 + trend_hunter 7）：全部是「外部源/LLM/插件不可用优雅降级」语义，加 `# noqa: BLE001` + 中文注释。
  - S110×4（cookies 1 + mcp_client 1 + trend_hunter 2）、S112×1（mcp_client）：`try-except-pass/continue` 均带明确降级意图，加 noqa。
- **小幅重构 5 条**：
  - PLW0602（mcp_client `global _servers` 无赋值）→ 删掉 `_servers`，只留 `global _servers_loaded`（`_servers` 只做 item 赋值，无需 global）。
  - PYI034（session_store `__enter__`）→ 返回类型 `-> Self`（`typing.Self`，Python 3.12 可用；类从不被子类化，`Self` 与 `SessionStore` 等价）。
  - PLC0206（conftest）→ 恢复环境改 `for k, value in saved.items()`。
  - TRY002（test_plugins）→ `raise Exception("down")` 改 `raise RuntimeError("down")`（同被 `except Exception` 捕获，测试行为不变）。
  - SIM117×3（test_session_store）→ 嵌套 `with` 合并单条 `with … as d, SessionStore(…) as s:`。

### mypy 17 → 0（16 基线 + 1 自 fix 回归）

- **cookies.py playwright `import-not-found`（回归，非基线）**：`ruff --fix` 的 I001 把单行 import 拆成括号多行，`# type: ignore[import-not-found]` 落到 symbol 行，模块级告警失去抑制。把 ignore 注释移回 `from` 行。
- **app.py 3 条**：
  - `run_quality_gates(node, state)`：`state` 是 `dict[str, Any]`，`SocialMediaState` 是 TypedDict，加 `cast(SocialMediaState, state)`。
  - `res.name` / `res.payload` → `res["name"]` / `res["payload"]`：**latent 运行时 bug 修复**（见下「关键偏离」）。
- **web_server.py 13 条**：
  - `_graph_app` 补精确类型 `CompiledStateGraph[SocialMediaState, None, SocialMediaState, SocialMediaState] | None` + 3 处 `assert _graph_app is not None`（`_one_step` / `get_state` / `concierge_turn`，lifespan 保证先赋值）。
  - `_cfg` 返回类型 `dict[str, Any]` → `RunnableConfig`（修 ainvoke/aget_state 的 config 实参类型）。
  - `_gates` 里 `run_quality_gates` 加 `cast(SocialMediaState, state)`。
  - `store.upsert(..., last_stage=state.get("current_stage"))` → `... or ""`（修 `Any | None` vs `str`；pipeline 内 current_stage 恒为 str，`or ""` 是 no-op 守卫）。

## 关键偏离（mypy 暴露的 latent 运行时 bug）

`app.py:_ask_transcribe` 用 `res.name` / `res.payload` 读 chainlit `AskActionResponse`。该类型是 TypedDict（运行时 = dict），chainlit 自身源码用 `res['label']` 下标访问。`res.name` 若执行到会 `AttributeError`。本阶段按 mypy 要求改下标，同时修正了 latent bug。此路径（chainlit UI 且 candidate_videos 非空）无单测覆盖，故 216 绿从未触发。**改下标是正确且必要的行为修正**，非纯类型注解。

## 测试证据

- `ruff check src tests`：**All checks passed!**
- `mypy src web_server.py app.py`：**Success: no issues found in 29 source files**
- `python -m pytest -q`：**216 passed in 1.75s**

## 未完成项 / 环境注意

1. **裸 `pytest` 命令会 ModuleNotFoundError（`No module named 'src'`）**：仓库无 root `conftest.py` / `pytest.ini` / `pyproject.toml`，pytest 9 控制台脚本不把 cwd 加进 sys.path。正确姿势 `python -m pytest`（`python -m` 注入 cwd）。历史 handoff 写「pytest -q 216」实为 `python -m pytest -q` 或带 PYTHONPATH。未加 pytest 配置（超本阶段 surgical 范围），如要裸 `pytest` 可用需补 root `conftest.py` 或 `pytest.ini`。
2. **P5-F 云端 ASR 接线**仍可选（未做），等本阶段收尾后决定。

## 下阶段入口

- P5-G 完成即 P5 工程验收（E1–E7）全绿。剩功能验收 F1 真数据全图 E2E 卡 bilibili 412（外部源故障，非代码 bug），源恢复后复现。
- 可选 P5-F：`transcribe._asr_cloud` stub 接 DashScope callback 流式。

## unverified_assumptions

1. **`or ""` 守卫的 None 分支从未真实发生**：pipeline 各节点恒回字符串 `current_stage`，`state.get("current_stage")` 的 `None` 只在理论上存在（`_one_step` 之前状态无此键）。未构造「current_stage 缺失」路径实测，属防御性 no-op。
2. **`res["name"]`/`res["payload"]` 下标语义**：依据 chainlit 2.12.0 源码 `send()` 内 `res['label']` 下标访问判定 `AskActionResponse` 运行时是 dict；未在真实 chainlit UI 里点候选视频转录走通此分支（需 bilibili 源 + 真实视频 + 交互）。
3. **`CompiledStateGraph[...]` 泛型参数**：与已装 langgraph 1.2.11 的 `_graph.compile(checkpointer=…)` 返回类型对齐（mypy 错误信息原文），未做版本升级兼容性预留。
