# HANDOFF-P5-F5 — 甩链接真实链复现（下载 + 转录）

状态：F5 严格复现通过（下载 29,226,098 bytes + funasr local 转录 755 字中文）· 2026-10-19

## 背景

P5-F1 遗留「F1 真数据全图 E2E 未复现」：bilibili `bilibili_search` HTTP 412 反爬，
`trend_hunter` 返回空 trends → 无素材。本阶段绕过搜索 412，走**甩链接模式**直接验
下载 + 转录真实链（用户点名唯一空白：之前只抓到 B 站标题+评论区，下载+转录没真跑过）。
这是 F1 完整 E2E 与 P5-D 视觉抽帧的前置。

## 执行结果（全部实跑，非 mock）

| 步骤 | 命令/输入 | 结果 |
|------|-----------|------|
| funasr 重启 | `funasr-server --device cpu --host 127.0.0.1 --port 8000`（后台） | `:8000` 回 405（有响应即活，非 000） |
| 下载 | `video_download.run(url='https://www.bilibili.com/video/BV1LEJ96bE7c')` | `path` 非空，**29,226,098 bytes**（= P5-E F5 基线） |
| 转录 | `transcribe.run(source='…/BV1LEJ96bE7c', backend='local')` | **text 755 字非空中文**，backend=local，全链 109s |

链路确认：url → download_video 落盘 tempfile → ffmpeg 抽 16k 单声道 wav → funasr :8000
multipart → 755 字中文。与 P5-E F5 记录完全一致（同 BV 同字节数同字数）。

## 根因 / 风险点排查

- **fnval=0 DASH-only 回落（P5-C 已知风险）未触发**：BV1LEJ96bE7c `playurl` durl 非空，
  直下成功。`video_download.py` 现写死 fnval=0，对新 DASH-only 视频 durl 空报错，触发时
  再改 16 重试——本阶段不预改（YAGNI，功能验证为主，surgical 只改本阶段）。
- **bilibili 搜索 412 未复现**（本阶段不触搜索，甩链接绕过），源侧波动仍未定性，非代码 bug。
- **终端 mojibake 非代码 bug**：Windows 控制台 GBK 显示，`has_cjk=True` 证实文本真中文。

## 未完成项

1. **F1 真数据全图 E2E（到 END）仍未跑**：需 bilibili 源恢复（或换源）后走
   trend_hunter → … → data_analyst 全图，确认非 human_gate。本阶段只通了 F5 甩链接，
   为 F1 完整 E2E 铺路（转录逐字稿 = 可溯源素材）。
2. **P5-D video_vision 抽帧未动**：视觉分镜卡零现成代码，本阶段只验证了它的前置
   （下载产物 + ffmpeg 可抽帧），抽帧+Qwen-VL 描述待 P5-D 落。
3. **fnval=16 回落分支未实跑**：无触发样例，代码未改，测试也未补（无真实 DASH-only
   BV）。触发后再 TDD 补。

## 下阶段入口

- **F1 完整 E2E**：bilibili 源恢复后 `v2_app.ainvoke`（显式 `enabled_sources=['bilibili']`
  复现，承 P5-E 未验证假设 #5）→ 到 data_analyst（END），确认溯源门 PASS 非 human_gate。
- **P5-D video_vision**：`video_visual` 状态字段已预留，`VOICEDNA_VISION=0` 短路门待落，
  抽帧 + Qwen-VL 描述为唯一新写件。

## unverified_assumptions

1. **单条视频复现，未批量**：下载+转录只 BV1LEJ96bE7c 一条。fnval=16 回落分支、多平台
   （douyin/xhs 需 cookie）均未测，不能据此断言下载器对新视频/新平台普适。
2. **funasr 进程后台起，会话结束可能被回收**（承 P5-C 风险 #4）：下阶段 F1 全图 E2E /
   P5-D 抽帧前先 `curl :8000`，000 则重起 `funasr-server --device cpu`。
3. **转录 109s 为全链耗时**（下载+ffmpeg+ASR），未单独测 RTF；P5 方案记 CPU RTF 0.29
   （30s 视频 ≈ 9s），本次视频更长故更久，未与 RTF 交叉验证。
4. **has_cjk 校验是唯一「真中文」证据**：终端显示 mojibake 不影响内存字符串，但未做
   逐字人工核对转录准确性（如错字率），仅证非空中文 + 字数=755=基线。
