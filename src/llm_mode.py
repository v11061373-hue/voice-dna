"""LLM 参与度控制（C0）：全局三档 + 每 agent 布尔开关，存内存（os.environ，无持久化）。

三档语义（仅对开关亮起的 agent 生效）：
  deterministic 确定性：零 LLM（style_mimic 走降级卡）。
  fallback      兜底（默认）：主路径先跑，无 baseline 才调 LLM。
  full          全开：每步调 LLM。
"""

from __future__ import annotations

import os
from typing import Any

MODE_DETERMINISTIC = "deterministic"
MODE_FALLBACK = "fallback"
MODE_FULL = "full"
MODES = (MODE_DETERMINISTIC, MODE_FALLBACK, MODE_FULL)

AGENTS = (
    "trend_hunter",
    "topic_planner",
    "style_mimic",
    "script_writer",
    "publish_optimizer",
    "data_analyst",
)

_ENV_MODE = "VOICEDNA_LLM_MODE"


def get_mode() -> str:
    m = os.environ.get(_ENV_MODE, MODE_FALLBACK)
    return m if m in MODES else MODE_FALLBACK


def set_mode(mode: str) -> None:
    os.environ[_ENV_MODE] = mode if mode in MODES else MODE_FALLBACK


def agent_enabled(agent: str) -> bool:
    """每 agent 布尔开关（默认全亮）。"""
    return os.environ.get(f"VOICEDNA_LLM_{agent.upper()}", "1") not in ("0", "false", "False")


def set_agent(agent: str, enabled: bool) -> None:
    os.environ[f"VOICEDNA_LLM_{agent.upper()}"] = "1" if enabled else "0"


def llm_enabled(agent: str) -> bool:
    """该 agent 是否可调 LLM：确定性档无视开关强制零 LLM。"""
    if get_mode() == MODE_DETERMINISTIC:
        return False
    return agent_enabled(agent)


def should_llm(agent: str, has_baseline: bool) -> bool:
    """三段式第二段决策：该 agent 当前该不该调 LLM 补充。

    全开 → 总是；兜底 → 无 baseline 才调；确定性/开关关 → 不调。
    """
    if not llm_enabled(agent):
        return False
    if get_mode() == MODE_FULL:
        return True
    return not has_baseline


def supplement(agent: str, has_baseline: bool, baseline: Any, fn) -> Any:
    """三段式第二段统一入口：按 C0 档位决定是否调 fn() 做 LLM 补充。

    - 确定性/开关关/无 key → baseline 原样。
    - 全开 → 总是 fn()；兜底 → 无 baseline 才 fn()。
    - 无 baseline 的 LLM 生成打「llm_fallback」标签（供溯源门查）。
    - fn 异常 → baseline（LLM 不可用不阻断主路径）。
    """
    from src import llm  # 懒加载，避循环 import

    if not should_llm(agent, has_baseline):
        return baseline
    if not llm.has_key():
        return baseline
    try:
        result = fn()
    except Exception:  # noqa: BLE001 — LLM 异常回落 baseline，不阻断主路径
        return baseline
    if not has_baseline and isinstance(result, dict):
        result["llm_fallback"] = True
    return result
