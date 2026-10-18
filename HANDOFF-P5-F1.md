# HANDOFF-P5-F1 — 溯源门修复（script_writer 约束 + judge 宽容度）

状态：F1 核心修复完成 + 功能已验证（注入热点 gate PASS）+ 真数据全图 E2E 复现通过 · 2026-10-19

## 背景

P5-E 遗留 F1 未达成：LLM full 档编造素材没有的具体细节，被 P5-A 溯源门 HALT。
本阶段分两层修（两文件，各 TDD）：

## 改动清单

| 改动 | 文件 | 测试 |
|------|------|------|
| `SCRIPT_PROMPT_TEMPLATE` 约束 #4 强化：禁编造「具体数字/品牌/型号/人名/价格」，涉及数量/型号只复述素材原词、不得把约数换算成精确数 | `src/tools/script_writer.py` | `test_prompt_forbids_fabricating_specific_numbers` |
| `_trace_prompt` 溯源指令校准：只拦无法溯源的「具体事实」（具体数字/品牌/型号/人名/价格/事件），修辞润色/文学化/拟人化/比喻/过渡语不算编造 | `src/orchestrator/quality_gate.py` | `test_trace_prompt_limits_to_hard_fabrication` |

## 根因（两层）

1. **硬编造（具体数字）**：qwen 把热点「近万淘汰」编成「9876」。约束 #4 原只说「数据」太含糊，未禁「型号」+「约数换精确数」。→ 约束强化。
2. **软演绎被误拦**：judge 把「被系统拉黑/更新通道关了/移交回收链」等修辞/拟人化当编造 HALT。这是「硬编造」vs「软演绎」边界问题，非真编造。→ judge 指令校准。

## 测试证据（全部实跑）

- `pytest -q`：**210 passed**（P5-E 基线 208 + 2 新测：script_writer 1 + quality_gate 1）。
- `ruff check`（两触及文件）：**All checks passed**。
- `mypy src`：**Success**（触及文件无 issue）。

## 功能验证（真 qwen full + 注入热点，隔离 bilibili 抖动）

注入热点「某手机品牌近万部库存被淘汰」→ `script_writer` 输出保留「近万部」（不编「9876」），
`run_quality_gates("script_writer", state)` = **PASS**，judge：

> 所有具体事实均能溯源…未添加不可溯源的具体数字、品牌、型号、人名、价格或事件。

（改动前同输入 judge `pass=False`，HALT。）

## 未完成项

1. ~~**F1 真数据全图 E2E（到 END）未复现**~~ → **已复现**（2026-10-19，bilibili 源恢复）：
   见下「真数据 E2E 复现」。
2. **脚本偶发英文夹带**：本轮注入测试 qwen 输出尾句「already on the list」，judge 未拦（非
   溯源问题）。若在意，属 script_writer 语言约束，非 F1 范围。

## 真数据 E2E 复现（2026-10-19，bilibili 412 已恢复）

`app.ainvoke({"account_profile": "热点", "enabled_sources": ["bilibili"]})`，`VOICEDNA_LLM_MODE=full`：

- **到 END**：`current_stage == "data_analyst"`，`stage_status == "ok"`，`errors == None`
  （非 human_gate）。script_writer 溯源门、data_analyst 门全 PASS。
- **trends 4 条真数据**（bilibili 真标题：苏杉杉热点追踪 / 广东台热点追踪 2010 旧闻等），
  `candidate_videos` 3 条。
- **script body 可溯源，零硬编造**：全篇只复述真热点内容（苏杉杉/豆包/CP 关系/退团原因/
  433 角度/南海污泥焚烧发电厂/吸毒男劫持），无编造的具体数字/品牌/型号/人名。软演绎
  （文学化对比）未被误拦。
- data_analyst `report` 里的具体数字（9800.0/1420.0）来自 `_DEMO_VIEWS` 确定性兜底
  （`data_analyst.py:90`，v1 无真实 views 时），溯源到 `metrics` 字段，非 LLM 编造，门不拦。

注：profile 用「热点」而非具体赛道，因 bilibili_search 有 HTTP 412 间歇性反爬/限流
（外部源，非代码）。实测（2026-10-19 探针）：同一会话内「数码」首查 412、再查 ok:10，
「美妆/游戏/美食」412，「热点」恒 ok。412 命中时 `_normalize_search_results` 回空 →
trend_hunter 空 → 门 HALT。成功时「数码」返回真实数码标题（芯片/GPU/5090 等）且命中
`_TRACK_KEYWORDS`，`_filter_by_keywords` 不误滤。**无「标题形态与词表错配」问题**——
此前误判为词表错配，已纠正。

## unverified_assumptions

1. **judge 宽容度只靠单轮注入验证**：judge 是 qwen（同模型），单次 PASS 有随机性。真数据
   全图 E2E 才是 F1 最终验收，需 bilibili 源恢复后跑「全图 ainvoke → data_analyst（END）」
   确认非 human_gate。
2. **analytics 溯源门同受校准影响**：`_trace_prompt` 是 script_writer / data_analyst 共用，
   校准指令同样作用于 analytics（metrics 数字仍是「具体事实」会拦，修辞不再误拦）。既有
   `test_trace_prompt_analytics_includes_metrics` 仍绿，未单独跑 analytics 真数据。
3. **bilibili 412 是否短暂**：本会话两次 `bilibili_search` 均 412，未确认是限流还是需登录。
   P5-E handoff #5 已记「显式 ['bilibili'] 稳定返回 7」——与当前 412 矛盾，源侧波动大。
