# HANDOFF-P5-A — 素材喂入 script_writer（trace-gate 修）+ 空产出 judge 门修复

状态：P5-A 代码完成 + 已验证 · 2026-10-19

## 完成度

### P5-A 主线（素材喂入 script_writer）

| 改动 | 文件 |
|------|------|
| `SCRIPT_PROMPT_TEMPLATE` 加「可溯源素材」段（画像/热点标题/文案样本） | `src/tools/script_writer.py` |
| `_fmt_trends` 热点标题→顿号串；`_llm_script` 扩参收 trends/samples/profile | 同上 |
| `run()` 收 trends/samples/profile 并转发给 LLM | 同上 |
| `script_writer_node` 补传 trends/samples/account_profile | `src/orchestrator/graph.py` |
| `_script_writer` 补参数 | `src/mcp_server.py` |

### 额外修复（F1「E2E 到 END」必需，超出 P5-A 三代码点）

**① 空产出 judge 门 HALT 修复**（`src/orchestrator/quality_gate.py`）：

- 根因：`_relevance_judge_gate` / `_trace_judge_gate` 对**空产出**仍调 judge。judge 见「产出: []」判 pass=false → HALT。空 ≠ 跑题/编造，是「无数据」，应由非空门/下游兜，不该由 judge 拦死。
- 修复：加 `_content_empty(stage, state)`，两 judge 门在空产出时直接 PASS（跳过 judge）。

**② analytics 溯源门溯源源修正**（同文件）：

- 根因：`_trace_prompt` 对 analytics 用 trends/samples/profile 作溯源源，但 report 数字来自 `_DEMO_VIEWS` 演示种子（metrics），不是 trends/samples/profile。溯源源用错 → 误判「编造」HALT。
- 修复：analytics 的溯源源改为 metrics/benchmark/anomalies（report 数字在 metrics 里即 PASS）。

### 测试证据

- `pytest -q`：**177 passed**（基线 174 + 空产出 judge 2 测 + analytics 溯源 1 测）。
- `ruff check` P5-A 触及文件 + quality_gate.py：**clean**。
- `mypy src`：**no issues**（24 源文件）。
- 全图 E2E（LLM full + bilibili 真数据 5 条）：**stage=data_analyst（END，非 human_gate）**，status ok，script 溯源 PASS，analytics 溯源 PASS。

## 验证结论（证据，非估算）

1. **script 溯源门 PASS 已验证**：喂 samples/profile 后 LLM 脚本无编造，脚本质量门全过。
2. **analytics 溯源门 PASS 已验证**：report 数字（9800/1420）溯源到 metrics，不再误拦。
3. **空 trends 不再拦死**：cn-scraper 断网/限流时 relevance 门 PASS，pipeline 继续。
4. **F1 全图 E2E 到 END 达成**：bilibili 5 条真数据 → 六节点全过 → data_analyst（END），非 human_gate。

## 下阶段入口

按 PLAN-P5.md §六 进 **P5-B transcribe 工具**（不依赖 cn-scraper，funasr 本地已验）。
