# HANDOFF-P4-A — 数据源层（A1 注册表 → A2 选用 → A3 召回 → A4 登录）

状态：完成 ✅ · 2026-10-19

## 完成度

- **A1 能力声明**：`plugins/sources.json` 从 URL 契约扩为能力声明
  - bilibili / youtube：`requires_auth:false`（keyless）
  - douyin / weibo：`requires_auth:true` + `auth:"cookie"` + `auth_hint` + `login_url`
  - search：`kind:"search"` + `servers:[baidu-search/baidu_search, bing-cn/bing_search]`
  - `load_plugins()` 兼容旧字符串 URL 契约（`{平台: url}` → `{kind:http,url}`）
- **A2 选用 UI**：`static/index.html` 对话框正上方常驻 chip 栏
  - 渲染自 `/api/sources`；亮=选中 / 暗=未选；`localStorage['vd.enabledSources']` 持久化
  - 默认亮 = bilibili + youtube + search（`default_enabled = not requires_auth`）
  - 选中集通过 `/api/run {enabled:[...]}` 传入 → graph `enabled_sources` → `trend_hunter.run(enabled=...)`
- **A3 关键词召回 + 排序 + 去重**：`src/tools/trend_hunter.py` 重写
  - 修 bug：`run()` 新增 `profile` 参数，关键词过滤不再被忽略
  - 词表版关键词抽取（零 LLM，`_TRACK_KEYWORDS` 10 赛道）；未知赛道返回空不过滤
  - 板块源拉全量后按关键词过滤（标题+分类子串命中）
  - `heat × 时间衰减` 排序（半衰期 6h，`time=0` 不衰减）
  - 标题相似度去重（`difflib.SequenceMatcher` 阈值 0.85，无 embedding）
  - 检索源走 stdio `npx -y baidu-search-mcp` / `npx -y bing-cn-mcp`（`plugins/mcp_servers.json`），复用 mcp_client `StdioTransport`，归一化 list/dict/JSON-string/markdown 四种返回形状
- **A4 cookie 登录**：`src/cookies.py` + 前端统一入口
  - V1 手动贴：`POST /api/cookie` → 只落 `~/.voice-dna/cookies.json`
  - V2 自动扫码：`POST /api/cookie/scan` → playwright 懒加载（未装返回「需安装 Chrome」）
  - 统一入口 = cookie 状态检测：`doStart()` 先 `GET /api/cookie`，有 requires_auth 源缺 cookie → 弹登录引导（auth_hint + 手动贴 + 自动扫码 + 跳过），否则直接跑
- 接线：`src/schemas.py`（`enabled_sources`）、`src/orchestrator/graph.py`、`src/mcp_server.py`（`enabled` 参数）、`web_server.py`（`/api/sources` `/api/cookie` `/api/cookie/scan` + `enabled` 透传）

## 铁律核验

- cookie 只落 `~/.voice-dna/cookies.json`：grep 全仓 `cookie` 仅命中 `web_server.py` 端点签名 + `src/cookies.py` 本地文件写，无 sessions.db / checkpoints.db 写路径
- key 只 `os.environ`（内存），不落盘
- 检索型源走 stdio，无自定义爬虫
- handoff 含 `unverified_assumptions`

## 测试证据

- `pytest`：**90 passed**（73 → +17：A1 契约 2 + A3 召回/排序/去重 9 + A2 选用 3 + cookie 3）
- `mypy src/tools/trend_hunter.py src/cookies.py src/mcp_server.py src/schemas.py src/orchestrator/graph.py`：Success（5 files）
- `ruff check --fix`：修 3 处 import 排序；余 BLE001/S110（盲 except + try-except-pass）为「网络源优雅降级」刻意保留，与 `_fetch_popular` 等既有风格一致，非本阶段引入

## 未完成 / 待办

- 前端 chip 栏 / 登录引导为纯 JS，pytest 不覆盖，需手动开浏览器验 `/` 页面（chips 渲染、切换持久化、缺 cookie 弹登录、贴 cookie 后重跑）
- `web_server.py` 有 mypy 遗留（`_graph_app` Optional union、ainvoke 重载、`run_quality_gates` 参数类型），P4-B 阶段既有，本阶段未动（非新引入）
- `trend_hunter.run(enabled=...)` 已接 graph 与 web；chainlit 旧前端（`app.py`）未接 chip 栏，仍走 `platform` 单源参数

## unverified_assumptions（未验证假设，待放行）

1. **检索源真实解析未联调**：`_normalize_search_results` 对 baidu-search-mcp（markdown）/ bing-cn-mcp（JSON `results`）的解析只针对已知返回形状写，未对真实 `npx` 子进程输出跑通端到端（测试用 monkeypatch 假 `call_tool`）。需实机验证：`npx -y baidu-search-mcp` 的 `baidu_search` 与 `npx -y bing-cn-mcp` 的 `bing_search` 返回是否落进归一化分支、标题是否完整。
2. **V2 自动扫码是依赖检测 stub**：`auto_scan()` 完整扫码流程（开 Chrome → 跳登录页 → 等扫码 → 抓 cookie）未经真实浏览器/真实登录页验证，120s 轮询超时与 cookie 名白名单（sessionid/sid/passport）是拍脑袋值，需真实站点校准。
3. **关键词抽取是词表版**：PLAN §八明确「A3 先 ship 词表版（零 LLM），LLM 抽取随 P4-C 落地（依赖 D 的 llm.py）」。词表 10 赛道覆盖面窄，长尾赛道（如「穿搭」「情感」）会返回空不过滤 → 全量热点直接进选题。
4. **YouTube/B站 keyless 真实可达性**：`_fetch_popular`（B站 API 带 UA）此前已真实验证；`_fetch_trending`（YouTube `ytInitialData`）递归解析逻辑对真实页面未在当前网络环境跑通（海外网络依赖）。
5. **search 默认亮但需 npx 首次拉包**：前端默认选中 search 源，首次运行会 `npx -y` 下载 baidu-search-mcp / bing-cn-mcp（网络 + 时间开销），若下载失败 `_search_one` 优雅降级为空，不影响其余源。

## 下阶段入口

P4-D 个人账号（供应商 + key + `llm.py` 抽象，供 P4-C 的 LLM-judge 与关键词 LLM 抽取用）。真相源 `PLAN-P4.md` §六。
