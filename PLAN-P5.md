# P5 方案 — 视频内容摄入（ASR 转录 + 视觉分镜）+ 可溯源素材回流

> 状态：可行性方案 + 任务分解（待批准后执行）
> 最后更新：2026-10-19
> 前置：P4 六阶段完成（169 测试绿）+ cn-scraper 迁移 + 回流 loop

---

## 一、可行性结论（实测证据，非估算）

| 能力 | 判定 | 证据 |
|------|------|------|
| ASR 本地 funasr（SenseVoiceSmall） | ✅ 已验证 | 12 条抖音视频转录过；本机 `funasr-server.exe` 在 PATH；CPU RTF 0.29（30s 视频 ≈ 9s） |
| ASR 云端 DashScope | 🔸 模型在列未接通 | 8 个 ASR 模型在 `/models`；兼容模式 multipart 断连；原生 SDK 已改 callback 流式。接线 30min-1h |
| 视觉 Qwen-VL-Max | 🔸 key 已持久，需新写 | `DASHSCOPE_API_KEY` 已 setx；手B 已验证视觉能力；分镜分析零现成代码 |
| 视频下载 bilibili | ✅ 无需登录直下 | cn-scraper `bilibili_search` 已返回真实 url |
| 视频下载 douyin/xhs | ✅ 需 cookie，已验证 | `dy_transcribe.py` CDP `:9222` 抓媒体流法实测 12 条全通 |
| ffmpeg 抽音轨/抽帧 | ✅ 已内嵌 | `imageio_ffmpeg` 自带二进制，无系统依赖 |

**结论：ASR 是复用已验证件，一两小时；视觉是新写一个抽帧+视觉工具，功能态可行但成本高；下载是复用已验证件。**

---

## 二、架构总览

### 核心原则（与用户拍板锁定）

1. **内置接口，不内置模型**：voice-dna 加 `transcribe()` / `video_vision()` / `download_video()` 三个 tool，后端抽象。funasr 模型不进 repo，声明为可选依赖。
2. **本地 funasr 默认，云端 DashScope 可选**（实测翻转"云端默认"：本地已验证且免费）。
3. **视频摄入 = 后置增强，不进主管线**。trend_hunter 顺手记代表性视频 url，主流程照旧纯文本一次跑完。
4. **跑完询问，不中断**：END 后调用层问「候选视频 N 个，转录哪个？」，中途零打断。
5. **v2 回流**：转录逐字稿作新素材，二次跑带素材，data_analyst 出 v1 vs v2 结构化对照。
6. **视觉功能态**：抽帧 + Qwen-VL 描述 → 分镜节奏风格卡，默认关（成本门）。

### 素材统一（关键洞察）

trace-gate 编造 HALT 的根因 = script_writer 拿不到可溯源素材。视频转录逐字稿 **就是** 缺的那块素材。两者合并成一个改动：

```
可溯源素材 = trends（标题） + samples（用户样本） + transcripts（转录逐字稿，可选）
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
    style_mimic             script_writer
  （学真实口播风格）      （基于素材写，不编造）
```

**P5-A（trace-gate 修）是 P5-E（视频回流）的同一根**，先落 A 再落 E，后者是大号版。

### 数据流

```
主流程（不变，纯文本）:
  trend_hunter → topic_planner → style_mimic → script_writer → [门] → publish → analyst → [门] → END
        │
        └─ 顺手记 candidate_videos（代表性视频 url 快照）

后置增强（END 后，调用层驱动）:
  询问「转录哪个视频？」→ 下载 → 抽音轨 → ASR → transcripts
      → 二次跑（带 transcripts 素材）→ style_mimic'/script_writer' → publish'/analyst'
      → data_analyst 出 v1 vs v2 对照（变化/更好/被验证/未变）

甩链接模式:
  用户给视频链接 → download_video → transcribe → 同回流
```

---

## 三、任务分解

### P5-A 素材喂入 script_writer（trace-gate 修，小）

`script_writer` 现在只拿 `style_card`，LLM 自由编造被溯源门拦。改：

