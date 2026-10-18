# 简历项目经历 — voice-dna（表达基因）

> 目标岗位：AI 应用开发工程师 / 前向部署工程师（FDE）
> 全部数字来自仓库实测（221 测试全绿 / ruff·mypy 0 告警 / 真实数据 E2E），可直接引用。

---

## voice-dna — 多 Agent 社媒内容生成与视频素材回流系统

**个人项目 · 独立完成 · 2026**

**一句话**：LangGraph 编排 6 个专家 Agent 的社媒内容生成管线，接真实数据源 + 五门安全网关 + 五门质量门 + LLM-judge 防幻觉，端到端从热点捕捉到成片脚本，并支持视频转录素材二次回流生成 v2 版本。

**技术栈**：Python / LangGraph（状态图编排 + 中断恢复）/ FastMCP（工具网关）/ FastAPI / chainlit / funasr（ASR）/ Qwen-VL（视觉）/ DeepSeek·Qwen·GLM·Kimi·混元（多供应商）

**核心工作**：

- **多 Agent 编排**：6 个专家 Agent（热点捕捉 / 选题策划 / 风格模仿 / 脚本写作 / 发布优化 / 数据分析）+ Concierge 对话向导 + LLM-judge，三段式架构「确定性主路径 + LLM 补充 + LLM 兜底」，主路径免费不幻觉、LLM 只在无 baseline 时兜底。
- **质量与安全双门禁**：自研五门安全网关（工具白名单 / 动作 / 风险 / 预算 / 审计 HMAC）+ 五门质量门（schema 硬门 / 非空长度 / 溯源门判编造 / 赛道相关 / 合规词表），LLM 编造内容被溯源门 HALT 拦截走人工介入。
- **多模型供应商切换**：通用 OpenAI 兼容 client 抽象，6 家供应商（DeepSeek/Qwen/GLM/Kimi/混元/自定义）下拉即切，LLM-judge 独立 provider 解耦；key 只落内存不落盘。
- **数据源接入**：bilibili/YouTube 免登录直采 + 抖音/微博 cookie 登录（手动贴 + playwright 自动扫码）+ baidu/bing 检索源关键词召回，`heat×时间衰减` 排序 + 相似度去重。
- **视频摄入与数据回流**：ASR 转录（本地 funasr + 云端 DashScope）+ 视频下载 + Qwen-VL 视觉分镜卡；转录逐字稿作为可溯源素材二次跑 v2，出 v1 vs v2 结构化对照（真实数据：29MB 视频转录 755 字、v2 脚本「更好」）。
- **前端交互**：chainlit 对话式 + FastAPI 逐步执行双前端，数据源 chip 栏、个人账号面板、会话状态持久化（LangGraph Sqlite checkpointer）。
- **工程质量**：TDD 全程 221 测试全绿，ruff/mypy 0 告警，真数据端到端验证（非 mock）。

**可量化成果**：

| 指标 | 值 |
|------|-----|
| 测试用例 | 221 全绿（TDD 红→绿） |
| 专家 Agent | 8（6 专家 + Concierge + LLM-judge） |
| 安全/质量门 | 5 + 5 |
| LLM 供应商 | 6 家预设 |
| 数据源 | 6 平台（2 keyless + 2 cookie + 2 检索） |
| lint / mypy | 0 告警（ruff 25→0，mypy 17→0） |
| 真数据 E2E | 视频下载 29MB → 转录 755 字 → v2 回流 verdict「更好」 |
