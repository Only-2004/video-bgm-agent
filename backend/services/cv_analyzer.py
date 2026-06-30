"""
CV 管线 — 纯代码视频分析（零 LLM 调用）

输出：
- 转场点（PySceneDetect，毫秒级精度）
- 张力曲线（帧差法 + 光流法，0.0-1.0 连续数值）
- 色调情绪（颜色统计）
- 视频音频特征（librosa）
"""

import cv2
import numpy as np
import os
from typing import List, Dict, Tuple


def _to_python(obj):
    """递归将 numpy 类型转为 Python 原生类型，确保 JSON 序列化安全"""
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_python(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


class CVAnalyzer:
    def analyze(self, video_path: str) -> dict:
        """
        运行完整 CV 管线。

        Returns:
            {
                "duration": float,
                "transitions": [{"timestamp", "type", "duration", "scene_index"}],
                "tension_curve": [{"timestamp", "tension", "frame_diff", "motion"}],
                "color_mood": {"warm_ratio", "dark_ratio", "mood_tendency"},
                "video_audio": {"bpm", "energy", "spectral_centroid", "loudness_curve"},
                "keyframe_timestamps": [float],
            }
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        fps = max(cap.get(cv2.CAP_PROP_FPS), 1)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        cap.release()

        print(f"[CV] 视频: {duration:.1f}s, {fps:.0f}fps, {total_frames} frames")

        # 1. 转场检测
        transitions = self._detect_transitions(video_path, fps, duration)
        print(f"[CV] 转场: {len(transitions)} 个")

        # 2. 张力曲线 + 运镜检测
        tension_curve, camera_motion_type = self._compute_tension_curve(video_path, fps, sample_fps=2)
        print(f"[CV] 张力曲线: {len(tension_curve)} 个采样点, 运镜: {camera_motion_type}")

        # 3. 色调情绪
        color_mood = self._compute_color_mood(video_path, fps)
        print(f"[CV] 色调: {color_mood['mood_tendency']} (暖{color_mood['warm_ratio']:.2f} 暗{color_mood['dark_ratio']:.2f})")

        # 4. 视频音频
        video_audio = self._analyze_video_audio(video_path)
        if video_audio:
            print(f"[CV] 视频音频: BPM={video_audio['bpm']:.0f}, 能量={video_audio['energy']:.3f}")
        else:
            print("[CV] 视频音频: 无音频轨或分析失败")

        # 5. 关键帧时间戳（转场点 + 均匀补充）
        keyframe_timestamps = self._compute_keyframe_timestamps(transitions, duration, max_frames=8)

        # 6. 给转场点分配 tension_level（取转场时刻最近的张力值）
        transitions = self._assign_transition_tension_levels(transitions, tension_curve)

        # 7. 计算 alignment_strategy
        alignment_strategy = self._compute_alignment_strategy(transitions, tension_curve)
        print(f"[CV] alignment_strategy: {alignment_strategy}")

        # 8. 剪辑节奏模式分析
        rhythm_pattern = self._analyze_rhythm_pattern(transitions)
        print(f"[CV] rhythm_pattern: {rhythm_pattern['pattern']} "
              f"(intervals={[f'{i:.1f}' for i in rhythm_pattern['intervals']]})")

        return _to_python({
            "duration": round(duration, 1),
            "fps": round(fps, 1),
            "transitions": transitions,
            "tension_curve": tension_curve,
            "color_mood": color_mood,
            "video_audio": video_audio,
            "keyframe_timestamps": keyframe_timestamps,
            "alignment_strategy": alignment_strategy,
            "camera_motion_type": camera_motion_type,
            "rhythm_pattern": rhythm_pattern,
        })

    # ============ 辅助方法 ============

    def _assign_transition_tension_levels(self, transitions: List[Dict], tension_curve: List[Dict]) -> List[Dict]:
        """给每个转场点分配 tension_level（取最近张力值）"""
        if not tension_curve:
            for t in transitions:
                t["tension_level"] = 0.5
            return transitions

        timestamps = [p["timestamp"] for p in tension_curve]
        values = [p["tension"] for p in tension_curve]

        for t in transitions:
            ts = t["timestamp"]
            idx = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - ts))
            t["tension_level"] = round(values[idx], 3)

        return transitions

    def _compute_alignment_strategy(self, transitions: List[Dict], tension_curve: List[Dict]) -> str:
        """
        根据转场密度和平均张力判定对齐策略：
        - avg_tension > 0.6 且 转场≥3 → full_beat_sync
        - 0.3 ≤ avg_tension ≤ 0.6 且 转场≥3 → partial_alignment
        - 转场密度 ≥ 0.4（每秒0.4个转场）→ 至少 partial_alignment（密度否决权）
        - 否则 → ambient_only
        """
        num_transitions = len(transitions)

        if tension_curve:
            avg_tension = sum(p["tension"] for p in tension_curve) / len(tension_curve)
        else:
            avg_tension = 0.5

        # 计算转场密度（转场数 / 视频时长秒数）
        if transitions:
            timestamps = [t.get("timestamp", 0) for t in transitions]
            duration = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 1.0
            # 至少按视频最后一秒来算，避免除零
            video_span = max(duration + 1.0, 3.0)
            transition_density = num_transitions / video_span
        else:
            transition_density = 0.0

        # 主逻辑
        if avg_tension > 0.6 and num_transitions >= 3:
            return "full_beat_sync"
        elif 0.3 <= avg_tension <= 0.6 and num_transitions >= 3:
            return "partial_alignment"

        # 密度否决权：转场密集 → 至少 partial_alignment
        # 典型场景：跟拍盲区张力低(0.35)，但5秒内3个转场（滑雪/运动视频）
        if transition_density >= 0.4 and num_transitions >= 3:
            return "partial_alignment"

        if avg_tension > 0.6 and num_transitions >= 1:
            return "partial_alignment"

        return "ambient_only"

    def _analyze_rhythm_pattern(self, transitions: List[Dict]) -> Dict:
        """
        分析剪辑节奏模式：从转场间隔序列判断节奏走向。

        模式分类：
        - 加速型: 间隔递减（8→5→3→2），情绪推向高潮
        - 减速型: 间隔递增，情绪收束
        - 爆发型: 前段长间隔 + 后段密集（蓄势后爆发）
        - 匀速型: 间隔方差小，稳定节奏
        - 未知: 转场不足

        Returns:
            {"pattern": str, "intervals": list, "slope": float, "variance": float}
        """
        if len(transitions) < 3:
            return {"pattern": "未知", "intervals": [], "slope": 0.0, "variance": 0.0}

        # 提取相邻转场间隔
        timestamps = [t["timestamp"] for t in transitions]
        intervals = [
            round(timestamps[i + 1] - timestamps[i], 2)
            for i in range(len(timestamps) - 1)
        ]

        if not intervals or len(intervals) < 2:
            return {"pattern": "未知", "intervals": intervals, "slope": 0.0, "variance": 0.0}

        n = len(intervals)

        # 线性回归斜率：负=加速，正=减速
        x = np.arange(n, dtype=float)
        y = np.array(intervals, dtype=float)
        x_mean = x.mean()
        y_mean = y.mean()
        slope = float(np.sum((x - x_mean) * (y - y_mean)) / (np.sum((x - x_mean) ** 2) + 1e-8))

        # 方差：小=匀速
        variance = float(np.var(y))
        avg_interval = float(y_mean)

        # 归一化斜率（相对于平均间隔）
        norm_slope = slope / (avg_interval + 0.01)

        # 爆发型检测：后1/3的平均间隔 < 前1/3的平均间隔的40%
        is_burst = False
        if n >= 3:
            third = max(1, n // 3)
            early_avg = float(np.mean(y[:third]))
            late_avg = float(np.mean(y[-third:]))
            if early_avg > 0 and late_avg / early_avg < 0.4:
                is_burst = True

        # 分类
        if is_burst:
            pattern = "爆发型"
        elif norm_slope < -0.15 and n >= 3:
            pattern = "加速型"
        elif norm_slope > 0.15 and n >= 3:
            pattern = "减速型"
        elif variance < (avg_interval * 0.3) ** 2 + 0.5:
            pattern = "匀速型"
        else:
            pattern = "匀速型"

        return {
            "pattern": pattern,
            "intervals": intervals,
            "slope": round(slope, 3),
            "variance": round(variance, 3),
            "avg_interval": round(avg_interval, 2),
        }

    # ============ 1. 转场检测 ============

    def _detect_transitions(self, video_path: str, fps: float, duration: float) -> List[Dict]:
        """PySceneDetect 检测转场"""
        try:
            from scenedetect import detect, ContentDetector

            # 自适应阈值
            threshold = self._estimate_threshold(video_path, fps)
            scene_list = detect(video_path, ContentDetector(threshold=threshold))

            transitions = []
            for i, (start, end) in enumerate(scene_list):
                if i == 0:
                    continue  # 跳过第一个场景（开场）
                ts = start.get_seconds()
                scene_dur = (end - start).get_seconds()

                # 判断转场类型
                t_type = self._classify_transition(video_path, ts, fps)

                transitions.append({
                    "timestamp": round(ts, 2),
                    "type": t_type,
                    "duration": round(scene_dur, 2),
                    "scene_index": i,
                })

            return transitions

        except ImportError:
            print("[CV] scenedetect 未安装，降级到帧差法检测")
            return self._detect_transitions_fallback(video_path, fps, duration)

    def _estimate_threshold(self, video_path: str, fps: float) -> float:
        """自适应阈值：根据视频亮度/对比度调整"""
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        brightnesses = []
        contrasts = []
        sample_count = 10

        for i in range(sample_count):
            t = int((i / sample_count) * total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, t)
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightnesses.append(np.mean(gray))
                contrasts.append(np.std(gray))
        cap.release()

        if not brightnesses:
            return 27.0

        avg_brightness = np.mean(brightnesses)
        avg_contrast = np.mean(contrasts)

        if avg_contrast < 30:
            threshold = 15.0 + (avg_contrast / 30) * 5
        elif avg_contrast > 70:
            threshold = 35.0 + ((avg_contrast - 70) / 60) * 10
        else:
            threshold = 25.0 + ((avg_contrast - 30) / 40) * 10

        if avg_brightness < 60:
            threshold *= 0.8

        return max(10.0, min(50.0, threshold))

    def _classify_transition(self, video_path: str, timestamp: float, fps: float) -> str:
        """通过转场前后帧的亮度变化判断转场类型"""
        cap = cv2.VideoCapture(video_path)
        frame_num = int(timestamp * fps)

        # 取转场前1帧和后1帧
        frames = []
        for offset in [-2, 0, 2]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_num + offset))
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append(np.mean(gray))
            else:
                frames.append(128.0)
        cap.release()

        if len(frames) >= 3:
            # 亮度变化大 → 可能是淡入淡出
            brightness_diff = abs(frames[0] - frames[2])
            if brightness_diff > 60:
                return "淡入淡出"
            # 亮度从暗到亮 → 闪白
            if frames[2] - frames[0] > 80:
                return "闪白"

        return "硬切"

    def _detect_transitions_fallback(self, video_path: str, fps: float, duration: float) -> List[Dict]:
        """降级：用帧差法检测转场"""
        cap = cv2.VideoCapture(video_path)
        sample_fps = 2
        frame_interval = int(fps / sample_fps)

        prev_frame = None
        diffs = []
        timestamp = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if frame_num % frame_interval != 0:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_frame is not None:
                diff = cv2.absdiff(prev_frame, gray)
                diffs.append((timestamp, np.mean(diff) / 255.0))
            prev_frame = gray
            timestamp += 1.0 / sample_fps
        cap.release()

        # 找差异突变点
        if len(diffs) < 3:
            return []

        mean_diff = np.mean([d[1] for d in diffs])
        std_diff = np.std([d[1] for d in diffs])
        threshold = mean_diff + 2.5 * std_diff

        transitions = []
        for ts, diff_val in diffs:
            if diff_val > threshold:
                transitions.append({
                    "timestamp": round(ts, 2),
                    "type": "硬切",
                    "duration": 0,
                    "scene_index": len(transitions),
                })

        return transitions

    # ============ 2. 张力曲线 ============

    def _compute_tension_curve(self, video_path: str, fps: float, sample_fps: int = 2) -> Tuple[List[Dict], str]:
        """
        帧差法 + 光流法计算张力曲线，含运镜检测。

        三因子张力公式：
        tension = 0.3 × frame_diff + 0.3 × object_motion + 0.4 × camera_motion_score

        关键洞察：相机运动本身就是能量信号，不是噪声。
        跟拍 = 相机在动 = 视频有运动感，这个信号不应被丢弃。

        - frame_diff: 帧间像素差异（画面变化）
        - object_motion: 局部残差运动（物体运动，减去全局运动后的剩余）
        - camera_motion_score: 全局运动（相机运动），归一化到[0,1]

        Returns:
            (tension_curve, camera_motion_type)
        """
        cap = cv2.VideoCapture(video_path)
        frame_interval = int(fps / sample_fps)

        prev_frame = None
        tension_curve = []
        timestamp = 0

        # 收集全局运动向量用于运镜类型判断
        global_motion_vectors = []
        # 收集全局运动幅值用于归一化
        global_magnitudes = []

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if frame_num % frame_interval != 0:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_frame is not None:
                # 帧差法
                diff = cv2.absdiff(prev_frame, gray)
                frame_diff_score = np.mean(diff) / 255.0

                # 光流法（拆分全局/局部）
                object_motion = 0.0
                camera_motion_score = 0.0
                global_magnitude = 0
                try:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_frame, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                    )

                    # 全局运动：所有像素光流的平均值（相机运动）
                    global_flow_x = np.mean(flow[..., 0])
                    global_flow_y = np.mean(flow[..., 1])
                    global_magnitude = np.sqrt(global_flow_x**2 + global_flow_y**2)
                    global_motion_vectors.append((global_flow_x, global_flow_y))
                    global_magnitudes.append(global_magnitude)

                    # 局部残差：每个像素减去全局平均后的运动（物体运动）
                    local_flow_x = flow[..., 0] - global_flow_x
                    local_flow_y = flow[..., 1] - global_flow_y
                    local_magnitude = np.mean(np.sqrt(local_flow_x**2 + local_flow_y**2))

                    # 三因子独立归一化
                    object_motion = min(local_magnitude / 5.0, 1.0)
                    # camera_motion_score 先用原始值，后面统一归一化
                    camera_motion_score = global_magnitude
                except Exception:
                    pass

                tension_curve.append({
                    "timestamp": round(timestamp, 1),
                    "frame_diff": round(frame_diff_score, 3),
                    "object_motion": round(object_motion, 3),
                    "camera_motion_raw": round(camera_motion_score, 3),
                })

            prev_frame = gray
            timestamp += 1.0 / sample_fps

        cap.release()

        # 归一化 camera_motion_score 到 [0,1]
        if global_magnitudes:
            cam_max = max(global_magnitudes)
            cam_min = min(global_magnitudes)
            for t in tension_curve:
                raw = t.pop("camera_motion_raw")
                if cam_max > cam_min:
                    t["camera_motion_score"] = round((raw - cam_min) / (cam_max - cam_min), 3)
                else:
                    t["camera_motion_score"] = 0.0
        else:
            for t in tension_curve:
                t.pop("camera_motion_raw", None)
                t["camera_motion_score"] = 0.0

        # 三因子综合张力
        for t in tension_curve:
            tension = (
                0.3 * t["frame_diff"]
                + 0.3 * t["object_motion"]
                + 0.4 * t["camera_motion_score"]
            )
            t["tension"] = round(min(tension, 1.0), 3)
            # 保留 motion 字段兼容旧逻辑
            t["motion"] = round(
                min(t["camera_motion_score"] + t["object_motion"] * 0.5, 1.0), 3
            )

        # 平滑处理（移动平均）
        if len(tension_curve) > 3:
            values = [t["tension"] for t in tension_curve]
            window = min(5, len(values))
            smoothed = np.convolve(values, np.ones(window) / window, mode="same")
            for i, t in enumerate(tension_curve):
                t["tension"] = round(float(smoothed[i]), 3)

        # 运镜类型检测
        camera_motion_type = self._detect_camera_motion(global_motion_vectors)

        return tension_curve, camera_motion_type

    def _detect_camera_motion(self, global_motion_vectors: List[Tuple[float, float]]) -> str:
        """
        根据全局运动向量判断运镜类型。

        - 跟拍/摇镜头：全局运动大 + 方向一致
        - 固定机位：全局运动≈0
        - 手持：全局运动方向随机（抖动）
        - 推镜头：径向运动（从中心向外扩散）
        """
        if len(global_motion_vectors) < 3:
            return "未知"

        xs = np.array([v[0] for v in global_motion_vectors])
        ys = np.array([v[1] for v in global_motion_vectors])

        avg_mag = np.mean(np.sqrt(xs**2 + ys**2))

        # 全局运动很小 → 固定机位
        if avg_mag < 1.0:
            return "固定机位"

        # 计算方向一致性（余弦相似度的方差）
        angles = np.arctan2(ys, xs)
        # 方向一致性：用复数均值的模长 / 个体均值
        mean_cos = np.mean(np.cos(angles))
        mean_sin = np.mean(np.sin(angles))
        resultant_length = np.sqrt(mean_cos**2 + mean_sin**2)  # 0=完全随机, 1=完全一致

        # 径向运动检测（推拉镜头）：中心像素运动小，边缘像素运动大
        n_frames = len(global_motion_vectors)
        is_radial = False
        if avg_mag > 2.0 and resultant_length > 0.5:
            # 简单启发：如果全局运动方向主要是水平或垂直（不是随机），且 magnitude 中等
            # 推镜头的特征：运动方向从中心向外，但我们用全局平均来近似
            # 如果 x 和 y 分量都比较大且方向一致 → 更可能是跟拍
            # 如果 magnitude 大但方向有径向特征 → 推镜头
            # 这里用一个简单启发：跟拍通常 x 分量远大于 y（水平跟拍）
            ratio = abs(mean_cos) / (abs(mean_sin) + 0.01)
            if 0.3 < ratio < 3.0 and avg_mag > 3.0:
                # x 和 y 都有分量 → 可能是推拉或斜向跟拍
                # 检查是否有径向特征：看 magnitude 是否随时间递增（推镜头）
                mags = [np.sqrt(v[0]**2 + v[1]**2) for v in global_motion_vectors]
                if len(mags) > 5:
                    first_half = np.mean(mags[:len(mags)//2])
                    second_half = np.mean(mags[len(mags)//2:])
                    if second_half > first_half * 1.5:
                        is_radial = True

        if is_radial:
            return "推镜头"

        # 方向一致性高 + 运动大 → 跟拍/摇镜头
        if resultant_length > 0.6 and avg_mag > 2.0:
            return "跟拍"

        # 方向一致性低 + 运动存在 → 手持抖动
        if resultant_length < 0.5 and avg_mag > 1.5:
            return "手持"

        # 其他：有运动但不够强
        return "轻微运动"

    # ============ 3. 色调情绪 ============

    def _compute_color_mood(self, video_path: str, fps: float) -> Dict:
        """颜色统计 → 色调情绪倾向"""
        cap = cv2.VideoCapture(video_path)
        sample_fps = 1

        warm_scores = []
        dark_scores = []

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if frame_num % int(fps / sample_fps) != 0:
                continue

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # 暖色调占比（红/橙/黄：色相0-60）
            warm_mask = (hsv[..., 0] < 60) & (hsv[..., 1] > 50)
            warm_ratio = np.mean(warm_mask)

            # 暗色调占比（亮度<100）
            dark_ratio = np.mean(hsv[..., 2] < 100)

            warm_scores.append(warm_ratio)
            dark_scores.append(dark_ratio)

        cap.release()

        if not warm_scores:
            return {"warm_ratio": 0.3, "dark_ratio": 0.3, "mood_tendency": "中性"}

        avg_warm = float(np.mean(warm_scores))
        avg_dark = float(np.mean(dark_scores))

        if avg_warm > 0.4 and avg_dark < 0.3:
            mood = "温暖明亮"
        elif avg_dark > 0.4 and avg_warm < 0.2:
            mood = "阴暗压抑"
        elif avg_warm > 0.3 and avg_dark > 0.3:
            mood = "温暖但有阴影"
        else:
            mood = "中性"

        return {
            "warm_ratio": round(avg_warm, 3),
            "dark_ratio": round(avg_dark, 3),
            "mood_tendency": mood,
        }

    # ============ 4. 视频音频 ============

    def _analyze_video_audio(self, video_path: str) -> dict:
        """librosa 分析视频自带的音频轨（客观数据，不猜测）"""
        try:
            import librosa
        except ImportError:
            return None

        try:
            y, sr = librosa.load(video_path, sr=22050, mono=True)
        except Exception:
            # librosa 无法直接加载 mp4，用 moviepy 提取音频
            try:
                import tempfile, os
                from moviepy import AudioFileClip
                clip = AudioFileClip(video_path)
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                clip.write_audiofile(tmp.name, fps=22050, nbytes=2, codec="pcm_s16le", logger=None)
                clip.close()
                y, sr = librosa.load(tmp.name, sr=22050, mono=True)
                os.remove(tmp.name)
            except Exception:
                return None

        if len(y) < sr:  # 不到1秒
            return None

        # BPM
        tempo_bt, _ = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo_bt, '__len__'):
            tempo_bt = float(tempo_bt[0]) if len(tempo_bt) > 0 else 0
        else:
            tempo_bt = float(tempo_bt)

        # onset envelope BPM 交叉验证
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo_oe_arr = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
        tempo_oe = float(tempo_oe_arr[0]) if len(tempo_oe_arr) > 0 else 0

        # 交叉验证：两个方法差距大时，取较小值（避免半拍误检）
        if tempo_bt > 0 and tempo_oe > 0:
            ratio = max(tempo_bt, tempo_oe) / min(tempo_bt, tempo_oe)
            if ratio > 1.5:
                # 差距大，一个可能是另一个的倍频，取较小值
                tempo = min(tempo_bt, tempo_oe)
            else:
                tempo = (tempo_bt + tempo_oe) / 2
        else:
            tempo = max(tempo_bt, tempo_oe)

        # 能量
        rms = librosa.feature.rms(y=y)[0]
        energy = float(np.mean(rms))

        # 频谱质心
        spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

        # 响度曲线
        times = librosa.times_like(rms, sr=sr)
        step = max(1, len(rms) // 50)
        loudness_curve = [
            {"timestamp": round(float(times[i]), 1), "loudness": round(float(rms[i]), 4)}
            for i in range(0, len(rms), step)
        ][:50]

        # === 人声检测（客观：基频 + 零交叉率） ===
        has_speech, speech_segments = self._detect_speech(y, sr, rms, times)

        # === 背景音乐检测（客观：onset 规律性） ===
        music_playing = self._detect_music(y, sr, onset_env)

        # === 环境噪音级别（客观：能量分布） ===
        ambient_noise_level = self._classify_noise_level(rms)

        return {
            "bpm": round(tempo, 1),
            "energy": round(energy, 4),
            "spectral_centroid": round(spectral_centroid, 1),
            "loudness_curve": loudness_curve,
            "has_speech": has_speech,
            "speech_segments": speech_segments,
            "music_playing": music_playing,
            "ambient_noise_level": ambient_noise_level,
        }

    def _detect_speech(self, y, sr: int, rms, times) -> tuple:
        """人声检测：基频(f0) + 零交叉率(ZCR)"""
        import librosa as _librosa

        # 基频检测
        f0, voiced_flag, _ = _librosa.pyin(y, fmin=60, fmax=400, sr=sr)

        # 零交叉率
        zcr = _librosa.feature.zero_crossing_rate(y)[0]

        # 分帧判断每帧是否有人声
        frame_length = 2048
        hop_length = 512
        n_frames = len(rms)
        frame_dur = hop_length / sr

        speech_frames = []
        for i in range(n_frames):
            # 基频在人声范围且有声
            has_f0 = False
            if i < len(voiced_flag):
                has_f0 = bool(voiced_flag[i])

            # ZCR 在人声典型范围 (0.02-0.15)
            zcr_val = float(zcr[i]) if i < len(zcr) else 0
            zcr_ok = 0.02 < zcr_val < 0.15

            # 能量不能太低（排除静音段被误判）
            energy_ok = float(rms[i]) > 0.01

            speech_frames.append(has_f0 and zcr_ok and energy_ok)

        # 合并连续帧为时间段
        has_speech = sum(speech_frames) > n_frames * 0.05  # 超过5%帧有人声
        speech_segments = []

        if has_speech:
            in_segment = False
            seg_start = 0
            for i, is_speech in enumerate(speech_frames):
                ts = float(times[i])
                if is_speech and not in_segment:
                    seg_start = ts
                    in_segment = True
                elif not is_speech and in_segment:
                    if ts - seg_start > 0.5:  # 至少0.5秒才算一段
                        speech_segments.append([round(seg_start, 2), round(ts, 2)])
                    in_segment = False
            # 末尾段
            if in_segment and float(times[-1]) - seg_start > 0.5:
                speech_segments.append([round(seg_start, 2), round(float(times[-1]), 2)])

        return has_speech, speech_segments

    def _detect_music(self, y, sr: int, onset_env) -> bool:
        """背景音乐检测：onset 规律性"""
        import librosa as _librosa

        if len(onset_env) < 10:
            return False

        # 计算 onset 间隔的变异系数
        peaks = _librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10)
        if len(peaks) < 4:
            return False

        intervals = np.diff(peaks).astype(float)
        if len(intervals) < 3:
            return False

        cv = float(np.std(intervals) / (np.mean(intervals) + 1e-8))
        # CV < 0.8 表示 onsets 较规律 → 可能有音乐
        return cv < 0.8

    def _classify_noise_level(self, rms) -> str:
        """环境噪音级别：基于能量分布"""
        mean_energy = float(np.mean(rms))
        if mean_energy < 0.005:
            return "安静"
        elif mean_energy < 0.03:
            return "中等"
        else:
            return "嘈杂"

    # ============ 5. 关键帧时间戳 ============

    def _compute_keyframe_timestamps(
        self, transitions: List[Dict], duration: float, max_frames: int = 8
    ) -> List[float]:
        """
        基于转场点计算关键帧时间戳。

        策略：每个转场点取1帧 + 均匀补充到 max_frames
        """
        # 转场点帧
        timestamps = [t["timestamp"] for t in transitions]

        # 均匀补充
        if len(timestamps) < max_frames:
            step = duration / (max_frames - len(timestamps) + 1)
            for i in range(max_frames - len(timestamps)):
                ts = step * (i + 1)
                if not any(abs(ts - existing) < 1.0 for existing in timestamps):
                    timestamps.append(round(ts, 1))

        timestamps.sort()
        return timestamps[:max_frames]
