"""剪辑 Pattern 数据模型 — 从示范视频学习的 BGM 剪辑逻辑"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class AudioEntryInfo(BaseModel):
    """BGM 切入方式"""
    entry_type: str = "immediate"      # immediate / fade_in / delayed / on_beat
    entry_time_ratio: float = 0.0      # 0-1, 切入点在 BGM 中的位置
    fade_duration_sec: float = 0.0     # 淡入时长（秒）
    start_volume: float = 1.0          # 初始音量


class ClimaxAlignment(BaseModel):
    """高潮对齐"""
    bgm_climax_ratio: float = 0.5      # BGM 高潮位置（0-1）
    video_peak_ratio: float = 0.5      # 画面高潮位置（0-1）
    alignment_offset_sec: float = 0.0  # 音视频峰值偏移（秒）
    sync_tolerance_sec: float = 0.15   # 卡点容差（秒）


class VolumeSegment(BaseModel):
    """音量自动化规则"""
    time_ratio: float = 0.0            # 位置（0-1）
    volume: float = 1.0                # 目标音量
    segment_type: str = "normal"       # normal / duck / boost / fade_in / fade_out


class BeatSyncRule(BaseModel):
    """卡点规则"""
    sync_type: str = "none"            # beat_to_cut / energy_rise_to_transition / none
    strength: float = 0.0              # 0-1，卡点强度


class EditingPattern(BaseModel):
    """完整的剪辑 Pattern"""
    id: str = ""
    name: str = ""
    description: str = ""
    created_at: str = ""
    audio_entry: AudioEntryInfo = AudioEntryInfo()
    climax_alignment: ClimaxAlignment = ClimaxAlignment()
    volume_segments: List[VolumeSegment] = []
    beat_sync: BeatSyncRule = BeatSyncRule()
    demo_duration_sec: float = 0.0
    demo_video_id: Optional[str] = None
    detection_confidence: float = 0.5
