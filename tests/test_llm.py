"""通用 OpenAI 兼容 client 测试（D3）。"""

import httpx
import pytest

from src import llm


def _capture_post(monkeypatch, content):
    """替换 httpx.post，捕获 URL + kwargs，返回 content。"""
    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


def test_call_llm_posts_chat_completions(monkeypatch):
    captured = _capture_post(monkeypatch, "hi")
    out = llm.call_llm("prompt", base_url="https://api.deepseek.com", model="deepseek-chat", key="sk")
    assert out == "hi"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer sk"
    body = captured["kwargs"]["json"]
    assert body["model"] == "deepseek-chat"
    assert body["messages"] == [{"role": "user", "content": "prompt"}]


def test_call_llm_uses_env_defaults(monkeypatch):
    monkeypatch.setenv("VOICEDNA_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("VOICEDNA_MODEL", "deepseek-chat")
    monkeypatch.setenv("VOICEDNA_API_KEY", "sk-env")
    captured = _capture_post(monkeypatch, "x")
    llm.call_llm("p")
    body = captured["kwargs"]["json"]
    assert body["model"] == "deepseek-chat"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer sk-env"


def test_call_llm_raises_without_key(monkeypatch):
    monkeypatch.delenv("VOICEDNA_API_KEY", raising=False)
    with pytest.raises(ValueError):
        llm.call_llm("p")


def test_call_llm_system_message(monkeypatch):
    captured = _capture_post(monkeypatch, "x")
    llm.call_llm("p", base_url="b", model="m", key="k", system="你是专家")
    msgs = captured["kwargs"]["json"]["messages"]
    assert msgs[0] == {"role": "system", "content": "你是专家"}
    assert msgs[1] == {"role": "user", "content": "p"}


def test_has_key(monkeypatch):
    monkeypatch.delenv("VOICEDNA_API_KEY", raising=False)
    assert llm.has_key() is False
    monkeypatch.setenv("VOICEDNA_API_KEY", "sk")
    assert llm.has_key() is True


def test_call_llm_tracks_usage(monkeypatch):
    """call_llm 累加 usage（prompt+completion tokens），供 G4 成本预算计量。"""

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp())
    monkeypatch.setattr(llm, "_usage", {"prompt_tokens": 0, "completion_tokens": 0})
    llm.call_llm("p", base_url="b", model="m", key="k")
    assert llm.total_tokens() == 15
