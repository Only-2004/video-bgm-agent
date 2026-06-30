"""分析示范视频的 BGM 剪辑逻辑，生成 EditingPattern"""

import numpy as np
import librosa
import cv2
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models.patterns import (
    EditingPattern, AudioEntryInfo, ClimaxAlignment,
    VolumeSegment, BeatSyncRule,
)


class PatternAnalyzer:
    """从示范视频中提取 BGM 剪辑逻辑"""

    def analyze_demo(self, video_path: str, audio_path: str,
                     name: str = "", video_id: str = "") -> EditingPattern:
        """
        完整分析流程：
        1. librosa 分析音频 → 切入点、高潮、音量包络
        2. scenedetect + opencv 分析视频 → 场景切换、运动能量
        3. 关联分析 → 卡点强度、高潮对齐
        """
        # 1. 音频分析
        audio_result = self._analyze_audio(audio_path)

        # 2. 视频剪辑分析
        video_result = self._analyze_video_editing(video_path)

        # 3. 关联分析
        correlation = self._correlate_audio_video(audio_result, video_result)

        # 构建 Pattern
        duration = audio_result["duration"]
        pattern = EditingPattern(
            name=name or f"示范_{os.path.basename(video_path)[:20]}",
            description=self._generate_description(audio_result, video_result, correlation),
            audio_entry=audio_result["entry"],
            climax_alignment=correlation["climax_alignment"],
            volume_segments=audio_result["volume_segments"],
            beat_sync=correlation["beat_sync"],
            demo_duration_sec=duration,
            demo_video_id=video_id,
            detection_confidence=correlation["confidence"],
        )

        return pattern

    def _analyze_audio(self, audio_path: str) -> dict:
        """librosa 分析音频特征"""
        y, sr = librosa.load(audio_path, sr=22050, duration=180)
        duration = librosa.get_duration(y=y, sr=sr)

        # onset 强度
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

        # RMS 能量
        rms = librosa.feature.rms(y=y)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)

        # 鼓点
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0]) if len(tempo) > 0 else 100.0
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        # 能量曲线（7段）
        energy_curve = self._compute_energy_curve(y, sr, n_segments=7)

        # 切入点检测
        entry = self._detect_bgm_entry(onset_env, rms, times, rms_times, duration)

        # 高潮位置
        climax_ratio = self._detect_climax(energy_curve)

        # 音量变化段
        volume_segments = self._detect_volume_segments(rms, rms_times, duration)

        return {
            "duration": duration,
            "tempo": tempo,
            "beat_times": beat_times,
            "energy_curve": energy_curve,
            "entry": entry,
            "climax_ratio": climax_ratio,
            "volume_segments": volume_segments,
        }

    def _compute_energy_curve(self, y, sr, n_segments=7):
        """计算分段能量曲线"""
        segment_len = len(y) // n_segments
        curve = []
        for i in range(n_segments):
            start = i * segment_len
            end = min(start + segment_len, len(y))
            seg = y[start:end]
            if len(seg) == 0:
                curve.append(0.3)
                continue
            rms = float(np.mean(librosa.feature.rms(y=seg)))
            curve.append(min(1.0, rms * 3))
        return smooth_curve(curve)

    def _detect_bgm_entry(self, onset_env, rms, onset_times, rms_times, duration):
        """检测 BGM 切入点"""
        if len(onset_env) == 0 or duration <= 0:
            return AudioEntryInfo()

        onset_norm = onset_env / (np.median(onset_env) + 1e-6)
        rms_norm = rms / (np.max(rms) + 1e-6)

        # 找第一个显著 onset 峰值
        spike_threshold = 2.0
        for i, val in enumerate(onset_norm):
            if val > spike_threshold:
                entry_time = onset_times[min(i, len(onset_times) - 1)]
                entry_ratio = entry_time / duration

                # 判断类型
                window_start = max(0, i - 5)
                window_end = min(len(rms_norm), i + 5)
                window = rms_norm[window_start:window_end]
                if len(window) > 1:
                    energy_slope = (window[-1] - window[0]) / len(window)
                else:
                    energy_slope = 0

                if entry_ratio > 0.05:
                    entry_type = "delayed"
                    fade_dur = 0.5
                    start_vol = 0.3
                elif energy_slope > 0.05:
                    entry_type = "fade_in"
                    fade_dur = min(2.0, entry_ratio * duration)
                    start_vol = 0.2
                elif val > 4.0:
                    entry_type = "immediate"
                    fade_dur = 0.0
                    start_vol = 1.0
                else:
                    entry_type = "on_beat"
                    fade_dur = 0.0
                    start_vol = 0.8

                return AudioEntryInfo(
                    entry_type=entry_type,
                    entry_time_ratio=round(entry_ratio, 3),
                    fade_duration_sec=round(fade_dur, 2),
                    start_volume=start_vol,
                )

        # 没检测到明显切入点
        return AudioEntryInfo(
            entry_type="immediate",
            entry_time_ratio=0.0,
            fade_duration_sec=0.0,
            start_volume=1.0,
        )

    def _detect_climax(self, energy_curve):
        """从能量曲线找高潮位置"""
        if not energy_curve:
            return 0.5
        peak_idx = np.argmax(energy_curve[2:5]) + 2
        return round(peak_idx / (len(energy_curve) - 1), 3)

    def _detect_volume_segments(self, rms, rms_times, duration):
        """检测音量变化段（ducking 等）"""
        if len(rms) == 0 or duration <= 0:
            return []

        segments = []
        rms_norm = rms / (np.max(rms) + 1e-6)
        median_val = np.median(rms_norm)

        # 找低能量持续区段（ducking）
        in_duck = False
        duck_start = 0

        for i, val in enumerate(rms_norm):
            t = rms_times[min(i, len(rms_times) - 1)] / duration

            if val < median_val * 0.4 and not in_duck:
                in_duck = True
                duck_start = t
            elif (val >= median_val * 0.4 or i == len(rms_norm) - 1) and in_duck:
                in_duck = False
                duck_end = t
                if duck_end - duck_start > 0.03:  # 至少 3% 的时长
                    segments.append(VolumeSegment(
                        time_ratio=round(duck_start, 3),
                        volume=round(float(np.mean(rms_norm[max(0, i - 10):i])), 3),
                        segment_type="duck",
                    ))

        return segments

    def _analyze_video_editing(self, video_path: str) -> dict:
        """分析视频剪辑节奏"""
        # 场景切换检测
        scenes = self._detect_scenes(video_path)

        # 运动能量曲线
        motion_curve = self._compute_motion_energy(video_path)

        # 视频时长
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else 0
        cap.release()

        # 剪辑节奏：每秒切换次数
        cuts_per_second = len(scenes) / max(duration, 1)

        return {
            "scenes": scenes,
            "motion_curve": motion_curve,
            "duration": duration,
            "cuts_per_second": cuts_per_second,
        }

    def _detect_scenes(self, video_path):
        """检测场景切换点"""
        try:
            from scenedetect import open_video, SceneManager
            from scenedetect.detectors import ContentDetector

            video = open_video(video_path)
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=30.0))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            scenes = []
            for start, end in scene_list:
                scenes.append((start.get_seconds(), end.get_seconds()))
            return scenes
        except Exception:
            return []

    def _compute_motion_energy(self, video_path, sample_interval=1.0):
        """计算画面运动能量曲线"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else 0

        if duration <= 0:
            cap.release()
            return []

        motion_scores = []
        prev_gray = None
        sample_frame = int(fps * sample_interval)

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % max(sample_frame, 1) == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    diff = cv2.absdiff(prev_gray, gray)
                    motion_scores.append(float(np.mean(diff)))
                else:
                    motion_scores.append(0.0)
                prev_gray = gray

            frame_idx += 1

        cap.release()

        # 归一化
        if motion_scores:
            max_val = max(motion_scores) if max(motion_scores) > 0 else 1
            motion_scores = [s / max_val for s in motion_scores]

        return motion_scores

    def _correlate_audio_video(self, audio_result, video_result):
        """关联音频和视频分析结果"""
        beat_times = audio_result["beat_times"]
        scenes = video_result["scenes"]
        duration = audio_result["duration"]

        # 卡点检测
        sync_strength, sync_type = self._compute_sync_strength(beat_times, scenes)

        # 高潮对齐
        bgm_climax_ratio = audio_result["climax_ratio"]

        # 找视频运动峰值位置
        motion_curve = video_result["motion_curve"]
        if motion_curve:
            video_peak_idx = np.argmax(motion_curve)
            video_peak_ratio = video_peak_idx / max(len(motion_curve) - 1, 1)
        else:
            video_peak_ratio = 0.5

        # 计算偏移
        bgm_climax_time = bgm_climax_ratio * duration
        video_peak_time = video_peak_ratio * duration
        offset = abs(bgm_climax_time - video_peak_time)

        # 置信度
        confidence = 0.5
        if len(scenes) >= 3:
            confidence += 0.2
        if sync_strength > 0.3:
            confidence += 0.2
        if audio_result["tempo"] > 60:
            confidence += 0.1

        climax_alignment = ClimaxAlignment(
            bgm_climax_ratio=bgm_climax_ratio,
            video_peak_ratio=round(video_peak_ratio, 3),
            alignment_offset_sec=round(offset, 2),
            sync_tolerance_sec=0.15,
        )

        beat_sync = BeatSyncRule(
            sync_type=sync_type,
            strength=round(sync_strength, 3),
        )

        return {
            "climax_alignment": climax_alignment,
            "beat_sync": beat_sync,
            "confidence": min(confidence, 1.0),
        }

    def _compute_sync_strength(self, beat_times, scenes, tolerance=0.15):
        """计算卡点强度：画面切换与鼓点对齐的比例"""
        if not beat_times or not scenes:
            return 0.0, "none"

        beats = np.array(beat_times)
        matched = 0

        for start_time, _ in scenes:
            distances = np.abs(beats - start_time)
            if len(distances) > 0 and np.min(distances) < tolerance:
                matched += 1

        strength = matched / max(len(scenes), 1)

        if strength > 0.5:
            sync_type = "beat_to_cut"
        elif strength > 0.3:
            sync_type = "energy_rise_to_transition"
        else:
            sync_type = "none"

        return strength, sync_type

    def _generate_description(self, audio_result, video_result, correlation):
        """生成 Pattern 描述"""
        entry = audio_result["entry"]
        sync = correlation["beat_sync"]

        desc_parts = []
        desc_parts.append(f"BGM {entry.entry_type} 切入")
        desc_parts.append(f"Tempo {audio_result['tempo']:.0f}BPM")
        desc_parts.append(f"剪辑节奏 {video_result['cuts_per_second']:.1f} cuts/s")

        if sync.sync_type != "none":
            desc_parts.append(f"卡点强度 {sync.strength:.0%}")

        return "，".join(desc_parts)


def smooth_curve(curve, window=3):
    """简单移动平均"""
    result = []
    for i in range(len(curve)):
        start = max(0, i - window // 2)
        end = min(len(curve), i + window // 2 + 1)
        result.append(round(float(np.mean(curve[start:end])), 3))
    return result