1. `graph.py:68` `script_writer_node` 补传 `trends`/`samples`/`account_profile`。
2. `script_writer.py`：`run()` 收 `trends`/`samples`/`profile`；`SCRIPT_PROMPT_TEMPLATE` 加「可溯源素材」段；`_llm_script` 签名扩参。
3. `mcp_server.py:_script_writer` 补参数（同 `_topic_planner` analytics 那次）。

**验收-工程**：`test_script_writer.py` 加「喂素材后 LLM 输出含素材词」「缺素材时 prompt 无素材段」两测；`test_graph.py` 加「script_writer_node 转发素材」。全量 pytest 绿。

### P5-B transcribe 工具（ASR，核心）

新文件 `src/tools/transcribe.py`，`run(**kwargs) -> dict`：

```
transcribe(source: str, backend: str = "local") -> {"text": str, "source": str, "backend": str}
```

- `source` = 视频 url 或本地音/视频文件绝对路径。
- 内部链路：url → `download_video` 落盘；视频后缀 → ffmpeg 抽 16k 单声道 wav；→ ASR。
- 后端抽象（懒，两函数）：
  - `_asr_local(wav)`：`httpx.post("http://127.0.0.1:8000/v1/audio/transcriptions", files=...)`（复用 `dy_transcribe.py` 已验证调用）。
  - `_asr_cloud(wav)`：DashScope 流式，**P5-B 只留 stub 抛 `NotImplementedError`**，P5-F 可选接。
- `mcp_server.py` 注册 `transcribe`；`mcp_guard` 白名单动作分类加 `read`（无副作用，只读音频）。
- 铁律：临时 wav/m4a 落 `tempfile`，用完删；key/cookie 不落盘。

**验收-工程**：`test_transcribe.py` — 抽音轨命令正确（monkeypatch ffmpeg）、本地/云端后端分派、url vs 本地路径分支、后端缺省回落。全量绿。

**验收-功能**：本地 `transcribe("test_speech.wav")` 回非空文本（实测基准：funasr 回「你好世界」类）。

### P5-C download_video 工具（下载）

新文件 `src/tools/video_download.py`，`run(url) -> {"path": str}`：

- bilibili：直下（无登录）。
- douyin/xhs：复用 `dy_transcribe.py` 的 CDP `:9222` 抓媒体流法（需本机已登录 Chrome），或指引用户贴 cookie（cookie 落 `~/.voice-dna/cookies.json`）。
- 下载落 `tempfile` 临时目录，不落 repo。

**验收-工程**：`test_video_download.py` — url 平台分派（bilibili vs douyin 走不同函数）、cookie 只落指定路径。全量绿。

**验收-功能**：bilibili 真实 url 下载成功落盘（文件非空）。

### P5-D video_vision 工具（视觉分镜，功能态）

新文件 `src/tools/video_vision.py`，`run(path, fps=1/3) -> dict`：

- ffmpeg 按 `fps` 抽帧（默认 1 帧/3s）。
- 逐帧 Qwen-VL-Max（`DASHSCOPE_API_KEY`）描述画面/景别/转场。
- 汇总成「分镜节奏风格卡」`{"shot_rhythm": str, "visual_style": str, "scenes": [...]}`。
- 默认关（成本门：`VOICEDNA_VISION=0` 时 run 直接回空），功能态低帧率。
- 铁律：`DASHSCOPE_API_KEY` 只 env。

**验收-工程**：`test_video_vision.py` — 抽帧命令（monkeypatch）、`VOICEDNA_VISION=0` 短路、逐帧调用聚合。全量绿。

**验收-功能**：本地短视频抽 3 帧 + 视觉描述返回非空（有 key 时）；无 key 时优雅回空不崩。

### P5-E 后置增强 + v2 回流（串联）

1. `schemas.py` 加状态字段：
   ```python
   candidate_videos: list[dict]  # [{title, platform, url, heat}]
   transcripts: dict[str, str]   # {video_url: text}
   video_visual: dict[str, Any]  # 视觉分镜卡（可选）
   ```
