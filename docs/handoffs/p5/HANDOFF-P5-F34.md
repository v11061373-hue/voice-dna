# HANDOFF-P5-F34 — v2 回流全图 E2E（F3/F4 功能验收）

状态：✅ 完成 · 2026-10-19

## 背景

P5-E 落的 v2 回流（转录逐字稿 → 二次跑 → v1 vs v2 对照）此前只验了 F5 甩链接单条，
未串进全图。本阶段跑通 F3/F4 全图 E2E，是「视频摄入」核心卖点的功能验收。

## 执行链路（真数据，非 mock）

```
v1 = app.ainvoke({account_profile:"热点", enabled_sources:["bilibili"]})   # 4 trends + 3 candidate_videos
  → video_download.run(BV16n4y1R7e1)  # 广东台 150s 新闻口播，bilibili 直下
  → transcribe.run(path, backend="local")  # funasr :8000，719 字粤语新闻口播
  → v2 = v2_app.ainvoke({trends, topics, transcripts:{url:text}, v1_script:v1.script})
  → data_analyst 出 v1 vs v2 对照
```

`VOICEDNA_LLM_MODE=full`，provider=qwen（DASHSCOPE_API_KEY）。

## 验收结果（F3/F4 全 PASS）

| 标准 | 结果 | 证据 |
|------|------|------|
| F3：v2 脚本含转录内容词、与 v1 有差异 | ✅ | `comparison.changed=True`、`grounded=True`；v2 body 直接落地转录词（「罗湖中兴路」「信德堂药店」「人质」「零时四十五分」「记者赶到」），v1 body 是苏杉杉直播，两者完全不同 |
| F4：data_analyst report 含 v1 vs v2 结构化对照 | ✅ | `report` 尾缀「 v1 vs v2 对照：更好」；`comparison.verdict="更好"`（changed+grounded） |
| 到 END（非 human_gate） | ✅ | `v2.current_stage="data_analyst"`、`stage_status="ok"`、`errors=None` |

v2 script body 摘要：以转录的真实新闻细节开篇（深夜十一点半、罗湖中兴路、信德堂药店、人质对峙），
再与 v1 的「热点追踪旧闻」主题对接，甚至沿用粤语语气（「冇松手」「糖水」「阿伯」），
证明逐字稿真的成了可溯源素材（不是编造）。

## 关键发现（非本阶段引入，记录）

1. **候选视频可能是 MV/音乐**：首轮挑到的 BV1wang69Efu（苏杉杉，81s）音频是歌曲，
   funasr 转出的是歌词（168 字、含大量 ASR 错误），v2 脚本「grounded」在歌词上。换新闻
   口播视频 BV16n4y1R7e1（150s）后转出 719 字真口播。`select_candidate_videos` 只按 heat
   挑代表性视频，不过滤「是否有口播」——生产上转录 MV 得的是无价值歌词。属候选视频
   质量，非 F3/F4 范围。
2. **转录含 ASR 噪声 + 粤语**：719 字里夹带视频自带字幕残句（「他他老婆就是他老婆」）与
   粤语口语。v2 脚本仍能落地内容词（`_CONTENT_WORD_RE` 抽 2-4 字中文段），未阻断 grounded。

## 未完成项

- **F7 视觉功能态（P5-D）仍零代码**：video_vision 抽帧 + Qwen-VL 描述未落，`VOICEDNA_VISION`
  门短路已留 seam（video_vision.py 空跑回 {}），抽帧是唯一新写件。
- **F6 局部**：cloud 无 key 已单测覆盖；本地 funasr 未起、下载源 412 时的全链优雅降级未做
  真数据 E2E（412 已在 F1 复现里观测到空 trends → HALT，路径存在但未单独测）。

## unverified_assumptions

1. **grounded 判定依赖 LLM 逐字引用 2-4 字段**：`_CONTENT_WORD_RE` 是粗切分（无分词），
   v2 脚本须逐字含转录子串才 grounded=True。本轮 LLM 恰好落地了「罗湖中兴路」等词；
   若 LLM 换词重述（同义改写），会误判「变化」而非「更好」。要更准需 jieba/向量召回
   （`data_analyst.py:139` 已标 ponytail 升级路径）。
2. **单条视频单轮复现**：只 BV16n4y1R7e1 一条。MV 转录、超长视频（>5min）、douyin/xhs
   （需 cookie）未测，不能据此断言转录链对全平台/全时长普适。
3. **funasr 进程后台起，会话结束可能被回收**（承 P5-C 风险）：下阶段先 `curl :8000`，000 则
   `funasr-server --device cpu --host 127.0.0.1 --port 8000` 重起。
