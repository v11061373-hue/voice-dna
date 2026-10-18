"""个人账号配置 — provider / base_url / model / key + judge 组（D1/D2/D4）。

key 铁律：key 只落 os.environ（内存，重启失效），不进 sessions.db/checkpoints.db，
不写任何 json 文件。provider/base_url/model 非密，也一并放 os.environ（PLAN §六无持久化要求）。
"""

from __future__ import annotations

import os
from typing import Any

# 供应商预设（全 OpenAI 兼容，加一个 = 一行）。base_url 不含 /chat/completions 末段。
PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "qwen": {"label": "通义 Qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "glm": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "kimi": {"label": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "hunyuan": {"label": "腾讯混元", "base_url": "https://api.hunyuan.cloud.tencent.com/v1", "model": "hunyuan-lite"},
    "custom": {"label": "OpenAI 兼容", "base_url": "", "model": ""},
}

_ENV = {
    "provider": "VOICEDNA_PROVIDER",
    "base_url": "VOICEDNA_BASE_URL",
    "model": "VOICEDNA_MODEL",
    "key": "VOICEDNA_API_KEY",
    "judge_provider": "VOICEDNA_JUDGE_PROVIDER",
    "judge_base_url": "VOICEDNA_JUDGE_BASE_URL",
    "judge_model": "VOICEDNA_JUDGE_MODEL",
    "judge_key": "VOICEDNA_JUDGE_API_KEY",
}


def set_config(
    provider: str = "",
    base_url: str = "",
    model: str = "",
    key: str = "",
    judge_provider: str = "",
    judge_base_url: str = "",
    judge_key: str = "",
) -> None:
    """写配置到 os.environ（内存）。key 传入才覆盖，空串不动旧 key。"""
    preset = PROVIDERS.get(provider, PROVIDERS["custom"])
    os.environ[_ENV["provider"]] = provider or "custom"
    os.environ[_ENV["base_url"]] = base_url or preset["base_url"]
    os.environ[_ENV["model"]] = model or preset["model"]
    if key:
        os.environ[_ENV["key"]] = key

    jprovider = judge_provider or provider or "custom"
    jpreset = PROVIDERS.get(jprovider, PROVIDERS["custom"])
    os.environ[_ENV["judge_provider"]] = jprovider
    os.environ[_ENV["judge_base_url"]] = judge_base_url or jpreset["base_url"] or os.environ[_ENV["base_url"]]
    os.environ[_ENV["judge_model"]] = jpreset["model"] or os.environ[_ENV["model"]]
    if judge_key:
        os.environ[_ENV["judge_key"]] = judge_key


def main_settings() -> tuple[str, str, str]:
    """主 LLM (base_url, model, key)。"""
    return (
        os.environ.get(_ENV["base_url"], ""),
        os.environ.get(_ENV["model"], ""),
        os.environ.get(_ENV["key"], ""),
    )


def judge_settings() -> tuple[str, str, str]:
    """judge (base_url, model, key)。key 缺省回退主 key。"""
    return (
        os.environ.get(_ENV["judge_base_url"], ""),
        os.environ.get(_ENV["judge_model"], ""),
        os.environ.get(_ENV["judge_key"], "") or os.environ.get(_ENV["key"], ""),
    )


def get_config() -> dict[str, Any]:
    """/api/config GET 用 — key 只回「已配/未配」，不吐明文。"""
    def masked(env_key: str) -> str:
        return "已配" if os.environ.get(env_key) else "未配"

    return {
        "provider": os.environ.get(_ENV["provider"], ""),
        "base_url": os.environ.get(_ENV["base_url"], ""),
        "model": os.environ.get(_ENV["model"], ""),
        "key": masked(_ENV["key"]),
        "judge_provider": os.environ.get(_ENV["judge_provider"], ""),
        "judge_base_url": os.environ.get(_ENV["judge_base_url"], ""),
        "judge_model": os.environ.get(_ENV["judge_model"], ""),
        "judge_key": masked(_ENV["judge_key"]),
        "providers": [
            {"id": pid, "label": p["label"], "base_url": p["base_url"], "model": p["model"]}
            for pid, p in PROVIDERS.items()
        ],
    }
