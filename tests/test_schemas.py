"""编排状态 schema 契约测试（P5-E 视频摄入状态字段）。"""

from typing import Any

from src.schemas import SocialMediaState


def test_state_declares_video_fields():
    """P5-E 新增状态字段齐全：候选视频 / 转录逐字稿 / 视觉分镜卡 / v1 脚本快照。"""
    ann = SocialMediaState.__annotations__
    assert "candidate_videos" in ann
    assert "transcripts" in ann
    assert "video_visual" in ann
    assert "v1_script" in ann


def test_state_video_field_types():
    """新字段类型正确：candidate_videos=list[dict]，transcripts=dict[str,str]。"""
    ann = SocialMediaState.__annotations__
    assert ann["candidate_videos"] == list[dict[str, Any]]
    assert ann["transcripts"] == dict[str, str]
    assert ann["video_visual"] == dict[str, Any]
    assert ann["v1_script"] == dict[str, Any]
