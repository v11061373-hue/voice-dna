# HANDOFF-P4-E — 收尾验收（G4/G5 运行时接线 + 端到端真 LLM 联调）

状态：完成 ✅ · 2026-10-19

## 完成度

### 任务 1 — G4/G5 接进 call_tool 热路径

- **`src/mcp_client.py`**：模块级 `_guard = MCPGuard(whitelist=default_whitelist(), audit_log_path=logs/audit.jsonl, audit_secret=env)` 单例，治理每次本地 tool 调用
  - `call_tool` 加 `cost`/`retry` 形参，本地 tool 调用前跑 `_guard.check(agent_id=tool, action=TOOL_ACTIONS.get(tool,"read"), cost, retry)`，拒绝 → `GuardDenied(d.gate, d.reason)`
  - 五门（G1 白名单 / G2 动作 / G3 风险 / G4 限流+预算 / G5 审计）全进热路径；原内联 G1（`tool_name not in VOICE_DNA_TOOLS`）由 guard 的 G1 白名单取代
  - 外部 `server.tool` 保留内联 G1 server 注册检查，不进 G4/G5（pipeline 不调外部 tool）

### 任务 2 — 端到端真 LLM 联调（DeepSeek 本机 key）- key 来源：`DEEPSEEK_API_KEY`（env 已设），联调脚本运行时 `os.environ["VOICEDNA_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]`，base_url=`https://api.deepseek.com`，model=`deepseek-chat`。key 只 env 读取，未落盘未打印
- 真调结果（非降级卡，persona ≠ FALLBACK 文案）：
  - `llm.call_llm` smoke：0.9s 返回「收到」
  - `style_mimic`：真 LLM 风格卡（无样本时 persona 遵 prompt 标「未知」，未编造）
  - `script_writer`：真 LLM 脚本（body/scenes/duration）
  - `publish_optimizer`：真 LLM 发布计划（platform/best_time/tags/hashtags）
  - `data_analyst`：真 LLM 分析（report/metrics/benchmark/anomalies）
- 全图 E2E（`app.ainvoke`）：管线跑通，`logs/audit.jsonl` 累计落盘（G5 在 pipeline 热路径生效）；质量门在空 trends 时正确 HALT 走 human_gate

### 任务 3 — token 计量 + G4 成本预算（②）

- **`src/llm.py`**：`_usage` 字典累加 `call_llm` 每次 `usage.prompt_tokens/completion_tokens`，`total_tokens()` 暴露累计（跨 main + judge 共享）
- **`src/mcp_guard/gateway.py`**：加 `charge(agent_id, cost)` 后付费累加 `_cost_spent`，不拒绝；下一次 `check` 的 cost 预算据此拒绝
- **`src/mcp_client.py`**：`call_tool` 本地 tool 调用前后量 `llm.total_tokens()` 差，`charge` 进 G4；`VOICEDNA_TOKEN_BUDGET`（空=不限）设成本预算

## 铁律核验

- key 只 os.environ：联调只读 `DEEPSEEK_API_KEY` → `VOICEDNA_API_KEY`，不落盘不落库不打印
- 未新增任何 key/cookie 落盘路径

## 测试证据

- `pytest`：**164 passed**（C4 基线 159，+5）
  - `tests/test_mcp_client.py`：G4 预算门超限 / G5 审计 / token 差 charge / token 预算超限拒绝
  - `tests/test_llm.py`：`call_llm` 累加 usage（total_tokens==15）
  - `tests/test_guard.py`：`charge` 后 `check` 拒绝
- `mypy src/mcp_client.py`：Success（no issues）
- `ruff check src/mcp_client.py tests/test_mcp_client.py`：**5 处既有报错**（`load_servers` 的 PLW0602/S110/BLE001 行 47/58，`list_tools` 的 S112/BLE001 行 125），均非本次改动引入，未修（手术式不扩范围）
- 端到端真调：6 agent 中 style/script/publish/analyst 四 LLM tool 真调通（DeepSeek）

## 未完成 / 待办

- **全流程到 END 未跑通**：本机无 cookie/网络，`trend_hunter` 全源优雅降级 `[]` → `topic_planner` 无输入 → 质量门空 trends HALT → human_gate。是数据源可用性问题，非 LLM/接线问题。要完整到 END 需真实 cookie 或网络可达数据源
- **topic_planner 未直接 LLM 验证**：空 trends 下走确定性路径，未真调 LLM（同 fallback 模式，无 baseline 才调）
- **time/retry 预算未启用**：token 成本预算已接（任务 3）；G4 的 time/retry 仍无计量源，`call_tool` 传 `cost=0.0, retry=0` 占位
- **外部 `server.tool` 不进 G4/G5**：审计只覆盖本地 6 tool（pipeline 路径）

## unverified_assumptions（未验证假设，待放行）

1. **audit_secret 硬编码兜底**：`VOICEDNA_AUDIT_SECRET` 未设时用 `"voice-dna-dev"`，仅 HMAC 校验非密钥；生产应设 env
2. **DeepSeek key 有效**：以 smoke 返回「收到」为证，未做长时间/多请求压测
3. **审计文件累积**：`logs/audit.jsonl` 测试与手跑共用累积，多进程并发写未上锁（gateway 已有 ponytail 注释）
4. **token 预算口径**：`VOICEDNA_TOKEN_BUDGET` 空=不限；限流按「调用次数」非 token 数，token 级预算按 `call_llm` usage 累加（judge 独立 provider 同走 `call_llm`，共享 `_usage`）

## 下阶段入口

P4 建设五阶段（B/A/D/C/C4）+ 收尾验收（E）全落地。剩余非阻塞项：① 真实数据源跑完整到 END；③ 外部 `server.tool` 纳入 G4/G5；④ web_server.py mypy 清理。
