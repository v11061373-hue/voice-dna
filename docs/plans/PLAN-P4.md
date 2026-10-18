# P4 方案 — 专家 Agent + 五门网关 + 数据源可选用

> 状态：可行性方案 + 任务分解（待批准后执行）
> 最后更新：2026-10-19
> 前置：P0–P3 完成（66 测试通过）

## 一、可行性结论（哪些做 / 哪些拆 / 哪些缓）

| 改动 | 判定 | 说明 |
|------|------|------|
| 路1 数据源扩展（关键词召回 + 选用 + 登录指引） | ✅ 做，分 V1/V2 | V1 手动贴 cookie；V2 自动扫码抓 cookie（browser-use） |
| 五门网关 G1–G5 | ✅ 做，复制 bidforge-v4 | 源码在 `bidforge-v4/src/mcp_guard/`，复制适配即可 |
| 6 agent 全改 LLM | ✅ 做，但「主路径 + LLM 兜底」，非 LLM 自由选工具 | 见 §二 架构 |
| 个人账号 = 供应商 + key | ✅ 做，小 | 抽象 provider 配置 |
| 设置面板 | 🔸 缓，仅留可行性 | 见 §七 |

**核心结论：可扩展性的根因是数据源写死 + 无关键词召回，不是「agent 不会调工具」。** 先做数据扩展（路1），自由工具调用（ReAct）等五门网关 + LLM-judge 稳了再评估。6 个 agent 全 LLM 化，但 LLM 只做「补充 + 兜底」，主路径仍是确定性流程。

---

## 二、架构总览：LLM 在哪里用、怎么用

关键问题不是「用不用 LLM」，是「LLM 在主路径的哪个位置」。定死如下三层：

```
                    ┌─────────────────────────────────────────┐
  输入(profile)      │           专家 Agent（6 个）            │
  ──────────►       │                                         │
                    │  ① 主路径（确定性，免费，不幻觉）          │
                    │     scraper / 打分规则 / 词表 → baseline │
                    │                                         │
                    │  ② LLM 补充（专家 persona + prompt）      │
                    │     有 baseline → 润色/补理由/提炼洞察    │
                    │     无 baseline → LLM 兜底生成           │
                    │        （打「LLM兜底」标签，供溯源门查）   │
                    │                                         │
                    │  ③ 门禁（质量门，见 §五 C3）               │
                    └─────────────────────────────────────────┘
                                   │
                                   ▼
               质量门（schema/溯源/合规 5 门 + LLM-judge）→ 放行/退回
```

- **LLM 不替代主路径，只做补充 + 兜底。** baseline 免费、快、不幻觉；LLM 只在补充时调，成本可控。
- **幻觉靠「溯源门」压**：LLM 兜底内容必须能溯源到输入（热点/样本/关键词），编造即 HALT。
- **插件为何有用**：检索型数据源喂 LLM 真实素材，减少兜底编造；数据源越多，LLM 补充越有据可依。
- **两层门，别混**：工具调用过「安全网关 G1–G5」（§四，管能不能调）；产出内容过「质量门」（§五 C3，管产出行不行）。

---

## 三、P4-A 数据源层（热点捕捉 bug + 选用 + 登录）

### A1 数据源注册表：声明能力

`plugins/sources.json` 从「URL 契约」扩成「能力声明」：

```json
{
  "bilibili": {"kind": "scraper", "requires_auth": false},
  "douyin":   {"kind": "scraper", "requires_auth": true,  "auth": "cookie", "auth_hint": "登录抖音后从浏览器复制 cookie"},
  "weibo":    {"kind": "scraper", "requires_auth": true,  "auth": "cookie", "auth_hint": "..."},
  "dailyhot": {"kind": "http",   "url": "http://.../hot", "requires_auth": false}
}
```

- `requires_auth` / `auth` / `auth_hint` 三个新字段，前端据此渲染「已登录 / 未登录」。
- 内置 B站/YouTube 声明 `requires_auth:false`；抖音/微博声明 `requires_auth:true`。

### A2 数据源选用 UI（chip 栏，常驻明显位置）

