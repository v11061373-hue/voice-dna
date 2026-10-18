# voice-dna 项目全景总结（P4 + P5 全量交付）

> 用途：单一真相源，汇总 voice-dna（表达基因）P4 + P5 两阶段全部新增文档与能力。
> 数据全部来自仓库实测（测试/真实数据 E2E），非估算。最后更新 2026-10-19。

---

## 一、新增 md 文件清单

> 归档位置：PLAN 在 `docs/plans/`，HANDOFF 在 `docs/handoffs/p4/` 与 `docs/handoffs/p5/`。

| 文件 | 阶段 | 一句话 |
|------|------|--------|
| `PLAN-P4.md` | P4 方案 | 专家 Agent + 五门网关 + 数据源可选用 + 个人账号 + Concierge |
| `HANDOFF-P4-B.md` | 安全网关 | G1–G5 五门（白名单/动作/风险/预算/审计） |
| `HANDOFF-P4-A.md` | 数据源层 | 能力声明 + chip 选用 + 关键词召回 + cookie 登录 |
| `HANDOFF-P4-D.md` | 个人账号 | 多供应商切换 + key 铁律 + `llm.py` 抽象 |
| `HANDOFF-P4-C.md` | 6 agent LLM 化 | 三段式 + 5 门质量门 + LLM-judge |
| `HANDOFF-P4-C4.md` | Concierge | 只读向导 + 启动判意 agent |
| `HANDOFF-P4-E.md` | 收尾验收 | G4/G5 运行时接线 + 端到端真 LLM 联调 |
| `PLAN-P5.md` | P5 方案 | 视频摄入（ASR + 视觉分镜）+ 可溯源素材回流 |
| `HANDOFF-P5.md` | P5 定稿 | P5 开工前状态交接 |
| `HANDOFF-P5-A.md` | 素材喂入 | trace-gate 修（script_writer 可溯源素材） |
| `HANDOFF-P5-B.md` | transcribe | ASR 转录工具（funasr local + DashScope cloud） |
| `HANDOFF-P5-C.md` | video_download | 视频下载工具（bilibili 直下 / douyin/xhs cookie） |
| `HANDOFF-P5-D.md` | video_vision | 视觉分镜工具（抽帧 + Qwen-VL） |
| `HANDOFF-P5-E.md` | v2 回流 | 后置增强 + 转录素材二次跑 + v1/v2 对照 |
| `HANDOFF-P5-F.md` | 云端 ASR | DashScope 流式接线（可选） |
| `HANDOFF-P5-F1.md` | 溯源门修复 | script 零硬编造，210 绿 |
| `HANDOFF-P5-F5.md` | 甩链接 | 视频链接直下 + 转录真实链 |
| `HANDOFF-P5-F34.md` | 回流 E2E | v2 回流全图 E2E 真数据 |
| `HANDOFF-P5-UI.md` | 交互接线 | 甩链接/web_server v2/视觉真实现，221 绿 |
| `HANDOFF-P5-G.md` | 收尾清理 | 全仓 lint/mypy 归零 |

---

## 二、能力全景（按主题归类）

### 1. 多模型供应商切换（P4-D）
- `src/llm.py` 通用 OpenAI 兼容 client，6 agent 共用；`config.py` 供应商预设下拉，加一个 = 一行。
- 预设：DeepSeek / 通义 Qwen / 智谱 GLM / Kimi / 腾讯混元 / OpenAI 兼容（自定义 base_url + model）。
- LLM-judge 默认复用主 provider，可选独立 provider 解耦（`judge_provider/base_url/key`）。
- **铁律**：key 只落 `os.environ`（内存），不落盘不落库；`/api/config` GET 只回「已配/未配」。
- 真调验证：DeepSeek + Qwen 双 provider 真调通（`degraded=False`，真实中文风格卡）。

### 2. 六步专家 Agent 管线 + LLM 参与度控制（P4-C）
- 6 个专家 Agent：trend_hunter / topic_planner / style_mimic / script_writer / publish_optimizer / data_analyst。
- 三段式架构：**确定性主路径（免费不幻觉）+ LLM 补充 + LLM 兜底**；LLM 不替代主路径。
- 全局三档 `deterministic/fallback/full` + 每 agent 布尔开关（`src/llm_mode.py`）。
- 每个 agent 独立专家 persona（role/goal/backstory，`src/agents.py`）。

### 3. 五门安全网关（P4-B）
- 复制适配 BidForge `mcp_guard`：G1 工具白名单 / G2 动作门 / G3 风险门 / G4 预算门（成本+限流+重试）/ G5 审计门（JSONL + HMAC）。
- `mcp_client.call_tool` 未注册 tool 返回 `GuardDenied` 而非崩。
- G4 成本预算：token 计量 + `VOICEDNA_TOKEN_BUDGET` 预算门。

