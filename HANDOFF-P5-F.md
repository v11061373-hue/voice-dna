# HANDOFF-P5-F — 云端 ASR 接线（DashScope 流式，可选最后一步）

状态：✅ 完成 · 2026-10-19

## 交付内容

`transcribe._asr_cloud` stub 接 DashScope 流式 ASR（`paraformer-realtime-v2` + `Recognition` +
`RecognitionCallback`）。默认仍 local，`backend="cloud"` 显式切。key 走 `DASHSCOPE_API_KEY`，不落盘。

## 改动清单

| 改动 | 文件 | 测试 |
|------|------|------|
| `_asr_cloud`：懒加载 dashscope SDK（可选依赖）→ `Recognition` 流式（start/send_audio_frame/stop）→ 只回 `sentence_end=True` 文本拼接，跳过流式中间态 | `src/tools/transcribe.py` | `test_asr_cloud_streams_and_joins_sentence_end` |
| 无 `DASHSCOPE_API_KEY` 时显式 `RuntimeError`（F6 优雅降级） | `src/tools/transcribe.py` | `test_cloud_backend_requires_key` |
| `on_error` 回传 → `RuntimeError("DashScope ASR 失败: ...")` | `src/tools/transcribe.py` | `test_asr_cloud_raises_on_error` |
| 删旧 `test_cloud_backend_raises_not_implemented` → `test_cloud_backend_dispatches_to_asr_cloud` | `tests/test_transcribe.py` | 同上 |
| 测试隔离可选依赖：`_install_fake_dashscope` 把 `dashscope.audio.asr` 换成假模块（不要求真装 dashscope 跑测试） | `tests/test_transcribe.py` | — |

## 关键决策

- **模型/格式经真 API 实测定死**：`paraformer-realtime-v2` + `format="wav"` + `sample_rate=16000`
  （本会话 live 探针确认真 API 回非空中文，非照抄文档）。流式中间态是逐帧增长，`sentence_end`
  标志区分完整句，故只拼 `sentence_end=True` 的 `text`，避免把中间态拼进去。
- **dashscope SDK 懒加载、不进 requirements.txt**：cloud 是 opt-in（`backend="cloud"` 显式切），
  本地默认路径不依赖 SDK。符合 P5「内置接口，不内置模型」。未装时 `RuntimeError` 明确提示装法。
- **`run()` 入口零改动**：`_asr` 分派已就绪（P5-B），只换 `_asr_cloud` 内部，surgical。

## 测试证据（全部实跑）

- `python -m pytest -q`：**219 passed**（P5-G 基线 216 + 3 新测）。
- `ruff check src/tools/transcribe.py tests/test_transcribe.py`：**All checks passed**。
- `mypy src web_server.py app.py`：**Success: no issues found in 29 source files**。

## 功能验证（真 API，非 mock）

TTS（`sambert-zhichu-v1`）生成 16k 单声道 wav「你好世界，今天天气不错」→
`run(source='_probe_speech.wav', backend='cloud')`：

- `backend == "cloud"`，`text` 13 字非空，`has_cjk=True`（终端 mojibake 是 Windows GBK 显示，内存字符串真中文）。
- 临时 wav 用完已删，未落 repo。

## 未完成项

1. **F1 真数据全图 E2E（到 END）仍待 bilibili 源恢复**：承 HANDOFF-P5-F1/F5。本阶段不触搜索，与 cloud ASR 无关。
2. **长音频未测**：只验 ~2.5s 短 wav。`paraformer-realtime-v2` 流式有单次时长上限（官方实时模型约 5 分钟），长视频逐字稿需分段发帧或切 `paraformer-v2`（录音文件识别，异步 API，非本 Recognition 类）。未触发故未预改（YAGNI）。

## unverified_assumptions

1. **`sentence_end=True` 拼接策略只靠短句单轮验证**：多句长音频逐句 `sentence_end` 是否按序、`on_complete` 是否再兜底未测。当前 join 顺序 = 事件回调顺序，假设与句子先后一致。
2. **`paraformer-realtime-v2` 时长上限未探明**：短音频无碍，长音频（>5min）可能断连或截断。触发后需分段或换 `paraformer-v2` 异步文件识别 API（后者签名完全不同，是另一条接线）。
3. **`on_error` 只拿 `code`+`message`**：`RecognitionResult` 可能带 `status_code`/`request_id` 更细诊断，当前够用未全采。
