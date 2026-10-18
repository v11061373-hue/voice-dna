# 表达基因（Voice DNA）

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-52_passed-0e9f6e)
![Lint](https://img.shields.io/badge/Lint-ruff%2Bmypy_0_err-0fa3a3)
![License](https://img.shields.io/badge/License-MIT-555)

> 表达基因提取器：从博主文案抽结构化「风格 DNA」，贯穿热点选题 → 分镜脚本 → 发布优化 → 数据报告全链路。
> 题眼是「风格模仿」（style_mimic），其余五个 agent 围绕它提取的基因卡运转。自写 LangGraph 编排 + MCP + Chainlit。

## 它解决什么

目标岗位（字节跳动 产品实习生-TikTok）看重的不是「再搭一个发布器」，而是**内容理解 → 标注标准 → Prompt 撰写 → 数据分析 → 评测规则**这一串能力。表达基因把这串能力落成一条可跑、可测、可扩展的 Agent 流水线——题眼是「风格模仿」，其余环节围绕它提取的基因卡运转：

- **内容理解** = `style_mimic`：从博主文案样本抽取结构化「表达 DNA」（7 字段风格卡）
- **标注标准 / Prompt 撰写** = 风格卡字段 + 脚本生成 prompt 模板
- **数据分析** = `data_analyst`：对比基准（四分位 / 分层桶 / 互动率）+ IQR 异常检测
- **评测规则** = 质量门（确定性规则 + 统计异常，LLM-as-judge 留口子）

## 架构

```
用户输入账号画像
      │
      ▼
trend_hunter ──► topic_planner ──► style_mimic ──► script_writer
（热点猎人）      （选题策划）        （风格模仿）       （脚本文案）
                                                        │
                                          ┌─────────────┤
                                          │  脚本质量门 │
                                          └─────┬───────┘
                                   PASS          │ HALT
                                          publish_optimizer ──► human_gate
                                          （发布优化）             （人工兜底）
                                          │
                                          │  data_analyst（数据分析）
                                          │       │
                                          │  ┌────┴─────┐
                                          │  │ 分析质量门 │
                                          │  └────┬─────┘
                                          │  PASS │ HALT
                                          END ◄───┴──► human_gate
```

## 平台支持

| 平台 | 数据源 | 状态 |
|---|---|---|
| B站 | keyless API（`/x/web-interface/popular`） | ✅ 真数据（20 条/次） |
| YouTube | `/feed/trending` 页面 `ytInitialData` | ✅ 真实现（海外网络） |
| 抖音 / 微博 | 登录态源（契约预留） | ◻️ 接登录态即产数据 |

各平台数据源高度异构，差异化抓取与解析，收敛到统一 `TrendItem` 数据接口：

- **B站**：keyless API，但请求不带浏览器 UA 会被直接 412，需伪造 UA。
- **YouTube**：抓 `/feed/trending` 页面内嵌的 `ytInitialData`，递归遍历渲染器树定位内容项（依赖海外网络，国内环境返回空）。
- **抖音 / 微博**：需登录态，缺失时返回空数据（契约预留，接登录态即产数据）。

> 加新平台只需继承 `Scraper` 并设 `name`，注册表 `_SCRAPERS` 经 `__subclasses__` 自动发现。

## 六 Agent

| Agent | 职责 | 输入 | 输出 | 来源 |
|---|---|---|---|---|
| `trend_hunter` 热点猎人 | 抓平台热点 | `account_profile` | `trends[]` | 4 平台统一 TrendItem 契约（B站/YouTube keyless） |
| `topic_planner` 选题策划 | 加权打分排序 | `trends[]` | `topics[{title,score,reason}]` | 4 因子加权（40/30/20/10） |
| `style_mimic` 风格模仿 ⭐ | 抽表达 DNA（题眼） | `profile` + `topics` | `style_card`（persona/voice/catchphrases 等 7 字段） | DeepSeek 结构化抽取，三层兜底（prompt 约束 / markdown 剥离 / 缺字段标未知），无 key 降级通用卡 |
| `script_writer` 脚本文案 | 分镜脚本 | `style_card` | `{body, scenes[], duration}` | 五段式 HOOK→CTA |
| `publish_optimizer` 发布优化 | 平台/时间/标签 | `script` | `{platform, best_time, tags...}` | 启发式规则 |
| `data_analyst` 数据分析 | 对比基准 + 异常检测 | `metrics` | `{report, metrics, benchmark, anomalies}` | IQR 1.5 异常检测（合成数据验证） |

每个 Agent 是一个 MCP tool，统一 JSON 进出，可独立替换实现、独立测试。

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 编排 | **LangGraph**（自写 StateGraph） | 7 节点 + 2 条件边 + 2 质量门 |
| 工具 | **FastMCP** | 6 tool 注册，in-memory Client 直连 |
| 前端 | **Chainlit** | `@cl.on_message` 对话流，节点映射 `cl.Step` |
| LLM | **DeepSeek**（`deepseek-chat`） | `style_mimic` 结构化抽取；无 key 自动降级 |
| 统计 | **numpy** | IQR 异常检测 / 四分位 |

## 快速开始

```bash
# 1. 装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. （可选）配置 DeepSeek，真调结构化抽取；不配则降级通用风格卡
#    Windows: set DEEPSEEK_API_KEY=sk-xxx
#    macOS/Linux: export DEEPSEEK_API_KEY=sk-xxx

# 3. 跑测试
python -m pytest -q        # 52 passed

# 4. 起前端
chainlit run app.py        # 打开 http://localhost:8000
```

前端输入账号画像（如「美妆博主」），跑六步流水线，每步中间产物可点开查看，最终结果 JSON 回显。

## 项目结构

```
.
├── app.py                      # Chainlit 前端入口（graph.ainvoke 六步）
├── requirements.txt
├── src/
│   ├── schemas.py              # SocialMediaState（六步产物 + 控制字段）
│   ├── mcp_server.py           # FastMCP server：6 tool 注册
│   ├── mcp_client.py           # in-memory Client：call_tool 统一 JSON 进出
│   ├── orchestrator/
│   │   ├── graph.py            # LangGraph 编排（7 节点 + 条件边）
│   │   └── quality_gate.py     # 质量门（确定性规则 + 统计异常）
│   └── tools/                  # 6 个 Agent tool 实现
│       ├── trend_hunter.py     # B站 API + YouTube 页面（keyless）
│       ├── topic_planner.py
│       ├── style_mimic.py      # 结构化抽取
│       ├── script_writer.py
│       ├── publish_optimizer.py
│       └── data_analyst.py     # IQR 异常检测
└── tests/                      # 52 测试（含 MCP 真接往返测试）
```

## MCP 集成

6 个工具不是直接 `import` 内部函数，而是注册在 FastMCP server 上，编排节点经 in-memory `Client` 调 `call_tool` 走完整 MCP 协议：

```python
# src/mcp_server.py — 注册
mcp = FastMCP("voice-dna")

@mcp.tool(name="style_mimic")
def _style_mimic(profile: str = "", topics=None, samples=""):
    return style_mimic.run(profile=profile, topics=topics or [], samples=samples)

# src/mcp_client.py — 调用（async）
async def call_tool(tool_name: str, **kwargs):
    async with Client(FastMCPTransport(mcp=mcp)) as client:
        result = await client.call_tool(tool_name, kwargs)
    sc = result.structured_content
    return sc["result"] if isinstance(sc, dict) and list(sc) == ["result"] else sc
```

好处：工具可独立替换、独立测试；换真实 MCP server（起 stdio 子进程）时只改 `mcp_client` 一处、签名不变。

## 质量门

两条条件边决定流水线走向：

- **脚本质量门**：`script.body` 空 → HALT 进人工兜底；正文不足 30 字符 → WARN；达标 → 继续
- **分析质量门**：`analytics.report` 空 → HALT；缺 `metrics`/`benchmark` → WARN；全有 → END

质量门取最坏结果 `HALT > WARN > PASS`。

坚持「能确定性的不用 LLM」：脚本创作走五段式模板填充、数据分析走配置降级演示序列，LLM 只集中在风格抽取这一核心环节，显著降低推理成本并提升可测性。

## 测试

```bash
python -m pytest -q
# 52 passed
```

覆盖：7 节点编排编译、六步线性跑通、MCP 真接往返、两质量门路由、6 个 tool 单元测试（含 B站 UA、YouTube ytInitialData 解析）。

## 商业落地

技术能力落地真实业务场景，验证 Agent 内容生产的商业闭环：

- 用 `style_mimic` 抽取淘宝 12 条真实标题的表达 DNA，复用变体至拼多多、闲鱼、京东等五平台，产出含标题公式、定价锚点、客服话术的网店模仿策略。
- 再次调用 DeepSeek 生成小红书 3 篇引流笔记与 6 场景评论话术，支撑副业冷启动。

## License

[MIT](LICENSE)