### 4. 五门质量门 + LLM-judge（P4-C C3）
- `quality_gate.py` 5 门：①schema 硬门 ②非空+长度门 ③溯源门（LLM-judge 判编造 HALT）④赛道相关门（LLM-judge）⑤合规门（广告法违禁词表）。
- LLM-judge 结构化评分 `{score, pass, reason}`，第三方模型可配，阈值放行/退回。
- HALT/failed 走 `human_gate` 人工介入。

### 5. 数据源接入（P4-A）
- `plugins/sources.json` 能力声明：bilibili/youtube keyless、douyin/weibo cookie、baidu-search/bing-cn 检索源。
- 关键词召回：`heat × 时间衰减` 排序 + 标题相似度去重（difflib，无 embedding）。
- 检索源走 stdio `npx baidu-search-mcp / bing-cn-mcp`（MCP StdioTransport，无自写爬虫），归一化 4 种返回形状。
- Cookie 登录：V1 手动贴（只落 `~/.voice-dna/cookies.json`）+ V2 playwright 自动扫码。

### 6. 数据回流（P5-E v2 回流）
- 状态字段 `candidate_videos / transcripts / video_visual / v1_script`。
- trend_hunter 顺手记代表性视频（热度前 1–3）；END 后询问「转录哪个」，逐条 transcribe → 二次跑 `v2_app`（复用 v1 trends，不重抓）。
- data_analyst 出 v1 vs v2 结构化对照（`changed/grounded/verdict: 更好·变化·被验证·未变`）。

### 7. 视频摄入（P5-B/C/D/F）
- `transcribe`：ASR 转录，url → download → ffmpeg 抽 16k 单声道 → funasr 本地（默认）/ DashScope 云端（可选）。
- `video_download`：bilibili 直下（无登录）；douyin/xhs 复用 cookie/CDP。
- `video_vision`：ffmpeg 抽帧 + Qwen-VL（qwen3-vl-plus）逐帧描述 → 分镜节奏风格卡；`VOICEDNA_VISION` 成本门默认关。
- 甩链接模式：`is_video_url` 检出链接 → 下载+转录+视觉 → v2 回流生成脚本。

### 8. 前端交互（chainlit + FastAPI）
- chainlit 主对话（`:8081`）：六步流水线 + 甩链接 + 候选视频转录 + 视觉分镜卡。
- FastAPI web_server（`:8082`）：`/api/run` 逐步执行（LangGraph interrupt_after 每节点暂停）+ `/api/v2` 回流 + `/api/config` + `/api/cookie` + `/api/concierge` + `/api/tool`。
- 静态前端：数据源 chip 栏（localStorage 持久化）、个人账号面板、候选视频「转录并 v2 回流」按钮。

### 9. Concierge 对话辅助 agent（P4-C4）
- 只读向导 + 启动判意：白名单 = 只读 tool（get_state/list_sources/cookie_status）+ 唯一动作 `start_pipeline(profile)`。
- 判意三态：start（明确启动）/ ask（不确定反问）/ answer（答疑），答疑锚定真实 state，不编造。

### 10. 会话状态持久化 / 对话上下文记忆
- LangGraph Sqlite checkpointer（`checkpoints.db`）：按 `thread_id` 持久化每个会话的图状态，支持中断/恢复/逐步执行。
- `SessionStore`（`sessions.db`）：会话列表 CRUD。
- 前端 `localStorage`：数据源选中集等 UI 状态；`cookies.json`：登录态。

---

## 三、测试与工程证据

- **测试**：66 → 221 全绿（P4 五阶段 66→164；P5 164→221）。
- **lint**：`ruff check src tests` 0 告警（25 → 0）。
- **类型**：`mypy src web_server.py app.py` 0 告警（17 → 0，29 源文件）。
- **真实数据 E2E**：
  - F5 甩链接：bilibili 下载 29,226,098 bytes + funasr 转录 755 字中文。
  - F2/F3/F4 回流：真数据视频 → 719 字转录 → v2 脚本 grounded+changed、verdict「更好」、到 END。
  - F7 视觉：Qwen-VL 抽 6 帧，非空分镜卡（shot_rhythm/visual_style/scenes）。
- **铁律核验**：grep 全库无 key/cookie 明文落盘；临时音视频落 tempfile 用完删。

---

## 四、简历版（复制即用）

见同目录 [`RESUME.md`](RESUME.md)。

## 五、GitHub 简介版（复制即用）

见仓库根目录 [`README.md`](../README.md)。
