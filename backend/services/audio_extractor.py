"""从视频中提取音频轨道（moviepy → WAV）"""

import os
import sys
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class AudioExtractor:
    """从视频中提取 WAV 音频"""

    def extract(self, video_path: str, output_dir: str) -> str:
        """
        提取音频为 WAV（22050Hz 单声道，匹配 librosa）
        返回 WAV 文件路径
        """
        from moviepy import VideoFileClip

        os.makedirs(output_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(video_path))[0]
        wav_path = os.path.join(output_dir, f"{basename}_audio.wav")

        clip = VideoFileClip(video_path)
        audio = clip.audio

        if audio is None:
            raise ValueError("视频没有音轨")

        # 导出为 WAV
        audio.write_audiofile(
            wav_path,
            fps=22050,
            nbytes=2,
            codec="pcm_s16le",
            logger=None,
        )

        clip.close()

        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"WAV 文件未生成: {wav_path}")

        return wav_path

    def get_video_info(self, video_path: str) -> dict:
        """获取视频基本信息"""
        from moviepy import VideoFileClip

        clip = VideoFileClip(video_path)
        duration = clip.duration
        w, h = clip.size
        clip.close()

        return {"duration": duration, "width": w, "height": h}
