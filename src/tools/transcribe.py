"""transcribe tool — 视频/音频 → 文字（本地 funasr 默认，云端 DashScope 可选）。

后端：
- 本地 funasr-server（:8000 /v1/audio/transcriptions）默认，调用契约复用
  dy_transcribe.py 已验证的 multipart 上传（file 字段 + filename）。
- 云端 DashScope 流式（paraformer-realtime-v2，Recognition + RecognitionCallback），
  backend="cloud" 显式切，key 走 DASHSCOPE_API_KEY。

铁律：临时 wav 落 tempfile 用完删（TemporaryDirectory 上下文自动清）；
key 只 os.environ、cookie 只 ~/.voice-dna/cookies.json（下载在 P5-C，此处只留 seam）。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

FUNASR_URL = "http://127.0.0.1:8000/v1/audio/transcriptions"

DASHSCOPE_ASR_MODEL = "paraformer-realtime-v2"
DASHSCOPE_ASR_FORMAT = "wav"
DASHSCOPE_ASR_SAMPLE_RATE = 16000


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _needs_extract(path: str) -> bool:
    """非 wav（视频/m4a 等）需 ffmpeg 抽 16k 单声道 wav；wav 直接用。"""
    return Path(path).suffix.lower() != ".wav"


def _download(source: str) -> str:
    """url → 本地媒体文件路径。P5-C download_video 落地，此处 lazy import 作 seam。"""
    from src.tools import video_download  # type: ignore[attr-defined]  # P5-C 落地

    return str(video_download.run(source)["path"])


def _ffmpeg_bin() -> str:
    """ffmpeg 二进制：env 优先，其次 imageio_ffmpeg 自带，最后系统 ffmpeg。"""
    exe = os.environ.get("VOICEDNA_FFMPEG")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 — 未装 imageio_ffmpeg 时退回系统 ffmpeg
        return "ffmpeg"


def _extract_wav(media: str, outdir: str) -> str:
    """视频/非 wav 音频 → 16k 单声道 wav（写进 outdir，用完随 TemporaryDirectory 清）。"""
    wav = os.path.join(outdir, "audio.wav")
    subprocess.run(
        [_ffmpeg_bin(), "-y", "-i", media, "-ac", "1", "-ar", "16000", wav],
        capture_output=True,
        check=True,
    )
    return wav


def _asr_local(wav: str) -> str:
    """本地 funasr-server multipart 上传，回 {text}。契约同 dy_transcribe.py。"""
    with open(wav, "rb") as f:
        resp = httpx.post(
            FUNASR_URL,
            files={"file": (os.path.basename(wav), f, "audio/wav")},
            timeout=600,
        )
    resp.raise_for_status()
    data = resp.json()
    return str(data.get("text", "")) if isinstance(data, dict) else str(data)


def _asr_cloud(wav: str) -> str:
    """云端 DashScope 流式 ASR — 只回句末（sentence_end=True）文本拼接。

    dashscope SDK 懒加载（可选依赖）；key 走 DASHSCOPE_API_KEY（SDK 默认读 env）。
    """
    if not os.environ.get("DASHSCOPE_API_KEY"):
        raise RuntimeError("云端 ASR 需要 DASHSCOPE_API_KEY 环境变量")
    try:
        from dashscope.audio.asr import Recognition, RecognitionCallback
    except Exception as e:
        raise RuntimeError("云端 ASR 需要 dashscope SDK（pip install dashscope）") from e

    sentences: list[str] = []
    errors: list[str] = []

    class _Callback(RecognitionCallback):
        def on_event(self, result: Any) -> None:
            sentence = result.get_sentence()
            if (
                isinstance(sentence, dict)
                and sentence.get("sentence_end")
                and sentence.get("text")
            ):
                sentences.append(sentence["text"])

        def on_error(self, result: Any) -> None:
            errors.append(f"{getattr(result, 'code', '')} {getattr(result, 'message', '')}")

    recognition = Recognition(
        model=DASHSCOPE_ASR_MODEL,
        format=DASHSCOPE_ASR_FORMAT,
        sample_rate=DASHSCOPE_ASR_SAMPLE_RATE,
        callback=_Callback(),
    )
    recognition.start()
    with open(wav, "rb") as f:
        while chunk := f.read(3200):
            recognition.send_audio_frame(chunk)
    recognition.stop()
    if errors:
        raise RuntimeError(f"DashScope ASR 失败: {errors[-1]}")
    return "".join(sentences)


def _asr(wav: str, backend: str) -> tuple[str, str]:
    """按 backend 分派，返回 (text, 实际后端)。非 cloud 一律回落本地。"""
    if backend == "cloud":
        return _asr_cloud(wav), "cloud"
    return _asr_local(wav), "local"


def run(source: str = "", backend: str = "local", **kwargs: Any) -> dict[str, Any]:
    """视频/音频 url 或本地文件 → {"text", "source", "backend"}。"""
    if not source:
        raise ValueError("transcribe 需要 source（视频/音频 url 或本地文件路径）")
    media = _download(source) if _is_url(source) else source
    if _needs_extract(media):
        with tempfile.TemporaryDirectory() as tmp:
            text, used = _asr(_extract_wav(media, outdir=tmp), backend)
    else:
        text, used = _asr(media, backend)
    return {"text": text, "source": source, "backend": used}
