"""video_vision tool — 视频抽帧 + Qwen-VL 逐帧描述 → 分镜节奏风格卡（P5-D）。

成本门：VOICEDNA_VISION=1 才启用（默认关，未设 / 0 都回空 dict），不开不调 API。
链路：ffmpeg 按 fps 抽 jpg（imageio_ffmpeg 自带二进制，模式同 transcribe）
  → 逐帧 Qwen-VL-Max 描述画面/景别/转场 → 汇总 shot_rhythm / visual_style。

铁律：DASHSCOPE_API_KEY 只 os.environ；抽帧落 tempfile 用完删。
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from src.llm import parse_json

QWEN_VL_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_VL_MODEL = "qwen3-vl-plus"

_FRAME_PROMPT = "一句话描述该帧画面内容、景别（远景/中景/特写）与镜头运动/转场。"
_SUMMARY_PROMPT = (
    "以下是同一视频逐帧画面描述，请仅输出 JSON（不要 markdown 包裹），"
    '形如 {"shot_rhythm": "分镜节奏一句话", "visual_style": "视觉风格一句话"}：\n'
)


def _ffmpeg_bin() -> str:
    """ffmpeg 二进制：env 优先，其次 imageio_ffmpeg 自带，最后系统 ffmpeg（同 transcribe）。"""
    exe = os.environ.get("VOICEDNA_FFMPEG")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 — 未装 imageio_ffmpeg 时退回系统 ffmpeg
        return "ffmpeg"


def _vision_enabled() -> bool:
    """成本门：仅 VOICEDNA_VISION=1 开启，默认关。"""
    return os.environ.get("VOICEDNA_VISION") == "1"


def _extract_frames(media: str, outdir: str, fps: float) -> list[str]:
    """ffmpeg 按 fps 抽 jpg 帧到 outdir，返回帧文件路径（升序）。"""
    pattern = os.path.join(outdir, "frame_%04d.jpg")
    subprocess.run(
        [_ffmpeg_bin(), "-y", "-i", media, "-vf", f"fps={fps}", pattern],
        capture_output=True,
        check=True,
    )
    return sorted(str(p) for p in Path(outdir).glob("frame_*.jpg"))


def _image_b64(jpg: str) -> str:
    with open(jpg, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _call_qwen(messages: list[dict[str, Any]], key: str) -> str:
    resp = httpx.post(
        QWEN_VL_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": QWEN_VL_MODEL, "messages": messages},
        timeout=120,
    )
    resp.raise_for_status()
    return str(resp.json()["choices"][0]["message"]["content"])


def _describe_frame(jpg: str, key: str) -> str:
    img = _image_b64(jpg)
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}},
                {"type": "text", "text": _FRAME_PROMPT},
            ],
        }
    ]
    return _call_qwen(messages, key)


def _summarize(descriptions: list[str], key: str) -> dict[str, str]:
    joined = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    raw = _call_qwen([{"role": "user", "content": _SUMMARY_PROMPT + joined}], key)
    return dict(parse_json(raw))


def run(path: str = "", fps: float = 1 / 3, **kwargs: Any) -> dict[str, Any]:
    """视频文件 → 分镜节奏风格卡 {"shot_rhythm", "visual_style", "scenes"}。

    默认关（VOICEDNA_VISION≠1）或无 DASHSCOPE_API_KEY 时回空 dict，不调 API。
    """
    if not path:
        raise ValueError("video_vision 需要 path（视频文件绝对路径）")
    if not _vision_enabled():
        return {}
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        frames = _extract_frames(path, outdir=tmp, fps=fps)
        descriptions = [_describe_frame(f, key) for f in frames]
    summary = _summarize(descriptions, key)
    return {
        "shot_rhythm": summary.get("shot_rhythm", ""),
        "visual_style": summary.get("visual_style", ""),
        "scenes": descriptions,
    }
