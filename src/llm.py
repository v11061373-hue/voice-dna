"""通用 OpenAI 兼容 client — 6 agent 共用（D3）。

读 os.environ 的 VOICEDNA_* 配置（src/config.py 写入）。无 key 抛 ValueError，
调用方（style_mimic 等）据 has_key() 先降级。judge 独立调法：传显式 base_url/model/key。
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

# token 计量（G4 成本预算用）：call_llm 累加 usage，total_tokens() 供 call_tool 量调用前后差。
_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}


def total_tokens() -> int:
    """累计消耗 token 数（prompt+completion），跨 main + judge 全 LLM 共享。"""
    return _usage["prompt_tokens"] + _usage["completion_tokens"]


def has_key() -> bool:
    """主 key 是否已配（style_mimic 等据此决定走 LLM 还是降级卡）。"""
    return bool(os.environ.get("VOICEDNA_API_KEY"))


def parse_json(text: str) -> Any:
    """剥 markdown 包裹后解析 JSON（LLM 常把 JSON 包 ```json 里）。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # 去开头 ```json 或 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def call_llm(
    prompt: str,
    *,
    base_url: str = "",
    model: str = "",
    key: str = "",
    system: str = "",
    temperature: float = 0.3,
) -> str:
    """调 OpenAI 兼容 /chat/completions，返回 message.content。

    base_url/model/key 缺省从 os.environ VOICEDNA_* 取（主 provider）；显式传入即覆盖
    （judge 独立 provider 用）。无 key 抛 ValueError。
    """
    if not base_url:
        base_url = os.environ.get("VOICEDNA_BASE_URL", "")
    if not model:
        model = os.environ.get("VOICEDNA_MODEL", "")
    if not key:
        key = os.environ.get("VOICEDNA_API_KEY", "")
    if not key:
        raise ValueError("未配置 LLM key")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage") or {}
    _usage["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    _usage["completion_tokens"] += int(usage.get("completion_tokens") or 0)
    return data["choices"][0]["message"]["content"]
