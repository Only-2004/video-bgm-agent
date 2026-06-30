"""将学到的 EditingPattern 应用到新视频+BGM，生成剪辑计划"""

import numpy as np
from models.patterns import (
    EditingPattern, VolumeSegment, AudioEntryInfo,
    ClimaxAlignment, BeatSyncRule,
)


class PatternApplier:
    """将 Pattern 适配到新视频的 BGM"""

    def generate_plan(
        self,
        pattern: EditingPattern,
        video_duration: float,
        bgm_duration: float,
        bgm_beat_times: list = None,
        voice_segments: list = None,
    ) -> dict:
        """
        生成剪辑计划

        Args:
            pattern: 学到的剪辑模式
            video_duration: 新视频时长（秒）
            bgm_duration: 新 BGM 时长（秒）
            bgm_beat_times: 新 BGM 的鼓点时间列表
            voice_segments: 视频中有人声的片段 [(start, end), ...]

        Returns:
            剪辑计划 dict
        """
        # 1. 切入点：按比例缩放
        entry_point = self._scale_entry(pattern, bgm_duration)

        # 2. 音量曲线：Pattern 规则 + 人声 ducking
        volume_automations = self._build_volume_curve(
            pattern, bgm_duration, voice_segments
        )

        # 3. 高潮对齐：计算需要的偏移
        climax_plan = self._plan_climax_alignment(
            pattern, video_duration, bgm_duration
        )

        # 4. 卡点同步：标注需要卡点的位置
        beat_sync_plan = self._plan_beat_sync(
            pattern, bgm_beat_times, video_duration
        )

        return {
            "entry": entry_point,
            "volume_automations": volume_automations,
            "climax_alignment": climax_plan,
            "beat_sync": beat_sync_plan,
            "source_pattern": {
                "id": pattern.id,
                "name": pattern.name,
                "confidence": pattern.detection_confidence,
            },
        }

    def _scale_entry(self, pattern: EditingPattern, bgm_duration: float) -> dict:
        """按比例计算切入点"""
        entry = pattern.audio_entry
        entry_time = entry.entry_time_ratio * bgm_duration

        return {
            "type": entry.entry_type,
            "time_sec": round(entry_time, 2),
            "time_ratio": entry.entry_time_ratio,
            "fade_duration": entry.fade_duration_sec,
            "start_volume": entry.start_volume,
        }

    def _build_volume_curve(
        self,
        pattern: EditingPattern,
        bgm_duration: float,
        voice_segments: list = None,
    ) -> list:
        """
        构建音量自动化曲线

        合并两层规则：
        1. Pattern 学到的 ducking/boost 段
        2. 视频人声区段的 ducking（硬规则）
        """
        automations = []

        # Pattern 规则（按时间比例缩放）
        for seg in pattern.volume_segments:
            automations.append({
                "time_sec": round(seg.time_ratio * bgm_duration, 2),
                "time_ratio": seg.time_ratio,
                "volume": seg.volume,
                "type": seg.segment_type,
                "source": "pattern",
            })

        # 人声 ducking（优先级更高）
        if voice_segments:
            for start, end in voice_segments:
                automations.append({
                    "time_sec": round(start, 2),
                    "time_ratio": round(start / bgm_duration, 3) if bgm_duration > 0 else 0,
                    "volume": 0.25,
                    "type": "duck",
                    "source": "voice_detection",
                    "end_sec": round(end, 2),
                })

        # 按时间排序
        automations.sort(key=lambda x: x["time_sec"])
        return automations

    def _plan_climax_alignment(
        self,
        pattern: EditingPattern,
        video_duration: float,
        bgm_duration: float,
    ) -> dict:
        """
        计划高潮对齐

        目标：BGM 高潮位置与视频运动峰值对齐
        """
        climax = pattern.climax_alignment

        # Pattern 中的 BGM 高潮位置（比例）
        bgm_climax_time = climax.bgm_climax_ratio * bgm_duration

        # 期望视频峰值出现的时间
        # 如果知道视频运动曲线，可以直接用；否则用 0.5（中间）
        expected_video_peak = climax.video_peak_ratio * video_duration

        # 推荐的偏移：让 BGM 高潮对准视频峰值
        recommended_offset = bgm_climax_time - expected_video_peak

        return {
            "bgm_climax_ratio": climax.bgm_climax_ratio,
            "bgm_climax_time_sec": round(bgm_climax_time, 2),
            "video_peak_ratio": climax.video_peak_ratio,
            "recommended_offset_sec": round(recommended_offset, 2),
            "sync_tolerance": climax.sync_tolerance_sec,
        }

    def _plan_beat_sync(
        self,
        pattern: EditingPattern,
        bgm_beat_times: list,
        video_duration: float,
    ) -> dict:
        """
        计划卡点同步

        目标：在视频关键位置（运动峰值）附近找最近的鼓点
        """
        sync = pattern.beat_sync

        if sync.sync_type == "none" or not bgm_beat_times:
            return {"enabled": False, "sync_type": "none"}

        # 如果视频有运动曲线，找运动峰值附近的鼓点
        # 这里简化：返回 BGM 中间位置附近的鼓点
        mid_time = video_duration / 2
        beats = np.array(bgm_beat_times)

        # 找视频中点附近 3 个鼓点
        distances = np.abs(beats - mid_time)
        nearby_idx = np.argsort(distances)[:3]
        sync_points = [round(float(beats[i]), 2) for i in nearby_idx]

        return {
            "enabled": True,
            "sync_type": sync.sync_type,
            "strength": sync.strength,
            "sync_points": sync_points,
            "tolerance_sec": 0.15,
        }

    def format_plan_summary(self, plan: dict) -> str:
        """将剪辑计划格式化为可读文本"""
        parts = []

        entry = plan["entry"]
        parts.append(f"切入点: {entry['type']} @ {entry['time_sec']}s")

        if plan["volume_automations"]:
            parts.append(f"音量变化: {len(plan['volume_automations'])} 处")
            for a in plan["volume_automations"]:
                parts.append(f"  {a['type']} @ {a['time_sec']}s → 音量 {a['volume']}")

        climax = plan["climax_alignment"]
        parts.append(
            f"高潮对齐: BGM@{climax['bgm_climax_time_sec']}s ↔ 画面@{climax['video_peak_ratio']*100:.0f}%"
        )

        beat = plan["beat_sync"]
        if beat["enabled"]:
            parts.append(f"卡点: {beat['sync_type']} (强度 {beat['strength']:.0%})")
        else:
            parts.append("卡点: 无")

        return "\n".join(parts)