数据源是任务的地基，放**对话框正上方一条常驻 chip 栏**（不藏进侧栏）。每个数据源一个小椭圆 pill：

- **亮**（accent 描边/填充）= 启用，trend_hunter 跑它。
- **暗**（灰）= 禁用。
- 点一下切换亮/暗。默认亮：B站 + YouTube；抖音/微博暗（需登录，点亮触发 §A4 指引）。
- 选中集合存 localStorage（会话级，不进 DB）。trend_hunter 只跑亮起的平台。
- 检索源（baidu-search / bing-cn）作为「🔍 搜索召回」单独一个 chip：亮 = 关键词召回走搜索引擎，暗 = 只从榜单源过滤。默认亮（A3 召回依赖它）。

**验收-功能**：chip 栏点「抖音 + B站」亮起后跑全流程，trends 只含这两个平台，不含 YouTube；再点暗抖音重跑，trends 无抖音项。

### A3 关键词召回（修 bug）

`trend_hunter.run` 现在忽略 `profile`。改：

1. 从 profile 生成赛道关键词（LLM 抽取，缓存；无 key 用内置词表兜底）。
2. 检索型源（baidu-search / bing-cn）按关键词召回，榜单源（dailyhot/B站）全量拉回后按关键词过滤。
   - 检索源接法已定 **stdio**（非 httpx 直抓）：`npx -y baidu-search-mcp` / `npx -y bing-cn-mcp`，登记进 `plugins/mcp_servers.json`，复用 `mcp_client` 现成 StdioTransport。无 key、无自写爬虫、无反爬重实现。
   - 接线：trend_hunter 加一条「检索分支」，经 `mcp_client.call_tool("baidu-search.<tool>", ...)` 调检索源；榜单源仍走现有 scraper 分派（`load_plugins`）。两条支路合并后统一过关键词过滤 + 排序。
3. 排序：`heat × 时间衰减`（`TrendItem` 加 `time` 字段）。
4. 去重：标题相似度归组，同类保留最高热度一条（不 embedding）。

**验收-功能**：profile「美妆博主」跑 trend_hunter，产出里每条都命中美妆/护肤/彩妆类关键词，且按热度降序；近似标题不重复。
**验收-工程**：`TrendItem` 加 `time` 字段，`run()` 单测覆盖「关键词过滤」「时间热度排序」「去重」三例。

### A4 登录态 + 指引（V1 手动 / V2 自动）

**核心逻辑：项目只识别 cookie 通没通，两种登录方式都做。**

统一入口 = cookie 状态检测（scraper `requires_auth:true` 时先 probe 一次：用本地 cookie 试抓，命中风控/登录页 = 未通，取到数据 = 已通）：

- **未接通** → 前端在对话流弹「登录指引」+ 两个选项：
  - **手动贴**（V1）：auth_hint 指引 + 粘贴框，用户从浏览器复制 cookie 贴入 → 存本地文件（`~/.voice-dna/cookies.json`，不进 DB，不落 key 到库）。
  - **自动跳转扫码**（V2）：browser-use 自动开 Chrome 跳登录页 → 扫码 → 抓 cookie → 存本地；检测无 Chrome → 明确反馈「需安装 Chrome」。
- **已接通** → 直接跑任务，不再提示。

V1 + V2 都要，V2 依赖 playwright、有反爬风险，作为 V1 之后增强；两者共享同一个「cookie 状态检测 → 存本地 → 重跑」出口。

**LLM 辅助回答（贯穿）**：登录指引用「auth_hint（确定性主路径）+ LLM 补充」（自然语言解释「去哪个页面、点哪里、复制哪段」），优先 auth_hint，LLM 兜底润色。

**验收-功能**：勾「抖音」且 cookie 未通 → 展示指引 + 手动贴/自动扫码两选项；贴入 cookie 后重跑不再提示。V2 未装 Chrome → 明确反馈「需安装 Chrome」而非报错。cookie 已通 → 直接跑任务。
**验收-工程**：cookie 只落本地文件/内存，`grep` 全库无 cookie 明文入 sessions.db / checkpoints.db。

---

