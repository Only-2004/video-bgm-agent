from typing import Dict, List


class ConflictDetector:
    def __init__(self):
        pass

    def detect(self, bgm: Dict, analysis_audio: Dict) -> bool:
        """
        检测BGM与视频是否存在冲突

        冲突类型：
        1. 人声区域BGM能量过高
        2. 情绪严重不匹配
        """
        speech_segments = analysis_audio.get("speech_segments", [])

        # 如果没有人声，无冲突
        if not speech_segments:
            return False

        # 检查人声区域
        for segment in speech_segments:
            if len(segment) == 2:
                start, end = segment
                duration = end - start

                # 人声片段较短（<2秒）且BGM能量高，可能存在冲突
                if duration < 2 and bgm.get("rhythm_tag", {}).get("bpm", 0) > 140:
                    return True

        return False

    def has_emotion_mismatch(self, bgm_emotion: str, video_emotion: str) -> bool:
        """检测情绪是否严重不匹配"""
        mismatch_pairs = [
            ("悲伤", "兴奋"),
            ("兴奋", "悲伤"),
            ("紧张", "温馨"),
            ("温馨", "紧张"),
        ]
        return (bgm_emotion, video_emotion) in mismatch_pairs
