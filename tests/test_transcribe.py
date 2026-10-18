"""transcribe tool 测试 — url/本地分支、ffmpeg 抽音轨、本地/云端分派、后端回落。"""

import sys
import types

import pytest

from src.tools import transcribe
from src.tools.transcribe import run


def _install_fake_dashscope(monkeypatch, recognition_cls, callback_cls):
    """把 dashscope.audio.asr 换成假模块，隔离可选依赖（测试不要求真装 dashscope）。"""
    asr = types.ModuleType("dashscope.audio.asr")
    asr.Recognition = recognition_cls
    asr.RecognitionCallback = callback_cls
    audio = types.ModuleType("dashscope.audio")
    audio.asr = asr
    dashscope = types.ModuleType("dashscope")
    dashscope.audio = audio
    monkeypatch.setitem(sys.modules, "dashscope", dashscope)
    monkeypatch.setitem(sys.modules, "dashscope.audio", audio)
    monkeypatch.setitem(sys.modules, "dashscope.audio.asr", asr)


def test_missing_source_raises():
    with pytest.raises(ValueError):
        run()


def test_local_wav_defaults_to_asr_local(monkeypatch):
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "你好世界")
    called_cloud: list[str] = []
    monkeypatch.setattr(transcribe, "_asr_cloud", lambda wav: called_cloud.append("x") or "云")
    out = run(source="/tmp/a.wav")
    assert out == {"text": "你好世界", "source": "/tmp/a.wav", "backend": "local"}
    assert called_cloud == []


def test_cloud_backend_dispatches_to_asr_cloud(monkeypatch):
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "本地")
    monkeypatch.setattr(transcribe, "_asr_cloud", lambda wav: "云")
    out = run(source="/tmp/a.wav", backend="cloud")
    assert out == {"text": "云", "source": "/tmp/a.wav", "backend": "cloud"}


def test_cloud_backend_requires_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        transcribe._asr_cloud("/tmp/a.wav")


def test_asr_cloud_streams_and_joins_sentence_end(monkeypatch, tmp_path):
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"A" * 7000)  # 3 个 3200 字节块
    frames: list[bytes] = []
    init_kwargs: dict = {}

    class _FakeCallback:
        def __init__(self):
            self.events: list[dict] = []

    class _FakeResult:
        def __init__(self, sentence):
            self.sentence = sentence

        def get_sentence(self):
            return self.sentence

    class _FakeRecognition:
        def __init__(self, model, format, sample_rate, callback):
            init_kwargs.update(
                model=model, format=format, sample_rate=sample_rate, callback=callback
            )
            self.callback = callback

        def start(self):
            pass

        def send_audio_frame(self, buffer):
            frames.append(buffer)

        def stop(self):
            cb = self.callback
            # 流式中间态（sentence_end=False）+ 完整句（True）
            cb.on_event(_FakeResult({"text": "你好", "sentence_end": False}))
            cb.on_event(_FakeResult({"text": "你好世界", "sentence_end": True}))

    _install_fake_dashscope(monkeypatch, _FakeRecognition, _FakeCallback)

    out = transcribe._asr_cloud(str(wav))
    assert out == "你好世界"
    assert init_kwargs["model"] == "paraformer-realtime-v2"
    assert init_kwargs["format"] == "wav"
    assert init_kwargs["sample_rate"] == 16000
    assert frames == [b"A" * 3200, b"A" * 3200, b"A" * 600]


def test_asr_cloud_raises_on_error(monkeypatch, tmp_path):
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"A" * 3200)

    class _FakeCallback:
        pass

    class _FakeResult:
        def __init__(self, code, message):
            self.code = code
            self.message = message

    class _FakeRecognition:
        def __init__(self, **kw):
            self.callback = kw["callback"]

        def start(self):
            pass

        def send_audio_frame(self, buffer):
            pass

        def stop(self):
            self.callback.on_error(_FakeResult("InvalidParameter", "bad audio"))

    _install_fake_dashscope(monkeypatch, _FakeRecognition, _FakeCallback)

    with pytest.raises(RuntimeError, match="DashScope ASR 失败"):
        transcribe._asr_cloud(str(wav))


def test_unknown_backend_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "本地")
    monkeypatch.setattr(transcribe, "_asr_cloud", lambda wav: "云")
    out = run(source="/tmp/a.wav", backend="bogus")
    assert out["backend"] == "local"
    assert out["text"] == "本地"


def test_url_source_calls_download(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(transcribe, "_download", lambda u: calls.append(u) or "/tmp/d.wav")
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "文字")
    out = run(source="https://example.com/v.mp4")
    assert calls == ["https://example.com/v.mp4"]
    assert out["text"] == "文字"


def test_local_path_skips_download(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(transcribe, "_download", lambda u: called.append(u) or "/tmp/d.wav")
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "文字")
    run(source="/tmp/本地.wav")
    assert called == []


def test_video_source_extracts_wav_via_ffmpeg(monkeypatch):
    run_calls: list[list[str]] = []
    monkeypatch.setattr(transcribe, "_ffmpeg_bin", lambda: "ffmpeg")
    monkeypatch.setattr(transcribe.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "文字")
    out = run(source="/tmp/v.mp4")
    assert out["text"] == "文字"
    assert len(run_calls) == 1
    cmd = run_calls[0]
    assert cmd[0] == "ffmpeg"
    assert "-ac" in cmd and "1" in cmd
    assert "-ar" in cmd and "16000" in cmd
    assert cmd[-1].endswith(".wav")


def test_wav_source_skips_ffmpeg(monkeypatch):
    run_calls: list[list[str]] = []
    monkeypatch.setattr(transcribe, "_ffmpeg_bin", lambda: "ffmpeg")
    monkeypatch.setattr(transcribe.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    monkeypatch.setattr(transcribe, "_asr_local", lambda wav: "文字")
    run(source="/tmp/a.wav")
    assert run_calls == []


def test_asr_local_posts_wav_to_funasr(monkeypatch, tmp_path):
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF")
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "你好"}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["files"] = kw["files"]
        return _Resp()

    monkeypatch.setattr(transcribe.httpx, "post", fake_post)
    out = transcribe._asr_local(str(wav))
    assert out == "你好"
    assert captured["url"] == "http://127.0.0.1:8000/v1/audio/transcriptions"
    assert "file" in captured["files"]
