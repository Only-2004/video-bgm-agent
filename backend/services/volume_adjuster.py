from typing import List, Dict


class VolumeAdjuster:
    def __init__(self):
        self.speech_volume_ratio = 0.125  # -18dB
        self.transition_volume_ratio = 0.5  # -6dB
        self.transition_duration = 0.5  # 秒

    def adjust(self, speech_segments: List[List[float]], video_duration: float) -> List[Dict]:
        """
        计算BGM音量调整建议

        算法：
        1. 人声区域：降低至-18dB
        2. 非人声区域：保持原始音量
        3. 过渡区域：平滑过渡
        """
        adjustments = []

        for segment in speech_segments:
            if len(segment) != 2:
                continue

            start, end = segment

            # 人声区域：降低至-18dB
            adjustments.append({
                "start": start,
                "end": end,
                "volume_ratio": self.speech_volume_ratio,
                "reason": "人声区域",
            })

            # 人声前过渡
            if start > 0:
                adjustments.append({
                    "start": max(0, start - self.transition_duration),
                    "end": start,
                    "volume_ratio": self.transition_volume_ratio,
                    "reason": "人声前过渡",
                })

            # 人声后过渡
            if end < video_duration:
                adjustments.append({
                    "start": end,
                    "end": min(video_duration, end + self.transition_duration),
                    "volume_ratio": self.transition_volume_ratio,
                    "reason": "人声后过渡",
                })

        # 按时间排序
        adjustments.sort(key=lambda x: x["start"])

        return adjustments
