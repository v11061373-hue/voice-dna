# HANDOFF-P4-C4 — Concierge 对话辅助 agent（只读向导 + 启动判意）

状态：完成 ✅ · 2026-10-19

## 完成度

- **`src/concierge.py`**：Concierge 模块，三角色互斥定位落地
  - `CONCIERGE_AGENT = "concierge"`，白名单 = 只读 tool（`get_state` / `list_sources` / `cookie_status`）+ 唯一动作 `start_pipeline`
  - `concierge_whitelist()` / `make_guard()`：复用同一个 `MCPGuard`（G1–G5），白名单更窄（只读 + 单动作），不含任意 run/write/发帖
  - `classify_intent()`：自由格式判意三态 `start`（明确启动）/ `ask`（不确定反问）/ `answer`（答疑）
  - `extract_profile()`：从启动句抽画像（前缀剥离启发式，抽不到兜默认「美妆博主」）
  - `start_pipeline(profile)`：唯一动作，返回 `ConciergeReply(kind="start_pipeline")`，pipeline 内部仍由 Orchestrator 确定性调度
  - `_ground_answer(text, state)`：答疑按主题路由（登录/数据源 → `_ground_login`，产物 → `_ground_products`，其余 → 卡哪/下一步/human_gate/failed），全锚定真实 state；state 空明确答「不知道」
  - `_ground_login()`：登录与数据源接入指引，锚定真实 `trend_hunter.list_sources()` + `cookies.cookie_status()`（已登录/未登录 + login_url），不编造
  - `_ground_products()`：解释产物，锚定 state 六产物键（trends/topics/style_card/script/publish_plan/analytics）真实内容，无产物明说「还没有」
  - `answer()`：ground 主路径 + LLM 润色（`llm.has_key()` 才润色，无 key 直接回 ground；LLM 只喂 ground 事实，禁止编造）
  - `handle()`：统一入口，判意 → 触发 / 反问 / 答疑
- **后端 `POST /api/concierge`**（web_server.py）：`{text, thread_id}` → 读 state（`get_state` 过 G1 白名单）→ `concierge.handle` → `{kind, text, profile}`
- **前端**（static/index.html）：`send()` 默认路由 free-form 输入到 `/api/concierge`；`start_pipeline` 回复走 `doStart(profile)`（保留 cookie 检查 + 卡片渲染），`ask_start`/`answer` 回复走 `addAgent` 纯文本。保留「继续/下一步/全跑/重来」快捷键

## 铁律核验

- key 只 `os.environ`：本阶段未动 key 路径，Concierge 用 `llm.has_key()` / `llm.call_llm`（读 os.environ），不落盘不落库
- cookie 只落 `~/.voice-dna/cookies.json`（未动 `src/cookies.py`）
- 检索型源走 stdio npx（未动）
- LLM 兜底可溯源：`answer` 的 LLM 润色只喂 ground 事实（锚定 state），prompt 明令「禁止编造」；state 空时 ground =「不知道」，LLM 照答
- handoff 含 `unverified_assumptions`

## 测试证据

- `pytest`：**159 passed**（C 基线 151，+8）
  - 新文件 `tests/test_concierge.py`（8 例）：只读 tool 放行 / run·write·发帖 G1 拒绝 / 明确启动触发 start_pipeline / 模糊输入反问不触发 / 回答锚定 state（空 state 答「不知道」）/ 登录问题锚定数据源指引 / 产物问题锚定真实产物 / 无产物明说「还没有」
- `ruff check src/concierge.py web_server.py tests/test_concierge.py`：**All checks passed**（BLE001 仅 answer 与 _ground_login 的 LLM 降级 except，已 `# noqa` 注释，与 llm_mode.supplement 同口径）
- `mypy src/concierge.py`：**Success（no issues）**
- `import web_server` 无导入/语法错误，`handle('启动')→start_pipeline` / `handle('帮我')→ask_start` / 空 state 答「不知道」 / 登录与产物路由冒烟通过

## 未完成 / 待办

- **`list_sources` / `cookie_status` 只读 tool 白名单已就位但 `handle` 答疑未实际调用**：~~答疑只锚定 state（「卡在哪 / 下一步」）；登录与数据源接入指引的 LLM 润色（auth_hint 主路径 + LLM 润色）未实现~~ **已补**：`_ground_login` 锚定真实数据源清单 + cookie 状态，`_ground_products` 锚定真实产物，均经 `answer` 走 LLM 润色路径
- **Concierge LLM 润色未真调**：`answer` 无 key 直接回 ground，LLM 润色路径（有 key）未联调（本环境无 key）
- **判意纯关键词启发式**：无 LLM 补充判意（见 unverified #1）
- **前端无 Concierge 独立面板**：回复用 `addAgent` 纯文本，pipeline 产物仍复用现有卡片渲染在同一对话流（符合 PLAN 放置要求，但无气泡/多轮 UI）

## unverified_assumptions（未验证假设，待放行）

1. **判意关键词启发式**：`classify_intent` 用 `_QUESTION_KWS`/`_START_KWS`/`_AMBIGUOUS_KWS` 三组词表 + 裸画像默认 start。覆盖验收三例 + 裸画像「美妆博主」→ start，但复杂/口语化启动句可能误判（「不确定先确认」兜底 ask，不自动触发）。要更准需 LLM 判意补充路径。
2. **profile 抽取启发式**：`extract_profile` 前缀剥离（帮我做/做一条/一篇…），复杂画像短语可能抽不准；抽空回默认「美妆博主」。
3. **Concierge LLM 润色稳定性**：有 key 时 `answer` 调 `llm.call_llm` 润色 ground，真实模型是否严守「不编造」未验（仅 prompt 约束，无 judge 兜底）。
4. **web_server.py 未入 mypy 范围**：本阶段 mypy 只查 `src/concierge.py`。web_server.py 原有 12 处 mypy 报错（`_graph_app` Optional / `aget_state` / `run_quality_gates` 类型，历史未查），新增 `/api/concierge` 端点沿用同款 `aget_state` 写法，属既有模式非本阶段新引入；要整体 mypy 干净需单独立项修 web_server.py。

## 下阶段入口

P4-C4 完成，PLAN §五 C0–C4 全落地。C4 是 P4-C 最后一个子项。后续候选：① P4 整体收尾验收（六步 + 5 门 + Concierge 端到端真 LLM 联调）；② PLAN §七 设置面板（本缓，价值低）；③ web_server.py mypy 清理（见 unverified #4）。
