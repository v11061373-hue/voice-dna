# Voice DNA 前端平台化改造计划

状态：P0+P1+P2+P3 完成（66 测试通过）· 最后更新 2026-10-18

## 目标

单页对话前端 → 市面 agent 软件形态：左边栏 + 双模式（全流程 / 单 agent）+ 会话历史（点进续跑）+ 插件（数据源 / 外部 skill = MCP tool 层）。

## 已锁定架构决策

1. 持久化：`langgraph-checkpoint-sqlite` 的 SqliteSaver 替换 InMemorySaver，原生续跑。
2. 会话历史：`sessions` 表（stdlib sqlite3）存元数据；checkpoint 存 SqliteSaver；resume = 用 thread_id 续跑。
3. 单 agent：`/api/tool` 直调 MCP tool（绕过 graph），`/api/tools` 列工具 + inputSchema。
4. 数据源插件：进程内 `plugins/scrapers/`（`Scraper.__subclasses__` 已内置）+ HTTP 契约 HttpScraper。
5. 外部 skill：MCP tool 层，`mcp_client` 从单 server → 多 server 按 tool name 路由。
6. secrets 只 env/本地不落库；不做多用户/鉴权。

## 任务

### P0 平台骨架 + 持久化（核心）

- **T0-1 依赖 + 持久 checkpoint**：加 `langgraph-checkpoint-sqlite`，`web_server` 换 SqliteSaver。
  验证：两个独立进程共用 DB，第二个进程能续跑同一 thread_id。
- **T0-2 会话存储**：`src/session_store.py`（sessions 表），`/api/sessions` list/create/delete。
  验证：pytest（建会话、列会话、删会话）。
- **T0-3 单 agent 后端**：`/api/tool`（直调 tool）+ `/api/tools`（列 6 tool + inputSchema）。
  验证：curl 直调 trend_hunter 返回热点列表。
- **T0-4 前端左栏布局**：nav + main 两栏。
- **T0-5 双模式前端**：全流程视图（现有）+ 单 agent JSON 表单视图。
- **T0-6 历史前端**：会话列表 + 点击加载历史 + 续跑。
  验证 E2E：左栏点单 agent 跑通、点历史恢复续跑。

### P1 数据源插件

- **T1-1** 进程内插件目录 + 自动发现 + 接入文档。
- **T1-2** HTTP 契约 HttpScraper（收 `{profile}` 回 `TrendItem[]`）+ 配置页。

### P2 外部 skill（MCP tool 层）

- **T2-1** `mcp_client` 多 server 路由（本地 in-memory + 外部 stdio/HTTP）。
- **T2-2** 外部 MCP server 配置 + 注册 + 前端列出外部工具。

### P3 交互页重构（参照 Accio，用户 2026-10-18 确认方向）

- **T3-1 侧栏重构**：顶部「新任务」（开新对话），中部单个 Agent，插件（数据源/外部 Skill），左下底部个人账号 + 设置（占位）。
- **T3-2 对话栏重构**：去掉单 agent 视图半屏 JSON textarea；可视化/产出进对话流（上），输入固定底部一条；单 agent 参数走底部紧凑输入。
- **T3-3 md 上传**：输入栏 📎 独立按钮，md 文本作 `samples` 前置注入 style_mimic + 全流程 prefix（已落地：graph/schema/web_server 三处贯通）。

## 不做

多用户/鉴权、key 落库、动态 JSON-schema 表单渲染（用 JSON 文本框代替）。

## 验证方式

- 后端：pytest（session_store、/api/tool 直调、多 server 路由）
- 前端：起 uvicorn + curl/浏览器手测
- E2E：start→next→auto→新会话→历史续跑
