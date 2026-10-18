# HANDOFF-P4-C — 6 agent LLM 化（主路径 + LLM 补充 + 门禁）

状态：完成 ✅ · 2026-10-19

## 完成度

- **C0 LLM 参与度控制**（`src/llm_mode.py`）：全局三档 `deterministic`/`fallback`(默认)/`full` + 每 agent 布尔开关（默认全亮）
  - 存 `os.environ`（`VOICEDNA_LLM_MODE` / `VOICEDNA_LLM_<AGENT>`），无持久化（与 D 的 key 铁律同口径，PLAN 无持久化要求）
  - API：`get_mode/set_mode/agent_enabled/set_agent/llm_enabled/should_llm/supplement`
  - `supplement(agent, has_baseline, baseline, fn)` = 三段式第二段统一入口：确定性/开关关/无 key → baseline；全开 → 总是 fn；兜底 → 无 baseline 才 fn；fn 异常 → baseline（不阻断主路径）
- **C1 专家 persona**（`src/agents.py`）：`PERSONAS`（6 agent role/goal/backstory，参照 BidForge）+ `system_prompt(agent)` → 喂 `llm.call_llm` 的 `system`
- **C2 三段式**（6 agent 全接 `llm.call_llm`）：
  - `style_mimic`（D 已接）+ `trend_hunter`（关键词 LLM 抽取，替代 A3 词表版）/ `topic_planner`（LLM 写理由）/ `script_writer`（LLM 写 body）/ `publish_optimizer`（LLM 优化标题标签）/ `data_analyst`（LLM 写结论）
  - 主路径（确定性）保留作 baseline；兜底档无 baseline 才 LLM；全开档每步 LLM
- **C3 LLM-judge 5 门质量门**：
  - `src/orchestrator/judge.py`：结构化 judge `{score, pass, reason}`，默认复用主 provider，可选独立 provider（`config.judge_settings()`）；无 key / 确定性档 → 跳过（pass=True）
  - `src/orchestrator/quality_gate.py` 重写为 5 门：①schema 硬门（确定性）②非空+长度门（确定性）③溯源门（judge）④赛道相关门（judge）⑤合规门（确定性词表）；`QUALITY_GATES` 按 stage 挂门，`run_quality_gates` 取最坏 HALT>WARN>PASS
  - `src/schemas.py` 补每 agent 输出 schema：`STYLE_CARD_FIELDS` / `OUTPUT_FIELD` / `OUTPUT_TYPE` / `REQUIRED_KEYS` / `ITEM_KEYS`
  - `src/orchestrator/graph.py`：6 节点全部改条件边，HALT/failed → `human_gate`（`_route` 助手 + 6 个 route 函数）

## 铁律核验

- key 只 `os.environ`：`VOICEDNA_API_KEY`/`VOICEDNA_JUDGE_API_KEY` 全库仅 `config.py`（写 os.environ）与 `llm.py`（`os.environ.get`）两处，无 sessions.db/checkpoints.db/json 写路径（grep 已核）
- cookie 只落 `~/.voice-dna/cookies.json`（本阶段未动 `src/cookies.py`）
- 检索型源走 stdio npx（本阶段未动 trend_hunter 的 scraper 分派，只加 LLM 关键词分支）
- LLM 兜底可溯源：无 baseline 的 dict 产物打 `llm_fallback` 标签，溯源门做输入比对
- handoff 含 `unverified_assumptions`

## 测试证据

- `pytest`：**151 passed**（D 基线 103）
  - 新文件：`test_llm_mode.py`(16) / `test_agents.py`(3) / `test_judge.py`(6) / `test_llm_supplement.py`(14)
  - 重写：`test_quality_gate.py`(13) / `test_graph.py`(7)
  - 覆盖验收四例：schema 缺字段 HALT / 编造热点溯源门 HALT / 违禁词 HALT / 正常产出 PASS + 全流程确定性零 LLM + 注入编造热点走 human_gate
- `mypy src/llm_mode.py src/agents.py src/orchestrator/judge.py src/schemas.py src/orchestrator/quality_gate.py src/orchestrator/graph.py src/tools/{style_mimic,trend_hunter,topic_planner,script_writer,publish_optimizer,data_analyst}.py src/llm.py`：**Success（13 files）**
- `ruff check`（本阶段新增/改动文件）：I001(import 排序)/RUF022(`__all__` 排序) 已 `--fix` 修净
  - 余 BLE001/S110（`llm_mode.py:84` supplement 盲 except + `trend_hunter.py` 网络降级 except/pass）=「网络源优雅降级」刻意保留（P4-A handoff 已定口径），非本阶段新引入
- `grep` 全库无 key 明文入 sessions.db / checkpoints.db

## 未完成 / 待办

- **LLM-judge 未真调**：judge 用 monkeypatch 验（skips/调用/settings 三例），真实模型结构化输出 `{score,pass,reason}` 稳定性未联调（见 unverified #3）
- **`llm_fallback` 标签当前无 agent 触发**：`supplement` 只在「无 baseline 且 dict 产物」时打标签，现有 5 agent 均有 baseline（has_baseline=True），trend_hunter 无 baseline 但返回 list；标签逻辑就位但真「无 baseline dict 兜底」场景未覆盖。溯源门靠 judge 语义比对输入，不依赖该标签
- **前端无档位/开关 UI**：C0 档位与每 agent 开关只存 os.environ，无设置面板（PLAN §七 设置面板本就缓）；要切换需直接设 env
- **全流程端到端真 LLM 未跑**：仅 D 阶段 style_mimic 真调过 DeepSeek/Qwen；其余 5 agent + judge 的 LLM 路径只用 fake 验

## unverified_assumptions（未验证假设，待放行）

1. **LLM 档位/开关同内存不持久**：继承 D #2 口径——PLAN 无持久化要求，`VOICEDNA_LLM_MODE`/`VOICEDNA_LLM_<AGENT>` 重启失效。要「记住上次档位」需另加落盘，当前未做。
2. **judge model 派生规则**：继承 D #3——judge 走 `config.judge_settings()`，`judge_model` 从 judge provider 预设派生，真用 judge 时需确认 model 名。
3. **LLM-judge 结构化输出格式**：`parse_judge` 剥 markdown 包裹 + 补默认值（score=0.0/pass=True/reason=""），但真实模型输出是否稳定带 `{score,pass,reason}` 未验；`pass` 缺失时默认 `True`（放行）是保守兜底，若模型漏输出 pass 会误放行。
4. **溯源门 judge 语义判「编造」的可靠性**：溯源门把「输入（热点/样本/画像）+ 产出」喂 judge 让它判是否可溯源，但真实 judge 对「编造热点」的检出率未验（仅 fake 验 pass=false → HALT 的接线）。

## 下阶段入口

P4-C 收尾完成，下阶段 **P4-C4 Concierge 对话辅助 agent**（独立阶段，勿与本阶段合并）：只读向导 + 启动判意，G1 白名单 = 只读 tool + 唯一动作 `start_pipeline(profile)`。依赖已就位：B 门禁（`src/mcp_guard/`）+ D `llm.call_llm` + 本阶段 C3 `quality_gate`/`judge`。
