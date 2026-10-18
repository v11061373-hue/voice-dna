# voice-dna（表达基因）

多 Agent 社媒内容生成管线：从热点捕捉到成片脚本，接真实数据源，内置安全网关 + 质量门 + LLM-judge 防幻觉，并支持视频转录素材二次回流生成 v2 版本。

## 为什么做

LLM 写社媒脚本最痛的是「编造」——没有可溯源素材，模型会瞎编具体数字/品牌/型号。voice-dna 用两条腿压住它：

1. **接真实数据源**：bilibili/YouTube/抖音/微博 + 搜索召回，把真实热点喂给 LLM。
2. **可溯源素材回流**：把热点视频转录成逐字稿，作为「有据可依」的素材喂回脚本写作，v1 vs v2 结构化对照。

## 架构

```
输入(画像) ──► 6 个专家 Agent（LangGraph 编排）
                 trend_hunter → topic_planner → style_mimic → script_writer
                   → [质量门] → publish_optimizer → data_analyst → [质量门] → END
                          │
                          └─ 五门安全网关（G1 白名单 / G2 动作 / G3 风险 / G4 预算 / G5 审计）
                          └─ 五门质量门（schema / 非空长度 / 溯源 / 赛道相关 / 合规）

后置增强（END 后）：
  候选视频 → 下载 → 抽音轨 → ASR 转录 → 二次跑 v2_app → v1 vs v2 对照
  甩链接 → download → transcribe → vision 分镜卡 → 直接生成脚本
```

每个 Agent 走「确定性主路径 + LLM 补充 + LLM 兜底」三段式：主路径免费、快、不幻觉；LLM 只在无 baseline 时兜底，编造内容被溯源门（LLM-judge）HALT 拦截。

## 能力清单

- **多供应商切换**：DeepSeek / 通义 Qwen / 智谱 GLM / Kimi / 腾讯混元 / OpenAI 兼容，下拉即切；LLM-judge 独立 provider 解耦。key 只落内存不落盘。
- **数据源接入**：bilibili/YouTube 免登录，抖音/微博 cookie（手动贴 + playwright 自动扫码），baidu/bing 检索源关键词召回，`heat×时间衰减` 排序 + 相似度去重。
- **视频摄入**：ASR 转录（funasr 本地 / DashScope 云端）、视频下载（bilibili 直下 / douyin·xhs cookie）、Qwen-VL 视觉分镜卡。
- **数据回流**：转录逐字稿作可溯源素材，二次跑生成 v2，data_analyst 出 v1 vs v2 对照（变化/更好/被验证/未变）。
- **对话记忆**：LangGraph Sqlite checkpointer 按 thread 持久化会话状态，支持中断/恢复/逐步执行。
- **双前端**：chainlit 对话式 + FastAPI 逐步执行，数据源 chip 栏 + 个人账号面板。

## 技术栈

Python · LangGraph · FastMCP · FastAPI · chainlit · funasr（SenseVoiceSmall）· Qwen-VL（qwen3-vl-plus）· DeepSeek/Qwen/GLM/Kimi/混元 · SQLite

## 质量

- 221 测试全绿（TDD 红→绿）
- `ruff` 0 告警 / `mypy` 0 告警（29 源文件）
- 真数据 E2E：视频下载 29MB → funasr 转录 755 字 → v2 回流 verdict「更好」
- key/cookie 铁律：只落 env / `~/.voice-dna/cookies.json`，全库无明文落盘

## 目录

- `src/tools/` — 6 专家 Agent + transcribe/video_download/video_vision 工具
- `src/orchestrator/` — LangGraph 图 + 质量门 + LLM-judge
- `src/mcp_guard/` — 五门安全网关
- `web_server.py` + `static/` — FastAPI 逐步执行前端
- `app.py` — chainlit 对话前端
- `PLAN-P4.md` / `PLAN-P5.md` + `HANDOFF-*.md` — 设计与交付文档