## 四、P4-B 安全网关 G1–G5（复制 bidforge-v4）

源码在 `bidforge-v4/src/mcp_guard/gateway.py` + `guard.py`（已确认存在）。复制到 `voice-dna-repo/src/mcp_guard/`，适配 6 tool + 外部 server。

| 门 | 作用（voice-dna 适配） |
|----|----------------------|
| G1 工具门 | 白名单 = 6 本地 tool + 已注册外部 `server.tool`；未知 tool 拒绝 |
| G2 动作门 | `read`（trend_hunter/topic_planner 读）/ `draft`（style/script/publish/analyst 产出）/ `external_write`（发帖、写文件，预留） |
| G3 风险门 | `external_write` 需人工批准；`read`/`draft` 自动放行 |
| G4 预算门 | 成本（token/调用数）+ 时间（超时）+ 重试（上限）+ 限流（沿用 BidForge 滑动窗口） |
| G5 审计门 | 请求/响应/批准 JSONL 留痕 + HMAC |

> 差异点：BidForge 的 G4 只做了限流；本次把「成本/时间/重试」并入 G4（LLM 化后这是压成本 + 防失控的关键）。

**验收-工程**：复制后 `pytest` 覆盖「白名单拒绝 / read·draft 放行 / external_write 需批准 / 预算超限拒绝 / 审计落盘」五例；`ruff` / `mypy` 通过。
**验收-功能**：单 agent 调一个未注册的 `server.tool`，返回「G1 拒绝」而非崩。

---

## 五、P4-C 6 个 agent LLM 化（主路径 + LLM 兜底）

### C0 LLM 参与度控制（三级全局档 + 每 agent 开关）

纠结点「LLM 参与度多高」用两级定死：

1. **全局档位**（设置里）：`确定性` / `兜底（默认）` / `全开`。
2. **每 agent 布尔开关**（亮=该 agent 允许调 LLM，暗=纯确定性，默认全亮）。

三档语义（仅对开关亮起的 agent 生效）：
- `确定性`：无视开关，全流程走主路径，零 LLM（style_mimic 走降级卡）。
- `兜底`（默认）：主路径先跑，无 baseline 才调 LLM 补充（§二 架构）。
- `全开`：每步都调 LLM，成本最高、幻觉风险最高，靠五门压。

覆盖三种场景：只在风格调 LLM = 全局「确定性」+ 单独亮 style_mimic；全流程 LLM = 全局「全开」；省成本默认 = 全局「兜底」。

### C1 专家 persona

每 agent 一个专家身份 + system prompt（role/goal/backstory，参照 BidForge 6 agent 结构）。persona 存 `src/agents/*.md` 或模块常量。

### C2 每个 agent 统一三段式（§二 架构）

| agent | 主路径（确定性） | LLM 补充 | 门禁 |
|-------|-----------------|----------|------|
| trend_hunter | scraper 召回 + 关键词过滤 | 无（关键词抽取走 A3，输入侧辅助） | 赛道相关门 |
| topic_planner | 4 因子打分 | LLM 写选题理由 + 洞察 | schema 门 |
| style_mimic | 词表降级卡 | LLM 抽风格卡（已有） | 7 字段 schema 门 |
| script_writer | 模板填充 | LLM 写脚本 body | 非空+长度门 |
| publish_optimizer | 规则时间表 | LLM 优化标题/标签 | schema 门 |
| data_analyst | 统计（IQR） | LLM 写结论 | 非空门 |

### C3 LLM-judge 结构化评分质量门

`quality_gate.py` 扩到 5 门（3 确定性 + 2 LLM-judge）：

1. **schema 硬门**（确定性）：字段必填 + 类型，最强第一道。
2. **非空+长度门**（确定性）：已有腿①，补阈值。
3. **溯源门**（LLM-judge）：产出里的热点/数据必须能溯源到输入，编造 HALT。
4. **赛道相关门**（LLM-judge）：产出语义命中 profile（词表只粗筛，语义相关交 judge），跑题 HALT。
5. **合规门**（确定性词表）：广告法违禁词/虚假宣传词。

