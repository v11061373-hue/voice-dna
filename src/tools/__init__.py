"""六 Agent MCP tool 注册表。call_tool 按名路由。"""

from src.tools import (
    data_analyst,
    publish_optimizer,
    script_writer,
    style_mimic,
    topic_planner,
    trend_hunter,
)

TOOLS = {
    "trend_hunter": trend_hunter.run,
    "topic_planner": topic_planner.run,
    "style_mimic": style_mimic.run,
    "script_writer": script_writer.run,
    "publish_optimizer": publish_optimizer.run,
    "data_analyst": data_analyst.run,
}
