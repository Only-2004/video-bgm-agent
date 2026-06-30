import cv2
import numpy as np
from typing import List, Tuple
import os
import uuid
import tempfile


class KeyFrameExtractor:
    def __init__(self, max_frames: int = 30, output_dir: str = None):
        self.max_frames = max_frames
        self._instance_id = uuid.uuid4().hex[:8]
        # cv2.imwrite 不支持中文路径，强制输出到无中文的临时目录
        if output_dir:
            self._output_dir = output_dir
        else:
            self._output_dir = tempfile.gettempdir()
        os.makedirs(self._output_dir, exist_ok=True)

    def _estimate_video_brightness(self, video_path: str, sample_count: int = 10) -> dict:
        """
        采样分析视频亮度和对比度，用于自适应场景检测阈值

        Returns:
            {"avg_brightness": 0-255, "avg_contrast": 0-255, "threshold": float}
        """
        cap = cv2.VideoCapture(video_path)
        fps = max(int(cap.get(cv2.CAP_PROP_FPS)), 1)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        brightnesses = []
        contrasts = []

        # 均匀采样 sample_count 帧
        for i in range(sample_count):
            t = (i / sample_count) * duration
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightnesses.append(np.mean(gray))
                contrasts.append(np.std(gray))
        cap.release()

        if not brightnesses:
            return {"avg_brightness": 128, "avg_contrast": 64, "threshold": 30.0}

        avg_brightness = np.mean(brightnesses)
        avg_contrast = np.mean(contrasts)

        # 自适应阈值逻辑：
        # - 低对比度（室内/夜景/雾天）→ 降低阈值，避免漏检
        # - 高对比度（户外/白天/强光）→ 提高阈值，避免误检
        # - 低亮度整体 → 适当降低阈值（暗场景变化不明显）
        if avg_contrast < 30:
            # 低对比度：阈值降到 15-20
            threshold = 15.0 + (avg_contrast / 30) * 5  # 15~20
        elif avg_contrast > 70:
            # 高对比度：阈值升到 35-45
            threshold = 35.0 + ((avg_contrast - 70) / 60) * 10  # 35~45
        else:
            # 中等对比度：阈值 25-35
            threshold = 25.0 + ((avg_contrast - 30) / 40) * 10  # 25~35

        # 低亮度补偿：整体偏暗时再降一点
        if avg_brightness < 60:
            threshold *= 0.8

        threshold = max(10.0, min(50.0, threshold))

        print(f"[关键帧] 亮度={avg_brightness:.0f}, 对比度={avg_contrast:.0f}, 自适应阈值={threshold:.1f}")

        return {
            "avg_brightness": avg_brightness,
            "avg_contrast": avg_contrast,
            "threshold": threshold,
        }

    def extract(self, video_path: str) -> List[str]:
        """
        分层采样策略提取关键帧

        三层策略：
        1. 镜头边界检测 - 使用PySceneDetect识别场景切换点
        2. 均匀补充采样 - 长镜头（>6秒）每4秒取一帧，短镜头取中间帧
        3. 高潮片段采样 - 基于帧差检测运动量最大的时间点
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 验证视频格式
        valid_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
        if not video_path.lower().endswith(valid_extensions):
            raise ValueError(f"不支持的视频格式，仅支持: {', '.join(valid_extensions)}")

        # 第一层：镜头边界检测
        scenes = self._detect_scenes(video_path)

        # 第二层：均匀补充采样
        frames = self._uniform_sampling(video_path, scenes)

        # 第三层：高潮片段重点采样（简化版）
        frames = self._climax_sampling(video_path, frames)

        # 限制最大帧数
        if len(frames) > self.max_frames:
            indices = np.linspace(0, len(frames) - 1, self.max_frames, dtype=int)
            frames = [frames[i] for i in indices]

        return frames

    def _detect_scenes(self, video_path: str) -> List[Tuple[float, float]]:
        """
        使用PySceneDetect检测镜头边界（自适应阈值）

        Returns:
            List of (start_time, end_time) tuples in seconds
        """
        try:
            from scenedetect import detect, ContentDetector

            # 自适应阈值：根据视频亮度/对比度调整
            video_info = self._estimate_video_brightness(video_path)
            threshold = video_info["threshold"]

            scene_list = detect(video_path, ContentDetector(threshold=threshold))
            scenes = [(s[0].seconds, s[1].seconds) for s in scene_list]
            print(f"[关键帧] 检测到 {len(scenes)} 个场景（阈值={threshold:.1f}）")
            return scenes
        except Exception:
            # 降级：返回均匀分割
            cap = cv2.VideoCapture(video_path)
            fps = max(int(cap.get(cv2.CAP_PROP_FPS)), 1)
            duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
            cap.release()
            return [(0, duration)]

    def _uniform_sampling(self, video_path: str, scenes: List[Tuple[float, float]]) -> List[str]:
        """
        均匀补充采样：长镜头（>6秒）每4-6秒取一帧

        Args:
            video_path: 视频文件路径
            scenes: 场景列表 [(start, end), ...]

        Returns:
            帧图片路径列表
        """
        frames = []
        cap = cv2.VideoCapture(video_path)
        fps = max(int(cap.get(cv2.CAP_PROP_FPS)), 1)

        for start, end in scenes:
            duration = end - start
            if duration > 6:
                # 长镜头：每4秒取一帧
                for t in range(0, int(duration), 4):
                    frame_num = int((start + t) * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                    ret, frame = cap.read()
                    if ret:
                        frame_path = os.path.join(
                            self._output_dir,
                            f"frame_{self._instance_id}_{len(frames)}.jpg"
                        )
                        cv2.imwrite(frame_path, frame)
                        frames.append(frame_path)
            else:
                # 短镜头：取中间帧
                mid = (start + end) / 2
                frame_num = int(mid * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    frame_path = os.path.join(
                        self._output_dir,
                        f"frame_{self._instance_id}_{len(frames)}.jpg"
                    )
                    cv2.imwrite(frame_path, frame)
                    frames.append(frame_path)

        cap.release()
        return frames

    def _climax_sampling(self, video_path: str, existing_frames: List[str]) -> List[str]:
        """
        高潮片段重点采样（简化版：基于帧差检测运动）

        检测运动量最大的时间点，补充关键帧。

        Args:
            video_path: 视频文件路径
            existing_frames: 已提取的帧路径列表

        Returns:
            更新后的帧路径列表
        """
        if len(existing_frames) >= self.max_frames:
            return existing_frames

        cap = cv2.VideoCapture(video_path)
        fps = max(int(cap.get(cv2.CAP_PROP_FPS)), 1)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # 简化的高潮检测：每隔1秒检测帧差
        prev_frame = None
        motion_scores = []

        for i in range(0, total_frames, fps):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_frame is not None:
                    diff = cv2.absdiff(prev_frame, gray)
                    motion_scores.append((i / fps, np.mean(diff)))
                prev_frame = gray

        cap.release()

        # 选取运动最大的3个时间点
        if motion_scores:
            motion_scores.sort(key=lambda x: x[1], reverse=True)
            for time_point, _ in motion_scores[:3]:
                cap = cv2.VideoCapture(video_path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(time_point * fps))
                ret, frame = cap.read()
                if ret:
                    frame_path = os.path.join(
                        self._output_dir,
                        f"climax_{self._instance_id}_{len(existing_frames)}.jpg"
                    )
                    cv2.imwrite(frame_path, frame)
                    existing_frames.append(frame_path)
                cap.release()

        return existing_frames
