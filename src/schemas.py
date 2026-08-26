"""编排状态定义。"""

from typing import Any, TypedDict


class SocialMediaState(TypedDict, total=False):
    """表达基因（Voice DNA）社媒 Agent 编排状态。六步产物 + 控制字段。"""

    # 输入
    account_profile: str  # 账号人设 / 赛道 / 独特性

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