每 agent 的必填字段 schema 存 `src/schemas.py`（`SocialMediaState` 已有六步产物字段，补每 agent 独立 output schema 常量），schema 硬门读它。

LLM-judge = 第三方模型（可配 provider，与主 LLM 解耦），结构化打分 `{score, pass, reason}`，阈值放行/退回重做。

**验收-工程**：`quality_gate.py` 5 门全挂，`pytest` 覆盖「schema 缺字段 HALT / 编造热点溯源门 HALT / 违禁词 HALT / 正常产出 PASS」。
**验收-功能**：跑「美妆博主」全流程，产出过 5 门后到 END；人为注入一条编造热点，溯源门 HALT 走 human_gate。

### C4 对话辅助 agent（Concierge，只读向导 + 启动判意）

定位：**答疑 + 指引 + 启动判意，不评判、不参与调度。** 三个角色互斥：

**放置**：常驻主对话栏（输入栏），自由格式输入，默认对话对象。pipeline 产出渲染在同一对话流，随时切回 Concierge 问。

| 角色 | 是什么 | 职责 |
|------|--------|------|
| Orchestrator | LangGraph 图（非 LLM，确定性） | 调度 6 agent |
| LLM-judge | 质量门 | 评判产出，放行/退回 |
| Concierge | 只读 LLM + 唯一动作 | 答疑 + 指引 + 启动判意 |

**权限 = 只读 + 一个动作**：G1 白名单 = 只读 tool（get_state / list_sources / cookie 状态）+ 唯一动作 `start_pipeline(profile)`。白名单不含任意 run/write/发帖。

**启动判意**：自由格式输入由 Concierge 判意——明确「启动」→ 直接触发 pipeline；不确定 → 问「要启动吗？」→ 用户确认才启动。这是它唯一的「动作」，不是自由工具调用（pipeline 内部仍由 Orchestrator 确定性调度）。

**能做**：答疑「为什么卡住 / 下一步干嘛」；登录与数据源接入指引（auth_hint 主路径 + LLM 润色）；解释产物；识别启动意图并触发 pipeline（唯一动作，不确定先确认）。

**不做**：调任意工具、改 state、写文件、发帖、参与 pipeline 内部调度。

**谁约束它**：同一个 G1–G5 网关，白名单更窄（只读 + 单动作）。幻觉压两处：① G1 白名单硬约束（想调 run 直接拒，比 prompt 强）；② 回答锚定真实 state，不锚定的部分明确说「不知道」。启动误判靠「不确定先确认」兜底。

---

## 六、P4-D 个人账号（供应商 + key）

- `/api/config` GET/POST：provider、base_url、model、key。供应商做成下拉预设（全 OpenAI 兼容，加一个 = 一行，零成本）：DeepSeek / 通义 Qwen / 智谱 GLM / Kimi / 腾讯混元 / OpenAI 兼容（自定义 base_url + model）。
- key 只落 `os.environ`（内存，重启失效），不落盘不落库（沿用 key 铁律）。
- style_mimic 的 `_call_deepseek` 抽成 `src/llm.py`（通用 OpenAI 兼容 client），6 agent 共用。
- LLM-judge 默认复用主 provider；可选独立 provider（`/api/config` 加 judge 字段组：judge_provider/base_url/key），与主 LLM 解耦。

**验收-功能**：个人账号填 DeepSeek key → 跑 style_mimic 真调 LLM（非降级卡）；填 Qwen key + base_url → 同样可用。
**验收-工程**：`grep` 全库无 key 明文入 sessions.db / checkpoints.db；`/api/config` GET 只回「已配/未配」。

---

## 七、设置面板（可行性选项，不落地）

参照 Accio 能照搬的，按价值排：

1. 数据源默认勾选（与 A2 chip 栏联动）—— 中价值。
2. 数据源默认勾选（与 A2 联动）—— 中价值。
3. 主题深/浅 —— 低价值（用户已定「重点在交互不在颜色」）。
4. 关于（版本 + 数据源接入方法，复用 plugins/README 三条）—— 低价值，顺手。

**建议**：设置先只做「关于 + 数据源默认勾选」，其余缓（供应商已在个人账号 §六）。

