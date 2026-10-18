"""video_download tool 测试 — 平台分派、cookie 单路径、tempfile 落盘用完删。"""

import os
import tempfile

import pytest

from src.tools import video_download
from src.tools.video_download import cleanup, run


@pytest.fixture(autouse=True)
def _clean_download_dir():
    video_download.cleanup()
    yield
    video_download.cleanup()


def _write(path):
    with open(path, "wb") as f:
        f.write(b"data")
    return path


def test_is_video_url_extracts_link():
    assert (
        video_download.is_video_url("看这个 https://www.bilibili.com/video/BV1xx411c7mD 视频")
        == "https://www.bilibili.com/video/BV1xx411c7mD"
    )
    assert video_download.is_video_url("https://v.douyin.com/abcd/") == "https://v.douyin.com/abcd/"
    assert (
        video_download.is_video_url("https://www.xiaohongshu.com/explore/abc")
        == "https://www.xiaohongshu.com/explore/abc"
    )
    assert video_download.is_video_url("https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"


def test_is_video_url_ignores_non_video():
    assert video_download.is_video_url("美妆博主") is None
    assert video_download.is_video_url("看 https://example.com/x 这个") is None


def test_platform_dispatch():
    assert video_download._platform("https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili"
    assert video_download._platform("https://v.douyin.com/abcd123/") == "douyin"
    assert video_download._platform("https://www.douyin.com/video/123") == "douyin"
    assert video_download._platform("https://www.xiaohongshu.com/explore/abc") == "xhs"
    assert video_download._platform("https://xhslink.com/abc") == "xhs"
    assert video_download._platform("https://example.com/v") == "unknown"


def test_run_dispatches_bilibili_vs_douyin(monkeypatch):
    calls = []
    monkeypatch.setattr(
        video_download,
        "_download_bilibili",
        lambda url, outdir: calls.append("bilibili") or os.path.join(outdir, "a.mp4"),
    )
    monkeypatch.setattr(
        video_download,
        "_download_douyin_or_xhs",
        lambda url, outdir: calls.append("douyin") or os.path.join(outdir, "a.mp4"),
    )
    run("https://www.bilibili.com/video/BV1xx411c7mD")
    run("https://v.douyin.com/abcd/")
    assert calls == ["bilibili", "douyin"]


def test_run_rejects_unknown_platform():
    with pytest.raises(video_download.VideoDownloadError):
        run("https://example.com/v")


def test_run_requires_url():
    with pytest.raises(ValueError):
        run()


def test_download_lands_in_tempfile_and_cleanup(monkeypatch):
    monkeypatch.setattr(
        video_download,
        "_download_bilibili",
        lambda url, outdir: _write(os.path.join(outdir, "v.mp4")),
    )
    out = run("https://www.bilibili.com/video/BV1xx411c7mD")
    path = out["path"]
    assert tempfile.gettempdir() in path
    assert "voice-dna-repo" not in path
    assert os.path.exists(path)
    cleanup()
    assert not os.path.exists(path)


def test_douyin_without_cookie_raises_guidance(monkeypatch):
    from src.cookies import COOKIE_PATH

    monkeypatch.setattr(video_download, "get_cookie", lambda p: None)
    with pytest.raises(video_download.VideoDownloadError) as e:
        video_download._download_douyin_or_xhs("https://www.douyin.com/video/123", "/tmp")
    assert str(COOKIE_PATH) in str(e.value)


def test_douyin_with_cookie_raises_not_wired(monkeypatch):
    monkeypatch.setattr(video_download, "get_cookie", lambda p: "cookie=abc")
    with pytest.raises(video_download.VideoDownloadError) as e:
        video_download._download_douyin_or_xhs("https://www.douyin.com/video/123", "/tmp")
    assert "未接线" in str(e.value)


def _fake_get_json(url, params):
    if "view" in url:
        assert params["bvid"] == "BV1xx411c7mD"
        return {"code": 0, "data": {"cid": 123, "title": "t"}}
    if "playurl" in url:
        assert params["cid"] == 123
        assert params["fnval"] == 0
        return {"code": 0, "data": {"durl": [{"url": "https://upos/x.mp4"}]}}
    raise AssertionError(f"unexpected url {url}")


def test_download_bilibili_parses_and_writes(monkeypatch, tmp_path):
    fetched = []
    monkeypatch.setattr(video_download, "_get_json", _fake_get_json)
    monkeypatch.setattr(video_download, "_fetch_bytes", lambda u: fetched.append(u) or b"MP4DATA")
    path = video_download._download_bilibili(
        "https://www.bilibili.com/video/BV1xx411c7mD", str(tmp_path)
    )
    assert fetched == ["https://upos/x.mp4"]
    assert path == os.path.join(str(tmp_path), "BV1xx411c7mD.mp4")
    with open(path, "rb") as f:
        assert f.read() == b"MP4DATA"
