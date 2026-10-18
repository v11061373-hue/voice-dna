# 外部数据源插件（P1）

热点猎人 `trend_hunter` 支持两类外部数据源接入，统一产出 `TrendItem` 契约：

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | str | 热点标题 |
| `platform` | str | 平台名（即分派名） |
| `heat` | float | 热度数值 |
| `url` | str | 跳转链接 |
| `category` | str | 分类 |

## 方式一：进程内 Scraper（`plugins/scrapers/`）

在 `plugins/scrapers/` 放一个 `.py`，继承 `Scraper` 设 `name`，实现 `get_items()` 迭代器。启动时自动 import 进分派表，`run(platform="<name>")` 即可命中。

```python
# plugins/scrapers/zhihu_hot.py
from src.tools.trend_hunter import Scraper, TrendItem

class ZhihuHotScraper(Scraper):
    name = "zhihu"

    def get_items(self):
        # 抓你的源，逐条 yield
        yield TrendItem(title="...", platform="zhihu", heat=100, url="...", category="...")
```

出错抛 `ScraperException` 即降级为无结果，不阻断其它平台。

## 方式二：HTTP 契约（`plugins/sources.json`）

外部服务暴露一个返回 `TrendItem[]` 的 JSON 端点，在 `plugins/sources.json` 登记：

```json
{"myapi": "https://your-service.example.com/trends"}
```

`trend_hunter` 会 `GET` 该 URL（带浏览器 UA，10s 超时），期望返回：

```json
[{"title": "热点", "platform": "myapi", "heat": 100, "url": "https://...", "category": "美妆"}]
```

`run(platform="myapi")` 命中；缺省 `run()` 聚合全部内置 + 插件源。

## 方式三：外部 Skill（MCP tool 层，P2）

外部 skill 以标准 MCP server 接入，`mcp_client` 按 tool name 路由。在 `plugins/mcp_servers.json` 登记：

```json
[
  {"name": "filesystem", "transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/data"]},
  {"name": "web", "transport": "http", "url": "http://localhost:9000/mcp"}
]
```

- `stdio`：`command` + `args` 起子进程（npx / python -m 等）。
- `http`：已运行的 Streamable HTTP MCP server，`url` 指向端点。
- `sse`：老式 SSE 端点，同上给 `url`。

登记后外部 tool 命名 `server.tool`（如 `filesystem.list_directory`），前端「外部 Skill」栏列出可单独运行，走同一个 `/api/tool`。

## 注意

- 插件只加载一次，改动后重启服务生效。
- 接入源若有 API key，放在你自己的服务端 / 环境变量里，不要写进 `sources.json` 或仓库。
