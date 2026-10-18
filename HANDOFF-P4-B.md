# HANDOFF-P4-B — 安全网关 G1–G5

状态：完成 ✅ · 2026-10-19

## 完成度

- 复制适配 `bidforge-v4/src/mcp_guard` → `src/mcp_guard/gateway.py` + `__init__.py`
- 五门全落地：G1 工具门（白名单）/ G2 动作门 / G3 风险门 / G4 预算门 / G5 审计门
- 接线：
  - `mcp_client.call_tool` 未注册 tool / server → `GuardDenied("G1", …)`（非 KeyError 崩）
  - `web_server /api/tool` 捕获 `GuardDenied` → 返回 `{allowed:false, gate:"G1", reason}`
- 测试：`tests/test_guard.py` 7 例 + `tests/test_mcp_servers.py` 断言 KeyError → GuardDenied

## 差异（vs BidForge）

- G4 只限流 → 并入成本 / 时间 / 重试（`cost_budget` / `time_budget` / `max_retries`）
- 去掉 `agent_tokens` 预共享令牌（单用户无鉴权）
- tool 名放宽 `server.tool`（允许 `.` / `-`），G2 显式映射 6 本地 tool + 关键字兜底外部 tool
- 审计去 msvcrt 文件锁（单进程追加；多进程再上 fcntl/msvcrt）

## 测试证据

- `pytest`：**73 passed**（66 → +7）
- `ruff check src/mcp_guard`：All checks passed
- `mypy src/mcp_guard`：Success（2 files）

## 未完成 / 待办

- 全仓 ruff 未清：`mcp_client.py` / `web_server.py` / `test_mcp_servers.py` 有 P0–P3 遗留告警（S110 / BLE001 / S112 / PLW0602 / import 排序），非本阶段引入，未动。
- G3 `external_write` 是「硬拒」；真正的人工批准交互（human_gate 按钮）待 P4-C 编排接入。
- `MCPGuard` 尚未被 pipeline 调用（P4-C 才接入 agent 编排）；当前只在 `call_tool` 单 agent 路径做 G1。

## 下阶段入口

P4-A 数据源层（A1 注册表 → A2 选用 → A3 召回 → A4 登录）。真相源 `PLAN-P4.md` §三。
