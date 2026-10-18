# HANDOFF-P5 — 视频内容摄入方案定稿交接（P5 开工前状态）

状态：方案已定稿待批准 · 2026-10-19

## 完成度（本会话）

### 已落盘的工程产物

- **PLAN-P5.md**：完整工程方案（可行性结论 + 架构 + 任务分解 P5-A~F + 工程/功能验收标准 + 进度管理表）。
- 上一会话已完成的增量（基线 169→170 测试绿）：
  - cn-scraper 迁入 trend_hunter（bilibili/douyin/weibo/xhs 4 平台 search 契约）。
  - 可选回流 loop（`loop_rounds`/`loop_count`，默认关）。

### 本会话诊断 + 证据（非代码，是决策依据）

1. **trace-gate HALT 根因定位**：全图 E2E（bilibili 真数据 + LLM full）卡在 script 溯源门，其余 3 门 PASS。根因 = `script_writer_node` 只传 `style_card`，`SCRIPT_PROMPT_TEMPLATE` 只注入 `{subject}`，script_writer 拿不到 trends/samples/transcripts，LLM 编造具体品牌/色号被溯源门正确拦下。门没错，是素材没喂。
2. **ASR 实测证据**（`C:\Users\rog\agent-senses\`）：
   - 本地 FunASR SenseVoiceSmall：`funasr-server.exe` 在 PATH；`funasr-server.log` 显示 CPU **RTF 0.29**（30s 视频 ≈ 9s，10min ≈ 3min）。已验证 12 条抖音视频转录（`dy_transcripts/*.md`）。
   - `ears_mcp.py` 已有视频→抽音轨→ASR 的 `transcribe` 工具（`imageio_ffmpeg` 自带 ffmpeg）。
   - `dy_transcribe.py`：CDP `:9222` 抓抖音媒体流法（已验证）。
3. **云端 DashScope ASR 实测**：`/compatible-mode/v1/models` 列 8 个 ASR 模型（`qwen-audio-3.0-asr-flash`、`fun-asr-flash-2026-06-15`、`qwen3-asr-flash-realtime` 等）；但 `audio/transcriptions` multipart **断连**（Server disconnected）；原生 `dashscope` SDK（已装）`Recognition.__init__` 已改 **callback 流式**（必填 `callback`），非旧阻塞 `call(file)`。结论：云端能通但要 30min-1h 接流式，未接。
4. **视觉**：`DASHSCOPE_API_KEY` 已 setx 持久；手B 已用 Qwen-VL-Max 验证视觉。分镜分析零现成代码。

## 已锁定的设计决策

1. 内置 `transcribe()` 接口，不内置模型；本地 funasr 默认，云端 DashScope 可选。
2. 视频摄入 = 后置增强，不进主管线；trend_hunter 顺手记 `candidate_videos`。
3. 跑完 END 后调用层（app.py）询问「转录哪个视频」，中途不打断。
4. v2 回流：转录逐字稿作新素材，二次跑带素材，data_analyst 出 v1 vs v2 对照。
5. 视觉功能态：抽帧 + Qwen-VL，默认关（`VOICEDNA_VISION=0`）。
6. 素材统一：可溯源素材 = trends + samples + transcripts，喂 style_mimic/script_writer（P5-A 和 P5-E 同根）。

## 待拍板（已给默认，未显式确认）

1. v2 回流 = 二次 ainvoke 复用 v1 trends（不重抓），只重跑 style→script→publish→analyst。
2. douyin/xhs 下载先只支持 bilibili 直下，CDP 法后补。
3. 视觉帧率 1 帧/3s。

## unverified_assumptions（未验证假设，待放行）

1. **funasr RTF 0.29**：来自 2026-10-06 日志 + 推断，未在本会话重跑确认；`funasr-server.exe` 在 PATH 是已确认事实。
2. **bilibili 视频直下**：只验证了 `bilibili_search` 返回 url，未实测下载 mp4。
3. **云端 DashScope 断连根因**：未深究（可能 endpoint/格式/model 名/域），留 P5-F 验证。
4. **v2 回流二次 ainvoke 复用 v1 trends**：设计假设，未实现验证。
5. **新用户无 funasr**：本地默认假设用户愿意 `pip install funasr` + 下模型；未做新环境安装验证。

## 下阶段入口

按 PLAN-P5.md §六执行顺序，先 **P5-A 素材喂入 script_writer**（小、快、已批准）：

1. `graph.py:68` `script_writer_node` 补传 `trends`/`samples`/`account_profile`。
2. `script_writer.py` `run()` 收素材 + `SCRIPT_PROMPT_TEMPLATE` 加素材段 + `_llm_script` 扩参。
3. `mcp_server.py:_script_writer` 补参数。
4. TDD：先写「喂素材后 LLM 输出含素材词」失败测试 → 实现 → 全量 pytest 绿（≥200）。
