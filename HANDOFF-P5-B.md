# HANDOFF-P5-B — transcribe 工具（ASR）

状态：P5-B 代码完成 + 已验证 · 2026-10-19

## 完成度

### 改动清单

| 改动 | 文件 |
|------|------|
| 新 tool `transcribe`（url/本地分支、ffmpeg 抽 16k wav、本地/云端分派、后端回落） | `src/tools/transcribe.py` |
| `transcribe` 注册进 TOOLS 表 | `src/tools/__init__.py` |
| `_transcribe` 注册 FastMCP tool | `src/mcp_server.py` |
| `transcribe` 进白名单 + 动作分类 `read`（无副作用只读音频） | `src/mcp_guard/gateway.py` |
| 6 tool → 7 tool 计数注释同步 | `src/mcp_guard/__init__.py`、`mcp_server.py`、`gateway.py` |
| 新增 `test_transcribe.py` 9 测 | `tests/test_transcribe.py` |
| 6 → 7 tool 断言更新 | `tests/test_mcp_client.py` |

### 内部链路（P5-B 落地的部分）

```
run(source, backend="local")
  ├─ source 是 url → _download(source)   [P5-C 接，此处 lazy import seam]
  ├─ 后缀非 .wav → _extract_wav (ffmpeg -ac 1 -ar 16000)   [tempfile，用完删]
  └─ _asr(wav, backend)
        ├─ backend="cloud" → _asr_cloud (stub 抛 NotImplementedError)
        └─ 其余一律 → _asr_local (httpx.post :8000/v1/audio/transcriptions)
```

- `_asr_local` 契约复用 dy_transcribe.py 已验证调用：multipart `file` 字段 + filename，
  回 `{"text": ...}`。
- `_ffmpeg_bin()`：`VOICEDNA_FFMPEG` env → imageio_ffmpeg 自带 → 系统 `ffmpeg`。
- 铁律：wav 落 `tempfile.TemporaryDirectory()` 上下文自动删；key 只 env；cookie 只
  `~/.voice-dna/cookies.json`（下载在 P5-C，P5-B 只留 `_download` seam）。

## 测试证据（全部实跑）

- `pytest -q`：**186 passed**（基线 177 + transcribe 9 测）。
- `ruff check`（P5-B 触及 8 文件）：**All checks passed**。
- `mypy src`：**Success: no issues found in 25 source files**。
- 功能实测（真机 funasr）：`run(source="C:\Users\rog\agent-senses\dy_transcripts\小毛驴入门指南.wav")`
  → `backend=local`，`text` 256 字非空中文（「哦，今天给大家推荐一个科研入门指南…」）。

## 未完成项

1. **url 分支真实下载未通**：`_download` 是 `src.tools.video_download` 的 lazy-import seam，
   该模块 P5-C 才建。P5-B 功能验收只测本地 wav（url 分支走单测 monkeypatch）。
2. **云端 ASR**：`_asr_cloud` stub 抛 `NotImplementedError`，P5-F 接 DashScope 流式。

## 下阶段入口（P5-C download_video 工具）

按 PLAN-P5.md §六，P5-B 完成进 **P5-C**：

1. 新文件 `src/tools/video_download.py`，`run(url) -> {"path": str}`；bilibili 直下，
   douyin/xhs 复用 dy_transcribe.py CDP :9222 抓流或指引贴 cookie。
2. 落地后 `transcribe._download` 的 lazy import 自动生效（无需改 transcribe.py）；
   并在 `src/tools/__init__.py` / `mcp_server.py` / `gateway.py` 按同模式注册。
3. TDD：先写 `test_video_download.py`（平台分派 + cookie 只落 `~/.voice-dna/cookies.json`）。

## unverified_assumptions

1. **`_download` lazy import 生效**：假设 P5-C 的 `video_download.run(url)` 返回
   `{"path": str}` 且自管下载 tempfile 清理；P5-B 未真机走 url 分支，未验证。
2. **funasr 启动参数**：本次用 `funasr-server --device cpu`（HANDOFF-P5 记录 RTF 0.29
   是 CPU 基准）；默认 `--device cuda` 在 GPU 机上未复测。
3. **`_asr_local` 契约字段**：file 字段名 / filename / `text` key 复用 dy_transcribe.py，
   本次真机转录回非空已验，但未逐字段比对 dy_transcribe 的原始返回结构。
4. **funasr-server 进程**：本会话后台起在 :8000（device cpu），会话结束可能被回收；
   P5-C/E 功能实测前需确认 `curl :8000` 有响应，否则重起 `funasr-server --device cpu`。
5. **ruff 全量基线**：`ruff check src tests` 仍有 26 个既有告警（SIM117 等），全在
   P5-B 未触及的文件（mcp_client/trend_hunter/cookies/llm_mode/session_store/conftest/
   test_plugins/test_session_store/test_mcp_servers）。P5-B 未顺手修（手术式），
   P5-B 触及的 8 文件单独 ruff 全绿。另有 `mypy web_server.py app.py` 13 告警（根目录，
   `mypy src` 不覆盖）。已排期为 **P5-G 全仓 lint/mypy 清理（收尾）**，见 PLAN-P5.md §六/§七。
