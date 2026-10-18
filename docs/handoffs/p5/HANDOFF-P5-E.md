# HANDOFF-P5-E — 后置增强 + v2 回流

状态：P5-E 代码完成 + F2/F3/F4/F5 已验证 · 2026-10-19

## 完成度

### 改动清单（5 步任务全落）

| 改动 | 文件 |
|------|------|
| 状态字段 `candidate_videos` / `transcripts` / `video_visual` + `v1_script`（可选） | `src/schemas.py` |
| `select_candidate_videos()`：抓完记代表性视频（热度降序前 1-3、platform 为视频平台） | `src/tools/trend_hunter.py` |
| `trend_hunter_node` 返回 `candidate_videos`；`style_mimic_node`/`script_writer_node`/`data_analyst_node` 转发 `transcripts`/`previous_script`；新增 `v2_app` 尾图（入口 style_mimic，不复跑 trend/topic） | `src/orchestrator/graph.py` |
| `_style_mimic`/`_script_writer`/`_data_analyst` 补 `transcripts`/`script`/`previous_script` 参数 | `src/mcp_server.py` |
| style_mimic / script_writer 收 `transcripts`，并入 prompt 可溯源素材段 + `_fmt_transcripts()` | `src/tools/style_mimic.py`、`src/tools/script_writer.py` |
| `compare_scripts()` + `_content_words()`；`run()` 收 `previous_script`/`transcripts` 出结构化对照；对照 verdict 挂 report 尾（放 supplement 之后，full 档 LLM 重写不丢） | `src/tools/data_analyst.py` |
| 溯源门 prompt 补转录逐字稿 | `src/orchestrator/quality_gate.py` |
| `_run_pipeline` 拆 `_stream_and_render`/`_ask_transcribe`；END 后 `cl.AskActionMessage` 问「转录哪个（跳过/全部/指定）」→ 逐条 `transcribe` → 二次跑 `v2_app` | `app.py` |

### 数据流（落地）

```
主流程 trend→topic→style→script→[门]→publish→analyst→[门]→END
        └ trend_hunter_node 顺手 candidate_videos（热度前 1-3 视频）
END 后（chainlit）：AskActionMessage 问转录 → transcribe.run 逐条 → transcripts 入 state
  → v1_script 快照 → v2_app 二次跑（style→script→publish→analyst，复用 v1 trends/topics）
  → data_analyst 出 comparison {changed, grounded, verdict: 更好/变化/被验证/未变}
```

## 测试证据（全部实跑）

- `pytest -q`：**208 passed**（基线 194 + 14 新测：schemas 2 + trend_hunter 2 + graph 5 + data_analyst 5）。
- `ruff check`（P5-E 触及文件）：**All checks passed**。
- `mypy src`：**Success: no issues found in 26 source files**。
- **F2** ✅ 真数据：`trend_hunter.run(profile='数码测评', enabled=['bilibili'])` → 7 热点，
  `select_candidate_videos` → 3 条真实 bilibili BV url（非空）。
- **F5** ✅ 甩链接：`transcribe.run(source='…/BV1LEJ96bE7c')` → 下载 29,226,098 bytes
  mp4 + funasr local → **text 755 字非空中文**（backend=local）。
- **F3** ✅ 逻辑层：v2 脚本 `changed=true` + `grounded=true`，`compare_scripts` verdict
  **「更好」**（v2 落地「一休/数码/二十冠王/瞬爆/冰盘」等转录词，且与 v1 不同）。
- **F4** ✅ E2E（trace 门隔离后）：`v2_app.ainvoke` 达 `data_analyst`，analytics 含
  `comparison` 字段，report 尾 **「v1 vs v2 对照：更好」**（full 档 LLM 重写后仍保留，
  见 data_analyst 修复）。

## 未完成项

1. **F1 未达成（全图 E2E 到 END 非 human_gate）**：trace 门（P5-A 的 LLM-judge）HALT 了
   LLM 脚本。根因 = qwen full 档会编造素材里没有的具体细节（如「9876 淘汰」对不上热点
   「近万淘汰」），溯源门判编造 HALT。这是 **P5-A 溯源门严格度 + script_writer prompt 未
   约束不编造**，非 P5-E 回归——P5-E 未触及 trace 门 / script_writer 编造约束。
2. **F3/F4 graph-level（不经 trace 门隔离）被同一门阻断**：v2 脚本虽落地转录词
   （verdict 更好），但 LLM 混入编造比喻（「架构重铸、缓存重生、硅基经脉」），trace 门
   HALT，v2 管到 data_analyst 前停。逻辑层 `compare_scripts` + F4 隔离 E2E 已证明对照链
   正确，只差 trace 门放行。

## 下阶段入口

按 PLAN-P5.md §六，P5-E 完成，下一 phase 二选一：

- **P5-D video_vision**（视觉分镜，功能态，可与 P5-F 并行）：`video_visual` 状态字段已
  预留，`VOICEDNA_VISION=0` 短路门待落。
- **P5-F 云端 ASR 接线**（可选最后）：`_asr_cloud` 接 DashScope callback 流式（P5-B 只留
  stub），默认仍 local。
- **P5-G 全仓 lint/mypy 清理**（收尾，E3 达标）：25 既有告警 + 根目录 `web_server.py`/
  `app.py` 13 告警。

顺带（P5-E 边界外，建议并入 P5-A 收尾或 P5-G）：trace 门严格度 vs script_writer 编造
具体数字的冲突，是 F1 卡点。若 F1 要绿，需在 script_writer prompt 加「只依据素材，不编造
具体数字/品牌/型号」约束，或调 judge 宽容度——非 P5-E 范围，留决策。

## unverified_assumptions

1. **F1 的「溯源门 PASS」未复现**：本会话 qwen judge + full 档下 trace 门一律 HALT。P5-A
   当时 F1 通过的状态（哪档位/哪 judge/哪温度）未在本会话复现，故 F1 记「未达成」而非
   「回归」。
2. **chainlit `_ask_transcribe` 未端到端 UI 手测**：本会话只验证 graph 层 + transcribe
   组件 + 代码审阅 `cl.AskActionMessage` 交互（`.name`/`.payload`）；未起 chainlit 前端点
   按钮走「跳过/全部/指定」三分支。AskActionMessage 交互路径待 P5-E 后真 UI 手测。
3. **bilibili fnval=0 DASH-only 分支未测**（承 P5-C）：部分新视频 fnval=0 可能 durl 空，
   需回落 fnval=16。本会话 BV1LEJ96bE7c 直下成功。
4. **funasr-server 进程回收风险**（承 P5-C）：本会话 `:8000` 有响应；会话结束可能被回收，
   下阶段功能实测前先 `curl :8000`，否则重起 `funasr-server --device cpu`。
5. **`enabled_sources=None`（chainlit 默认）下 trend_hunter 走全平台**，本会话观察到偶发
   返回 0（douyin/xhs 需登录 + cn-scraper 抖动）；显式 `['bilibili']` 稳定返回 7。这是
   P4/cn-scraper 迁移既有行为，非 P5-E 引入，但影响 F1 复现稳定性——E2E 时显式喂
   `enabled_sources=['bilibili']` 可复现。
6. **ruff 全量基线**：`ruff check src tests` 仍有 25 既有告警（在 P5-E 未触及文件），
   已排期 P5-G；P5-E 触及文件单独 ruff 全绿。