2. `trend_hunter.py`：抓完记代表性视频（最高热度 1-3 条、platform 为视频平台）入 `candidate_videos`。
3. `graph.py`：`style_mimic_node` / `script_writer_node` 转发 `transcripts`（并入可溯源素材）。
4. `app.py`（chainlit）：`_run_pipeline` 跑完 END 后，若 `candidate_videos` 非空，用 `cl.AskActionMessage` / actions 问「转录哪个视频？（跳过/全部/指定）」；用户选 → 逐条 `transcribe` → `transcripts` 入 state → 二次跑。
5. v2 回流：调用层用 v1 state + transcripts **二次 ainvoke**（复用 graph 调度 + 质量门；trend_hunter/topic_planner 结果复用 v1，不重抓）。data_analyst 出 v1 vs v2 对照。

**验收-工程**：`test_schemas.py`（新字段类型）、`test_trend_hunter.py`（candidate_videos 记代表性）、`test_graph.py`（transcripts 转发）。全量绿。

**验收-功能**：bilibili 真数据跑完 → 候选视频非空 → 转录 → v2 脚本与 v1 不同且含转录内容词 → data_analyst report 含 v1/v2 对照段。

### P5-F 云端 ASR 后端接线（可选，最后）

`_asr_cloud` 接 DashScope callback 流式（`Recognition` + `RecognitionCallback`，已验证 API 签名）。默认仍 local，`backend="cloud"` 显式切。

**验收-功能**：`transcribe(..., backend="cloud")` 回非空文本（填 `DASHSCOPE_API_KEY`）。

---

## 四、验收标准（工程 + 功能）

### 工程验收（每条可跑可证）

| # | 标准 | 验证 |
|---|------|------|
| E1 | TDD：每个新 tool / 改动有先失败再通过的测试 | 看测试 commit 顺序 |
| E2 | 全量 pytest 绿（当前 169，P5 后 ≥ 200） | `pytest -q` |
| E3 | ruff / mypy 零告警 | `ruff check src tests` / `mypy src` |
| E4 | 无孤儿 import/变量/函数（新增改动引入的） | `ruff` 未使用项 |
| E5 | 铁律：key 只 os.environ、cookie 只 `~/.voice-dna/cookies.json`、临时音视频落 tempfile 用完删 | 读代码 + grep 确认无明文 key / 无 cookie 落 DB |
| E6 | 三个新 tool 进 `mcp_server` + `mcp_guard` 动作分类正确 | `test_mcp_client.py` / `test_guard.py` |
| E7 | 文档：HANDOFF-P5-*.md 带 `unverified_assumptions` | 交接文件存在 |

### 功能验收（真数据，非 mock）

| # | 标准 | 验证 |
|---|------|------|
| F1 | trace-gate 修后，LLM full 档 script 不编造（溯源门 PASS） | 全图 E2E 到 END（非 human_gate） |
| F2 | bilibili 真数据 → candidate_videos 非空 | 全图 E2E |
| F3 | 转录后 v2 脚本含转录内容词、与 v1 有差异 | 全图 E2E 对照 |
| F4 | data_analyst report 含 v1 vs v2 结构化对照（变化/更好/被验证/未变） | 读 report |
| F5 | 甩链接：bilibili 直下 + 转录回非空 | 手动或脚本 |
| F6 | 无 key / 无 funasr / 无 DashScope 时优雅降级（不崩、明确提示） | 关后端测 |
| F7 | 视觉功能态：有 key 回分镜卡，`VOICEDNA_VISION=0` 短路回空 | 开关测 |

---

## 五、风险 + 待定决策点

| 项 | 风险 / 决策 | 默认 |
|----|------------|------|
| 云端 ASR 未接 | P5-F 才接，P5-B 只留 stub | 本地默认，不阻塞 |
| 视觉成本 | 逐帧 Qwen-VL 贵 | 功能态低帧率 + `VOICEDNA_VISION` 门，默认关 |
| douyin/xhs 下载 | 需本机登录 Chrome（CDP）或 cookie | bilibili 先行，douyin/xhs 复用已验证 CDP 法 |
| v2 回流二次 ainvoke | trend_hunter 重抓会慢/变化 | 复用 v1 trends（不重抓），只重跑 style→script→publish→analyst |
| transcript 大小 | 长视频逐字稿大 | 只喂代表性视频（1-3 条），截断超长 |
| 铁律新增 | 转录逐字稿本身可溯源（非编造），下载临时文件不落 repo | tempfile |

