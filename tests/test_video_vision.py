"""video_vision tool 测试 — VOICEDNA_VISION 成本门、抽帧命令、逐帧聚合、无 key 降级。"""

import pytest

from src.tools import video_vision
from src.tools.video_vision import run


def test_missing_path_raises():
    with pytest.raises(ValueError):
        run()


def test_vision_default_off_returns_empty(monkeypatch):
    monkeypatch.delenv("VOICEDNA_VISION", raising=False)
    run_calls: list[list[str]] = []
    monkeypatch.setattr(video_vision.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    out = run(path="/tmp/v.mp4")
    assert out == {}
    assert run_calls == []


def test_vision_zero_short_circuits(monkeypatch):
    monkeypatch.setenv("VOICEDNA_VISION", "0")
    run_calls: list[list[str]] = []
    monkeypatch.setattr(video_vision.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    out = run(path="/tmp/v.mp4")
    assert out == {}
    assert run_calls == []


def test_no_key_graceful_empty(monkeypatch):
    monkeypatch.setenv("VOICEDNA_VISION", "1")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    out = run(path="/tmp/v.mp4")
    assert out == {}


def test_extract_frames_ffmpeg_command(monkeypatch, tmp_path):
    monkeypatch.setattr(video_vision, "_ffmpeg_bin", lambda: "ffmpeg")
    run_calls: list[list[str]] = []
    monkeypatch.setattr(video_vision.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    frames = video_vision._extract_frames("/tmp/v.mp4", str(tmp_path), fps=1 / 3)
    assert frames == []
    assert len(run_calls) == 1
    cmd = run_calls[0]
    assert cmd[0] == "ffmpeg"
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1].startswith("fps=")
    assert cmd[-1].endswith(".jpg")


def test_run_aggregates_per_frame_descriptions(monkeypatch):
    monkeypatch.setenv("VOICEDNA_VISION", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(
        video_vision, "_extract_frames", lambda media, outdir, fps: ["/tmp/f1.jpg", "/tmp/f2.jpg"]
    )
    described: list[str] = []

    def fake_describe(jpg, key):
        described.append(jpg)
        return f"desc:{jpg}"

    monkeypatch.setattr(video_vision, "_describe_frame", fake_describe)
    monkeypatch.setattr(
        video_vision,
        "_summarize",
        lambda descs, key: {"shot_rhythm": "快切", "visual_style": "冷色"},
    )
    out = run(path="/tmp/v.mp4")
    assert out == {
        "shot_rhythm": "快切",
        "visual_style": "冷色",
        "scenes": ["desc:/tmp/f1.jpg", "desc:/tmp/f2.jpg"],
    }
    assert described == ["/tmp/f1.jpg", "/tmp/f2.jpg"]
