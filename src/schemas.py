"""编排状态定义 + 每 agent 输出 schema（C3 schema 硬门读）。"""

from typing import Any, TypedDict


class SocialMediaState(TypedDict, total=False):
    """表达基因（Voice DNA）社媒 Agent 编排状态。六步产物 + 控制字段。"""

    # 输入
    account_profile: str  # 账号人设 / 赛道 / 独特性
    samples: str  # 风格样本 / 参考素材（md 附件前置注入）
    enabled_sources: list[str]  # 前端 chip 选中的数据源（trend_hunter 只跑这些）

    # 六步产物
    trends: list[dict[str, Any]]  # 热点猎人：热点列表
    topics: list[dict[str, Any]]  # 选题策划：选题 + 评分
    style_card: dict[str, Any]  # 风格模仿：风格 DNA 卡
    script: dict[str, Any]  # 脚本文案：分镜脚本 + 画面 + 时长
    publish_plan: dict[str, Any]  # 发布优化：平台 + 时间 + 标签
    analytics: dict[str, Any]  # 数据分析：对比基准 + 异常检测

    # 控制
    current_stage: str
    stage_status: str
    errors: list[str]
    warnings: list[str]

    # 回流（可选，默认关）：数据分析→选题策划 循环边
    loop_rounds: int  # 额外回流次数；0 = 关（线性一次跑完）
    loop_count: int  # 已完成的分析遍数（data_analyst 每次成功 +1；首遍后 =1）

    # 视频摄入（P5-E 后置增强，可选）：trend_hunter 顺手记代表性视频，END 后调用层驱动转录
    candidate_videos: list[dict[str, Any]]  # 代表性视频候选 [{title, platform, url, heat}]
    transcripts: dict[str, str]  # 转录逐字稿 {video_url: text}
    video_visual: dict[str, Any]  # 视觉分镜卡（P5-D 功能态，可选）
    v1_script: dict[str, Any]  # v2 回流对照：v1 脚本快照（可选）


# ——— 每 agent 输出 schema（C3 schema 硬门）———

# 风格卡 7 字段（单一真相源；style_mimic 从此 import，勿再本地定义）。
STYLE_CARD_FIELDS: tuple[str, ...] = (
    "persona",
    "voice",
    "catchphrases",
    "sentence_patterns",
    "pacing",
    "narrative_structure",
    "visual_style",
)

# 每 stage → state 里的产物字段名。
OUTPUT_FIELD: dict[str, str] = {
    "trend_hunter": "trends",
    "topic_planner": "topics",
    "style_mimic": "style_card",
    "script_writer": "script",
    "publish_optimizer": "publish_plan",
    "data_analyst": "analytics",
}

# 每产物字段 → 期望类型（schema 硬门判类型）。
OUTPUT_TYPE: dict[str, type] = {
    "trends": list,
    "topics": list,
    "style_card": dict,
    "script": dict,
    "publish_plan": dict,
    "analytics": dict,
}

# dict 产物必填子字段。
REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "style_card": STYLE_CARD_FIELDS,
    "script": ("body", "scenes", "duration"),
    "publish_plan": ("platform", "best_time", "tags", "hashtags", "description"),
    "analytics": ("report", "metrics", "benchmark", "anomalies"),
}

# list 产物每项必填键。
ITEM_KEYS: dict[str, tuple[str, ...]] = {
    "trends": ("title", "platform", "heat"),
    "topics": ("title", "score", "reason"),
}
