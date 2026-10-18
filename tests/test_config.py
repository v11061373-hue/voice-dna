"""个人账号配置测试 — provider 预设 + set/get + key 铁律 + judge 组（D1/D2/D4）。"""

import json
import os

from src import config


def _isolate(monkeypatch):
    """copy 环境到新 dict，set_config 的 os.environ 写不会泄漏到其它测试。"""
    monkeypatch.setattr(os, "environ", os.environ.copy())


def test_providers_have_all_presets():
    for pid in ("deepseek", "qwen", "glm", "kimi", "hunyuan", "custom"):
        assert pid in config.PROVIDERS
        p = config.PROVIDERS[pid]
        assert p["label"]
        assert "base_url" in p and "model" in p
    # 预设供应商 base_url/model 非空；custom 留空由用户填
    for pid in ("deepseek", "qwen", "glm", "kimi", "hunyuan"):
        assert config.PROVIDERS[pid]["base_url"]
        assert config.PROVIDERS[pid]["model"]


def test_set_config_deepseek_resolves_preset(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(provider="deepseek", key="sk-abc")
    assert os.environ["VOICEDNA_BASE_URL"] == "https://api.deepseek.com"
    assert os.environ["VOICEDNA_MODEL"] == "deepseek-chat"
    assert os.environ["VOICEDNA_API_KEY"] == "sk-abc"


def test_set_config_custom_requires_base_url_model(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(provider="custom", base_url="https://x.example/v1", model="my-model", key="k")
    assert os.environ["VOICEDNA_BASE_URL"] == "https://x.example/v1"
    assert os.environ["VOICEDNA_MODEL"] == "my-model"
    assert os.environ["VOICEDNA_API_KEY"] == "k"


def test_set_config_explicit_base_url_overrides_preset(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(provider="qwen", base_url="https://proxy.example/v1", key="qk")
    assert os.environ["VOICEDNA_BASE_URL"] == "https://proxy.example/v1"
    assert os.environ["VOICEDNA_MODEL"] == "qwen-plus"  # model 仍走 preset


def test_get_config_masks_key(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(provider="deepseek", key="sk-secret-123")
    got = config.get_config()
    assert got["key"] == "已配"
    assert "sk-secret-123" not in json.dumps(got, ensure_ascii=False)


def test_get_config_unconfigured_key_masked(monkeypatch):
    _isolate(monkeypatch)
    got = config.get_config()
    assert got["key"] == "未配"
    assert got["judge_key"] == "未配"


def test_judge_defaults_to_main(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(provider="deepseek", key="sk-main")
    assert config.judge_settings() == config.main_settings()


def test_judge_independent_provider(monkeypatch):
    _isolate(monkeypatch)
    config.set_config(
        provider="deepseek", key="sk-main", judge_provider="qwen", judge_key="sk-judge"
    )
    base, model, key = config.judge_settings()
    assert key == "sk-judge"
    assert model == "qwen-plus"
    assert base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.main_settings()[2] == "sk-main"  # 主配置不被 judge 影响