---

## 六、执行顺序

```
P5-A 素材喂入（小，解决 trace-gate）→ P5-B transcribe → P5-C download
  → P5-E 后置增强+v2（串联 B/C）→ P5-D video_vision（功能态，可并行）
  → P5-F 云端 ASR（可选，最后）→ P5-G 全仓 lint/mypy 清理（收尾）
```

每个 phase：TDD 红→绿→refactor，全量 pytest 绿后才进下一 phase；P5-E 完成后跑 F1-F5 真数据 E2E。

P5-G 收尾清理范围（P5-B 摸底，非本阶段引入；前置各 phase 只保「触及文件干净」）：
- `ruff check src tests`：26 告警 — BLE001×10 + S110×4 + S112 + PLW0602 等刻意降级
  ~16 条加 `# noqa` 或重构；SIM117/I001/UP037/PLC0206 ~7 条 `--fix`；TRY002/PYI034 逐条判。
- `mypy web_server.py app.py`：13 告警（根目录文件，`mypy src` 不覆盖）。

---

## 七、进度管理（真相源）

> 项目级进度 = 下表 + 每 phase 一个 `HANDOFF-P5-<阶段>.md`（完成度 / 未完成项 / 下阶段入口 / 测试证据 / unverified_assumptions）。不靠会话记忆。会话上下文预算 = 1M token，一个 phase 装一个预算单元，超出落交接压上下文。

| 阶段 | 完成 | 交接文档 |
|------|------|---------|
| P5-A 素材喂入 script_writer（trace-gate 修） | ✅ | HANDOFF-P5-A.md |
| P5-B transcribe 工具（ASR） | ✅ | HANDOFF-P5-B.md |
| P5-C download_video 工具 | ✅ | HANDOFF-P5-C.md |
| P5-D video_vision 工具（功能态） | ✅ | HANDOFF-P5-D.md |
| P5-E 后置增强 + v2 回流 | ✅ | HANDOFF-P5-E.md |
| P5-F 云端 ASR 接线（可选） | ✅ | HANDOFF-P5-F.md |
| P5-G 全仓 lint/mypy 清理（收尾，E3 达标） | ✅ | HANDOFF-P5-G.md |

- F1 溯源门修复（P5-E 遗留卡点）：✅ 见 `HANDOFF-P5-F1.md`（script_writer 约束 + judge
  宽容度，210 绿，注入热点 gate PASS；真数据全图 E2E 已于 2026-10-19 bilibili 源恢复后
  复现，到 END 非 human_gate，script 可溯源零硬编造）。
- F5 甩链接真实链（下载+转录）：✅ 见 `HANDOFF-P5-F5.md`（BV1LEJ96bE7c 下载
  29,226,098 bytes + funasr local 转录 755 字中文，绕开搜索 412）。F1 完整 E2E 与
  P5-D 视觉抽帧的前置，已通。
- F2/F3/F4 v2 回流全图 E2E：✅ 见 `HANDOFF-P5-F34.md`（真数据 BV16n4y1R7e1 新闻口播
  150s → 719 字转录 → v2 脚本 grounded+changed、verdict「更好」、到 END 非 human_gate）。
  F2 由 F1 真数据全图 E2E 一并覆盖（bilibili 真数据 candidate_videos 非空）。
- F5/F6/F7 交互接线（甩链接进 chat + web_server v2 回流 + video_vision 真实现）：✅
  见 `HANDOFF-P5-UI.md`（`is_video_url` + chainlit 甩链接/视觉 + `/api/v2` + 前端「转录并
  v2 回流」按钮 + video_vision `qwen3-vl-plus` 实跑 6 帧非空分镜卡，221 绿）。

- 交接规范：每 phase 结束写 handoff，下单元读 handoff 续，不重读历史；handoff 固定带 `unverified_assumptions` 一节，防把未验证当已做。
- 本方案定稿交接（P5 开工前状态）：见 `HANDOFF-P5.md`。
