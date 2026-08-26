"""Chainlit 前端 — 表达基因（Voice DNA）社媒 Agent 对话流（步骤 5）。

六步流水线：热点猎人 → 选题策划 → 风格模仿 → 脚本文案 → 发布优化 → 数据分析。
用户输入账号画像，graph.ainvoke 跑六步，LangchainCallbackHandler 把每节点映射
成 cl.Step 卡片（中间产物可点开）。最终结果 JSON 发回。

参照 README「前端层 chainlit」调研：@cl.on_message + @cl.on_chat_start +
cl.LangchainCallbackHandler（graph.ainvoke 传 config callbacks 自动挂 Step）。
"""

import json

import chainlit as cl

from src.orchestrator.graph import app


@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.Message(
        content="表达基因（Voice DNA）就绪。输入账号画像（如「美妆博主」）启动六步流水线。"
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    profile = message.content.strip() or "美妆博主"
    handler = cl.LangchainCallbackHandler()
    result = await app.ainvoke(
        {"account_profile": profile},
        config={"callbacks": [handler]},
    )
    await cl.Message(
        content=json.dumps(result, ensure_ascii=False, indent=2)
    ).send()
