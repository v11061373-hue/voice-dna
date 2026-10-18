# HANDOFF-P5-UI — 交互接线（甩链接 / web_server v2 回流 / video_vision 抽帧真实现）

状态：✅ 完成 · 2026-10-19 · 221 测试绿

## 背景

P5 各 tool + v2 回流此前只在脚本层 E2E 验过，未全部接进运行中的前端交互。
本阶段把三个缺口接进对应交互，并把 video_vision 从「仅单测」推进到「真实现 + 功能态实跑」。

## 改动清单（全实跑，TDD）

| 改动 | 文件 | 测试/证据 |
|------|------|-----------|
| `is_video_url(text)` 纯函数：抽文本里第一个视频平台链接，非视频回 None | `src/tools/video_download.py` | `test_is_video_url_extracts_link` + `test_is_video_url_ignores_non_video`（红→绿） |
| 甩链接模式进 chainlit chat：`on_message` 检出链接 → `_run_link_mode`（下载+转录+视觉→v2 回流生成脚本） | `app.py` | 221 绿 + chainlit 8081 重启 200 |
| `_ingest_video` 抽公共：下载+转录+视觉一次下载三用，`_ask_transcribe` 复用之并出分镜卡 | `app.py` | 同上 |
| web_server v2 回流端点 `/api/v2`（v1 state + transcripts 二次跑 v2_app） | `web_server.py` | TestClient 空态回「v1 未跑完」；mypy clean |
| web_server 前端「候选视频 → 转录并 v2 回流」按钮 + v2 摘要卡 | `static/index.html` | node `new Function` 语法 OK |

## video_vision「真实现」实跑（F7 功能验收，非 mock）

`VOICEDNA_VISION=1` + `DASHSCOPE_API_KEY`（已 setx）真跑：

```
video_download.run(BV1LEJ96bE7c) → 29,226,098 bytes（= F5 基线）
video_vision.run(path, fps=0.05) → shot_rhythm + visual_style + 6 scenes（非空）
```

`qwen3-vl-plus` 逐帧描述 + 汇总分镜卡全通。**纠正此前交接「video_vision 零代码」的误记**
——`src/tools/video_vision.py` 早已实现（抽帧/逐帧 Qwen-VL/汇总）+ 8 单测，缺的只是功能态
实跑与 UI 接线，本阶段补齐。

## 各功能 ↔ 交互对应表

| 功能 | chainlit（主 chat，:8081） | web_server（FastAPI 逐步） |
|------|------|------|
| 六步流水线 | `on_message` 画像启动 | `/api/run` start/next/auto |
| 转录 transcribe | `_ask_transcribe`（END 后候选）+ 甩链接 | `/api/tool {tool:transcribe}` + 前端按钮 |
| 下载 video_download | `_ingest_video` 内部 | 同 `/api/tool` |
| 视觉 video_vision | `_ingest_video`（成本门默认关） | 未接（默认关，无 UI） |
| v2 回流 | `_ask_transcribe` / `_run_link_mode` 二次跑 v2_app | `/api/v2` + 前端「转录并 v2 回流」 |
| 甩链接 F5 | `on_message` 检出 URL 直进 | 未接（concierge 不识别 URL） |

## 服务运行状态

- funasr :8000 已跑（PID 348864，ASR 本地）。
- chainlit :8081 已重启（旧进程 343700 已 kill），200。**8000 被 funasr 占、8080 被 Docker 占**，
  故 chainlit 用 8081，非 README 写的 8000。
- web_server 未起（按需 `uvicorn web_server:server`）。

## 未完成项

1. **video_vision 的 web_server 前端未接**：成本门默认关（`VOICEDNA_VISION≠1` 回空），
   chainlit 已接（`_ingest_video` 里），web_server 前端无视觉按钮。启用视觉前先
   `VOICEDNA_VISION=1`，再决定要不要在 web_server 也加。
2. **甩链接 web_server 未接**：concierge 判意不识别 URL，甩链接只在 chainlit。若要在
   web_server 走甩链接，改 concierge 判意或前端 send() 加 URL 检测。
3. **index.html 无测试**：前端 JS 靠 node 语法检查 + 手测，仓库惯例前端不写 pytest。

## unverified_assumptions

1. **甩链接 v2 回流未真跑 E2E**：`_run_link_mode` 复用 F34 已验证的 v2_app 路径，但
   「无 trends、纯转录素材」这一条（style_mimic 空 topics、script_writer 空 trends 只靠
   transcripts）未单独真跑。理论上 script 靠转录词落地可过溯源门，未实测。
2. **video_vision fps=0.05 单条验证**：只 BV1LEJ96bE7c 一条、6 帧。逐帧 Qwen-VL 的
   `qwen3-vl-plus` 模型名、`data:image/jpeg;base64` 图片入参均单条通过，未多视频/多帧压测；
   成本随帧数线性涨（1/3 fps 长视频帧多费钱）。
3. **`/api/v2` 只测了空态错误路径**：TestClient 验了「无 trends 回错」；完整 v2 回流
   （真 v1 state + transcripts → v2_app）复用 F34 结果，未在 web_server 层真跑一次。
4. **chainlit 甩链接/视觉交互未点过 UI**：只验了 import + 服务 200，没在浏览器里真点
   「贴链接→转录→v2」和「候选视频→转录」。要人工点一遍收尾。
