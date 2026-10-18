"""LLM-judge（C3）：第三方模型结构化打分 {score, pass, reason}，与主 LLM 解耦。

默认复用主 provider，可选独立 provider（config.judge_settings()）。
无 key / 确定性档 → 跳过（pass=True），不阻断 pipeline。
"""

from __future__ import annotations

import json
from typing import Any

from src import config, llm, llm_mode

JUDGE_SYSTEM = "你是质量门裁判。只输出 JSON：{\"score\": 0-10, \"pass\": true/false, \"reason\": \"...\"}"


def judge(prompt: str, *, system: str = JUDGE_SYSTEM) -> dict[str, Any]:
    """结构化 LLM-judge。无 key 或确定性档 → 跳过（pass=True）。"""
    if llm_mode.get_mode() == llm_mode.MODE_DETERMINISTIC:
        return {"score": 0.0, "pass": True, "reason": "确定性档，judge 跳过"}
    base_url, model, key = config.judge_settings()
    if not key:
        return {"score": 0.0, "pass": True, "reason": "未配置 judge key，跳过"}
    text = llm.call_llm(prompt, base_url=base_url, model=model, key=key, system=system)
    return parse_judge(text)


def parse_judge(text: str) -> dict[str, Any]:
    """解析 judge 返回 JSON。剥 markdown 包裹，缺字段补默认。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # 去开头 ```json 或 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    data = json.loads(text)
    return {
        "score": float(data.get("score", 0.0)),
        "pass": bool(data.get("pass", True)),
        "reason": str(data.get("reason", "")),
    }