---

## 八、执行顺序与依赖

```
P4-B 五门网关（复制，独立，先做）   ← 无依赖，且是 C3/自由调用的前置
   ↓
P4-A 数据源层（A1 注册表 → A2 选用 → A3 召回 → A4 登录）
   ↓
P4-D 个人账号（llm.py 抽象）        ← C3 的 LLM-judge 依赖它
   ↓
P4-C 6 agent LLM 化（C1 persona → C2 三段式 → C3 5 门）
```

- P4-B 独立可先落地，风险最低，立刻复用 bidforge-v4 资产。
- P4-A 是「修 bug + 数据扩展」本体，工作量最大。A3 关键词抽取先 ship 词表版（零 LLM），LLM 抽取随 P4-C 落地（依赖 D 的 llm.py），不阻塞 A。
- P4-C 最后，依赖 B 的门禁 + D 的 llm.py。

## 九、边界与风险

1. **抖音/微博 cookie 反爬**：V1 手动贴 cookie 仍有失效风险；V2 自动扫码依赖 playwright，可能被风控。**降级策略**：登录态源抓不到即优雅返回空（现有 ScraperException 降级已就位），不阻断其余源。
2. **6 agent 全 LLM 化成本**：G4 预算门必须先上，否则 demo 一次全流程 token 失控。
3. **检索型源接入（已定）**：baidu-search / bing-cn 用 stdio（`npx -y baidu-search-mcp` / `npx -y bing-cn-mcp`）接，复用 `mcp_client` 现有 StdioTransport，无自写爬虫。唯一成本 = 每调 spawn 一次子进程（~1–2s），trend_hunter 可接受。
4. **key/cookie 铁律**：只本地/env，永不进 DB（sessions.db / checkpoints.db）。
5. **browser-use 内置**：V2 自动扫码需浏览器自动化，作**可选依赖**内置（懒加载，仅 V2 触发时 import + 起浏览器），V1 手动贴 cookie 不依赖它。实现二选一：playwright 直写（抓 cookie 是固定步骤，无需 agent 自主决策层，更省）或复用已装 browser-use（handsA 经验）。倾向 playwright 直写。

---

## 十、工程排期与进度管理（1M 上下文预算）

本工程（P4 建设）会话上下文预算 = **1M token**，是排期单位：一个阶段的工作（读代码 + 实现 + 测试 + 验证）装进一个预算单元；超出就落交接文档压上下文、下单元续。

- **排期**：五阶段串行 B→A→D→C，每阶段再拆子任务，子任务粒度 = 一个预算单元装得下。
- **项目级进度管理**：`PLAN-P4.md` 状态行 + 每阶段一个 `HANDOFF-P4-<阶段>.md`（完成度 / 未完成项 / 下阶段入口 / 测试证据）。真相源 = 下表，不靠会话记忆。

| 阶段 | 完成 | 交接文档 |
|------|------|---------|
| P4-B 安全网关 | ☑ | HANDOFF-P4-B.md |
| P4-A 数据源层 | ☑ | HANDOFF-P4-A.md |
| P4-D 个人账号 | ☑ | HANDOFF-P4-D.md |
| P4-C 6agent LLM 化 | ☑ | HANDOFF-P4-C.md |
| P4-C4 Concierge | ☑ | HANDOFF-P4-C4.md |
| P4-E 收尾验收（端到端真 LLM 联调 + G4/G5 运行时接线） | ☑ | HANDOFF-P4-E.md |

> C4 收尾三件归位：
> - Concierge LLM 润色真联调 → **P4-E**（需真实 LLM key）
> - 判意 LLM 补充 → **P4-E 可选**（低优先；启发式 + 反问兜底已过验收，可「不做」）
> - 前端独立面板 UI → **不做/缓**（spec §五 C4「放置」只要求常驻主对话栏 + 同流渲染，已满足；独立面板非 spec 项）

- **交接规范**：参照 BidForge「会话交接」——每阶段结束写 handoff，下单元读 handoff 续，不重读历史。handoff 固定带 `unverified_assumptions` 一节（未验证的假设/待放行项），防把未验证当已做。
