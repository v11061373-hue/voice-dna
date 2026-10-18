# HANDOFF-P5-C — download_video 工具（视频下载）

状态：P5-C 代码完成 + bilibili 真下载已验证 · 2026-10-19

## 完成度

### 改动清单

| 改动 | 文件 |
|------|------|
| 新 tool `video_download`：`run(url) -> {"path": str}`，平台分派 + bilibili 直下 + douyin/xhs 指引 + tempfile 落盘/cleanup | `src/tools/video_download.py` |
| `video_download` 注册进 TOOLS 表 | `src/tools/__init__.py` |
| `_video_download` 注册 FastMCP tool | `src/mcp_server.py` |
| `video_download` 进白名单 + 动作分类 `read`（下载无副作用只读远端） | `src/mcp_guard/gateway.py` |
| 7 tool → 8 tool 计数注释同步 | `src/mcp_guard/__init__.py`、`mcp_server.py`、`gateway.py` |
| 新增 `test_video_download.py` 8 测 | `tests/test_video_download.py` |
| 7 → 8 tool 断言更新 | `tests/test_mcp_client.py` |

### 内部链路（P5-C 落地）

```
run(url)
  ├─ _platform(url) → bilibili / douyin / xhs / unknown
  ├─ bilibili → _download_bilibili(url, _dl_dir())
  │     ├─ _bvid(url)：正则 BV[0-9A-Za-z]{10}
  │     ├─ view API 拿 cid（api.bilibili.com/x/web-interface/view，无 wbi）
  │     ├─ playurl API fnval=0 拿 mp4 durl（x/player/playurl）
  │     └─ _fetch_bytes(durl) 带 UA+Referer → 写 outdir/{bvid}.mp4
  ├─ douyin/xhs → _download_douyin_or_xhs(url, _dl_dir())
  │     └─ 只给指引（CDP :9222 抓流法 / 贴 cookie），下载接线留后补
  └─ _dl_dir()：模块级 tempfile.mkdtemp(prefix="voice-dna-download-")，atexit cleanup 删
```

- `_HEADERS` 复用 dy_transcribe.py `fetch()` 的 UA + Referer（`https://www.bilibili.com/`），
  直下 403 先查这个（已实测通）。
- 铁律：下载落 tempfile（不落 repo），进程退出 `cleanup()` 删；cookie 只读
  `src/cookies.COOKIE_PATH`（`~/.voice-dna/cookies.json`）；key 只 os.environ。
- 关键衔接：`transcribe._download` 的 lazy import 已自动接上 `video_download.run(source)["path"]`
  （`run` 返回 `{"path": str}` 即生效），未改 transcribe.py。

## 测试证据（全部实跑）

- `pytest -q`：**194 passed**（基线 186 + video_download 8 测）。
- `ruff check`（P5-C 触及 7 文件）：**All checks passed**。
- `mypy src`：**Success: no issues found in 26 source files**。
- 功能实测（真机 bilibili 直下）：`run("https://www.bilibili.com/video/BV15VfVYUEsG")`
  → 落 `%TEMP%\voice-dna-download-xxx\BV15VfVYUEsG.mp4`，**50,566,258 bytes 非空**，5.8s，
  `cleanup()` 后确认删除。
- 功能实测（transcribe url 分支全链 E2E）：`transcribe.run(source="…BV15VfVYUEsG")`
  → **backend=local、text 2405 字非空中文**，230.2s（下载+抽音轨+funasr）。确认
  `transcribe._download` 的 lazy import 已自动接上 `video_download.run`，seam 通。

## 未完成项

1. **douyin/xhs 下载未接线**：`_download_douyin_or_xhs` 只给指引（贴 cookie 到
   `~/.voice-dna/cookies.json` 或 CDP :9222 抓流）。根因：已验证的 dy_transcribe.py
   CDP 抓流依赖 `websockets`，voice-dna `requirements.txt` 未列该依赖（不新造/不新增依赖）。

## 下阶段入口（P5-E 后置增强 + v2 回流）

按 PLAN-P5.md §六，P5-C 完成进 **P5-E**（串联 B/C）：

1. `schemas.py` 加 `candidate_videos` / `transcripts` / `video_visual` 状态字段。
2. `trend_hunter.py` 记代表性视频（最高热度 1-3 条、platform 为视频平台）入 `candidate_videos`。
3. `graph.py`：`style_mimic_node` / `script_writer_node` 转发 `transcripts`。
4. `app.py`：END 后 `cl.AskActionMessage` 问「转录哪个视频」→ 逐条 `transcribe` → 二次 ainvoke。
5. v2 回流：复用 v1 trends，只重跑 style→script→publish→analyst，data_analyst 出 v1 vs v2 对照。

## unverified_assumptions

1. **bilibili fnval=0 单 mp4**：本会话 BV15VfVYUEsG 有 durl 直下成功；部分新发布视频
   fnval=0 可能 durl 空（DASH-only），届时回落 fnval=16 取 dash.audio 流。未测该分支。
2. **bilibili API 无 wbi**：`view`/`playurl` 实测 code 0（无需 wbi 签名）；`popular`/`ranking`
   列表接口返回 -352（wbi 签名），P5-C 不依赖列表接口，故无影响。
3. **douyin/xhs cookie 路径**：只验证了指引指向 `~/.voice-dna/cookies.json`（单路径），
   cookie 真实下载逻辑未接。
4. **funasr-server 进程**：本会话 `:8000` 有响应（`/docs` 200），会话结束可能被回收；
   P5-E 功能实测前需确认 `curl :8000`，否则重起 `funasr-server --device cpu`。
5. **ruff 全量基线**：`ruff check src tests` 仍有 25 既有告警（BLE001/S110/SIM117/I001/
   UP037/TRY002/S112/PYI034/PLW0602/PLC0206），全在 P5-C 未触及的文件；P5-C 触及 7 文件
   单独 ruff 全绿。已排期 **P5-G**。
