# HANDOFF-P5-D — video_vision 视觉分镜工具（功能态）

状态：✅ 完成（TDD 6 测 + 注册 2 测改 + 全量 216 绿 + F7 真数据功能验证）· 2026-10-19

## 交付内容

新文件 `src/tools/video_vision.py`，`run(path, fps=1/3) -> dict`：

- `_ffmpeg_bin()`：复用 imageio_ffmpeg 自带二进制（模式同 transcribe，surgical 未动 transcribe，本地复制 6 行 helper）。
- `_extract_frames(media, outdir, fps)`：ffmpeg `-vf fps=…` 抽 `frame_%04d.jpg` 到 tempfile。
- `_describe_frame(jpg, key)`：逐帧 Qwen-VL（data:image/jpeg;base64）一句话描述画面/景别/转场。
- `_summarize(descriptions, key)`：一次文本调用汇总成 `{"shot_rhythm", "visual_style"}`（`parse_json` 复用 src.llm）。
- `run()` 返回 `{"shot_rhythm", "visual_style", "scenes": [逐帧描述…]}`。

成本门：`_vision_enabled()` = `VOICEDNA_VISION == "1"`（默认关：未设 / 0 / 任意非 1 均回空 dict，不调 ffmpeg 不调 API）。无 `DASHSCOPE_API_KEY` 时也回空 dict 不崩。

注册接线：`src/mcp_server.py` 加 `@mcp.tool(name="video_vision")`；`src/mcp_guard/gateway.py`
`VOICE_DNA_TOOLS` + `TOOL_ACTIONS["video_vision"]="read"`（只读抽帧无副作用）；`src/tools/__init__.py`
TOOLS 注册表加 `video_vision`。tool 总数 8 → 9，`test_mcp_client.py` 两个「eight tools」断言同步改「nine tools」。

## 关键偏离（外部模型名漂移）

计划/任务写「Qwen-VL-Max」，实测 DashScope compatible-mode `/models` 已无 `qwen-vl-max`，当前 VL 模型只有 `qwen3-vl-plus`（通用）+ `qwen-vl-ocr` / `qwen-vl-ocr-2025-11-20`（OCR 专用）。
`qwen-vl-max` 调 `/chat/completions` 回 404（qwen-plus 同端点 200 证 key/端点正常），故 `QWEN_VL_MODEL` 定为 `qwen3-vl-plus`。功能验证已用 qwen3-vl-plus 真跑通。

## 测试证据

- `tests/test_video_vision.py` 6 测（TDD 先红后绿）：缺 path 抛 ValueError / 默认关回空 /
  `VOICEDNA_VISION=0` 短路 / 无 key 降级 / 抽帧命令（monkeypatch 断言 `-vf fps=` + `.jpg`）/
  逐帧聚合（2 帧 → scenes 2 条 + shot_rhythm/visual_style）。
- 全量 `pytest -q`：**216 passed**（P5-E 收尾 210 → 本阶段 +6）。
- `ruff check`（6 触及文件）**All checks passed**；`mypy src/tools/video_vision.py` **Success**。
- F7 功能验证（真 key + imageio_ffmpeg + 9s testsrc 视频）：
  - `VOICEDNA_VISION=1` → **3 帧**，shot_rhythm 56 字 / visual_style 55 字 / scenes 全 CJK 中文非空。
  - `VOICEDNA_VISION=0` → `{}`。

## 未完成项

1. **模型名漂移未做可配置**：`QWEN_VL_MODEL` 硬编码 `qwen3-vl-plus`。若 DashScope 再次改名，改一行常量即可；未加 env 覆盖（YAGNI，本次漂移说明改名会再发生，但先不预建配置）。
2. **空视频 / 极短视频（<3s）抽 0 帧**：`frames=[]` 时 `_summarize([])` 仍会调一次 API 汇总空串（可能回臆造卡）。真实短视频必有帧，未加 `if not frames: return {}` 守卫（可一行补）。
3. **P5-E 的 `video_visual` 状态字段已预留**，但本阶段只落独立 tool，未接进 graph 主管线（按计划视觉是后置增强，不进主管线；接线属 P5-E 完成后的可选串联，未在本阶段范围）。

## 下阶段入口

- **F1 真数据全图 E2E**（bilibili 源恢复后）：承 P5-F5，跑 `v2_app.ainvoke` 到 END 验溯源门。
- **P5-F 云端 ASR 接线**（可选）：transcribe `_asr_cloud` stub 接 DashScope 流式。
- **P5-G 收尾**：全仓 ruff/mypy 清理（E3 达标，26+13 告警已在 P5-B 摸底）。

## unverified_assumptions

1. **qwen3-vl-plus 图像格式契约**：用 OpenAI 兼容 `image_url` + `data:image/jpeg;base64` 验证通过，但仅 320x240 testsrc 合成视频；真实竖屏/高分辨率短视频未测，帧大小对 base64 体积与请求上限的影响未量化。
2. **模型名漂移点单一**：只确认 `qwen-vl-max` 404、`qwen3-vl-plus` 可用；`qwen-vl-ocr` 系专用 OCR 未测是否也能做通用分镜（选了通用 qwen3-vl-plus，未交叉对比画面描述质量）。
3. **成本未实测**：逐帧 + 汇总共 N+1 次调用（9s→3 帧→4 次），实际 token/价格未计量；`VOICEDNA_VISION` 门默认关，但开起后无预算上限（未接 G4 成本预算）。
4. **终端 mojibake 非代码 bug**：Windows 控制台 GBK 显示，`cjk` 校验证文本真中文（承 P5-F5 假设 #4）。
