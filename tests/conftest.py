"""测试级环境清理：VOICEDNA_LLM_* 档位/开关只存内存（os.environ），
确保跨测试不互相污染（set_mode/set_agent 直写 env，须手动清）。"""

import os

import pytest


@pytest.fixture(autouse=True)
def _clean_llm_env():
    saved = {k: os.environ[k] for k in list(os.environ) if k.startswith("VOICEDNA_LLM_")}
    for k in saved:
        del os.environ[k]
    yield
    # 只恢复测试前已存在的值；测试内 set_mode/set_agent 直写的内容被丢弃。
    for k, value in saved.items():
        os.environ[k] = value
