import asyncio
import httpx
import json
import os
from typing import List, Dict, Any, Optional


class MiMoAnalyzer:
    """MiMo-V2-Omni 统一视频分析服务（单次调用，一致性约束）"""

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = api_key or os.getenv(
            "MIMO_API_KEY", "sk-CpfQyqJEPcd5JPbDHEjG3MIlmbKoJwka"
        )
        self.api_url = api_url or os.getenv(
            "MIMO_API_URL", "https://ai.iapp.dpdns.org"
        )
        self.unified_prompt = self._load_unified_prompt()

    def _load_unified_prompt(self) -> str:
        """加载统一分析 prompt"""
        prompt_dir = os.path.join(os.path.dirname(__file__), "../prompts")
        path = os.path.join(prompt_dir, "unified_analysis.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _build_prompt(self, cv_data: dict) -> str:
        """将 CV 数据注入统一 prompt 模板"""
        template = self.unified_prompt
        if not template:
            return ""

        import json

        transitions = cv_data.get("transitions", [])
        transitions_json = json.dumps(transitions, ensure_ascii=False, indent=2)

        tension_curve = cv_data.get("tension_curve", [])
        if tension_curve:
            max_t = max(t["tension"] for t in tension_curve)
            avg_t = sum(t["tension"] for t in tension_curve) / len(tension_curve)
            high_points = [t for t in tension_curve if t["tension"] > 0.6]
            tension_summary = (
                f"采样{len(tension_curve)}个点, 平均张力={avg_t:.2f}, "
                f"最大张力={max_t:.2f}, 高张力点(>0.6)={len(high_points)}个\n"
                f"曲线: " + " → ".join(f"{t['tension']:.2f}" for t in tension_curve[:15])
            )
        else:
            tension_summary = "无数据"

        color_mood = json.dumps(cv_data.get("color_mood", {}), ensure_ascii=False)
        video_audio = cv_data.get("video_audio")
        video_audio_json = json.dumps(video_audio, ensure_ascii=False) if video_audio else "无音频轨"

        prompt = (
            template
            .replace("{num_transitions}", str(len(transitions)))
            .replace("{transitions_json}", transitions_json)
            .replace("{tension_summary}", tension_summary)
            .replace("{color_mood_json}", color_mood)
            .replace("{video_audio_json}", video_audio_json)
            .replace("{num_keyframes}", str(len(cv_data.get("keyframe_timestamps", []))))
        )
        return prompt

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 MiMo 返回的 JSON 响应"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认降级结果（所有维度合并）"""
        return {
            "visual": {
                "scene": "未知",
                "objects": [],
                "people_count": "未知",
                "activity": "未知",
                "color_tone": "中性",
                "lighting": "自然光",
                "visual_style": "写实",
            },
            "text": {
                "has_subtitles": False,
                "subtitle_text": "",
                "on_screen_text": [],
                "text_sentiment": "中性",
            },
            "semantic": {
                "video_description": "",
                "video_genre": "",
                "overall_atmosphere": {
                    "primary_mood": "未知",
                    "secondary_mood": "",
                    "description": "",
                },
                "music_imagination": {
                    "recommended_styles": [],
                    "recommended_characteristics": {},
                    "reference_description": "",
                },
                "key_matching_points": [],
                "video_imagination": "",
                "ideal_bgm_profile": "",
                "narrative_arc": {
                    "arc_type": "平稳型",
                    "climax_position": 0.5,
                    "opening_mood": "未知",
                    "closing_mood": "未知",
                },
                "scene_analysis": {
                    "scene_type": "未知",
                    "scene_description": "",
                    "mood": "中性",
                    "visual_energy": 0.5,
                },
                "bgm_suggestion": {
                    "primary_emotion": "未知",
                    "energy_level": "未知",
                    "style_tags": [],
                    "reasoning": "",
                },
                "rhythm_suggestion": {
                    "tempo_range": "80-120",
                    "rhythm_style": "未知",
                    "sync_points": "",
                },
            },
        }

    def _call_mimo_api_sync(self, image_paths: list, prompt: str) -> str:
        """调用 MiMo-V2-Omni API（支持多图，同步版本）"""
        import base64

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "Connection": "close",
        }

        # 构建多图 content blocks
        content_blocks = []
        for i, img_path in enumerate(image_paths):
            with open(img_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data,
                },
            })

        content_blocks.append({"type": "text", "text": prompt})

        payload = {
            "model": "mimo-v2.5",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": content_blocks,
                }
            ],
        }

        with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            response = client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()

        result = response.json()
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                return item["text"]
        return ""

    async def analyze_video(self, frames: List[str], cv_data: dict = None) -> Dict[str, Any]:
        """
        统一调用 MiMo-V2-Omni 分析（单次调用，一致性约束）

        Args:
            frames: 帧图片路径列表
            cv_data: CV 管线输出（可选）

        Returns:
            包含 visual/text/semantic 的字典
        """
        if not frames:
            return self._get_default_result()

        # 构建统一 prompt
        prompt = ""
        if cv_data:
            prompt = self._build_prompt(cv_data)
        if not prompt:
            prompt = self.unified_prompt

        if not prompt:
            print("[MiMo] 无可用 prompt，返回默认值")
            return self._get_default_result()

        # 选择关键帧：均匀采样最多5帧（避免token过多，同时保证多视角覆盖）
        max_send = min(5, len(frames))
        if len(frames) <= max_send:
            selected_frames = frames
        else:
            indices = [int(i * (len(frames) - 1) / (max_send - 1)) for i in range(max_send)]
            selected_frames = [frames[i] for i in indices]
        print(f"[MiMo] 统一分析（{len(selected_frames)}帧，共{len(frames)}帧可用）...")

        # 带重试的单次调用
        import time
        retries = 5
        last_error = None

        for attempt in range(retries + 1):
            try:
                response = await asyncio.to_thread(
                    self._call_mimo_api_sync, selected_frames, prompt
                )
                result = self._parse_response(response)
                if not result:
                    raise ValueError("MiMo 返回空响应")

                # 检查关键字段
                missing = []
                if not result.get("video_description") and not result.get("overall_atmosphere"):
                    missing.append("video_description/overall_atmosphere")
                if not result.get("music_imagination"):
                    missing.append("music_imagination")
                if missing and attempt < retries:
                    print(f"[MiMo] 缺少 {missing}，重试 {attempt+1}/{retries}")
                    time.sleep(2 * (attempt + 1))
                    continue

                # 从统一响应中拆分出各维度
                visual = result.get("visual", self._get_default_result()["visual"])
                text = result.get("text", self._get_default_result()["text"])

                # semantic = 除 visual/text 以外的所有字段
                semantic = {k: v for k, v in result.items() if k not in ("visual", "text")}

                print(f"[MiMo] 统一分析完成: genre={semantic.get('video_genre', '?')}, "
                      f"mood={semantic.get('overall_atmosphere', {}).get('primary_mood', '?')}")

                return {
                    "visual": visual,
                    "text": text,
                    "semantic": semantic,
                }

            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait = min(2 * (attempt + 1), 15)
                    print(f"[MiMo] 调用失败，{wait}s 后重试 {attempt+1}/{retries}: {e}")
                    time.sleep(wait)
                    continue

        print(f"[MiMo] 最终失败（{retries+1}次重试）: {last_error}")
        return self._get_default_result()
