"""
MiMo 精排序器 — Stage 3：纯文本调用，不发送音频

接收 Stage 2 的 Top-5 候选 + 视频分析，让 MiMo 做最终排序并输出理由。
"""
import json
import os
import re
import httpx

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "fine_ranking.txt")


class MiMoFineRanker:
    def __init__(self):
        from services.mimo_analyzer import MiMoAnalyzer
        analyzer = MiMoAnalyzer()
        self.api_key = analyzer.api_key
        self.api_url = analyzer.api_url
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    async def rank(self, video_analysis: dict, candidates: list) -> list:
        """
        对 Stage 2 的候选进行精排序。

        Args:
            video_analysis: 视频分析结果 dict
            candidates: Stage 2 返回的候选列表，每项含 {"track": dict, "score": float, "reason": str}

        Returns:
            排序后的候选列表，每项增加 rank, fine_score, fine_reason, recommended_start_sec
        """
        if not candidates:
            return []

        video_text = self._build_video_text(video_analysis)
        candidates_text = self._build_candidates_text(candidates)

        prompt = (
            self.prompt_template
            .replace("{video_analysis_text}", video_text)
            .replace("{candidates_text}", candidates_text)
        )

        try:
            raw = await self._call_api(prompt)
            result = self._parse_response(raw)
            return self._merge_results(candidates, result)
        except Exception as e:
            print(f"[MiMoFineRanker] 失败: {e}，降级使用Stage 2分数")
            return self._fallback(candidates)

    def _build_video_text(self, va: dict) -> str:
        """构建视频分析文本 — 以语义描述为主，让MiMo用理解力匹配"""
        parts = []

        # === 核心：语义描述（MiMo靠理解这些来匹配） ===

        # 视频内容描述
        video_desc = va.get("video_description", "")
        if video_desc:
            parts.append(f"【视频内容】{video_desc}")

        # 整体氛围
        oa = va.get("overall_atmosphere", {})
        if isinstance(oa, dict):
            oa_parts = []
            if oa.get("primary_mood"):
                oa_parts.append(oa["primary_mood"])
            if oa.get("secondary_mood"):
                oa_parts.append(oa["secondary_mood"])
            if oa.get("description"):
                oa_parts.append(oa["description"])
            if oa_parts:
                parts.append(f"【整体氛围】{' · '.join(oa_parts)}")

        # 情绪旅程
        emotion_journey = va.get("emotion_journey", "")
        if emotion_journey:
            parts.append(f"【情绪旅程】{emotion_journey}")

        # 逐场景描述
        scene_descs = va.get("scene_descriptions", [])
        if scene_descs:
            desc_str = "；".join(
                f"{s.get('timestamp', 0)}s {s.get('description', '')}"
                for s in scene_descs[:8]
            )
            parts.append(f"【场景画面】{desc_str}")

        # 配乐灵魂画像
        video_imagination = va.get("video_imagination", "")
        if video_imagination:
            parts.append(f"【配乐灵魂画像】{video_imagination}")

        # 叙事弧线
        arc = va.get("narrative_arc", {})
        if arc and arc.get("arc_type"):
            parts.append(f"【叙事弧线】{arc['arc_type']}（{arc.get('opening_mood', '?')} → {arc.get('closing_mood', '?')}）")

        # === 补充：结构化数据（辅助参考） ===

        genre = va.get("video_genre", "")
        if genre:
            parts.append(f"视频类型: {genre}")

        energy = va.get("energy_level", 0.5)
        parts.append(f"能量等级: {energy}")

        vocal_ok = va.get("vocal_ok", True)
        if not vocal_ok:
            parts.append("不允许人声")

        return "\n".join(parts)

    def _build_candidates_text(self, candidates: list) -> str:
        """构建候选BGM文本"""
        blocks = []
        for i, c in enumerate(candidates):
            track = c.get("track", c)
            lines = []
            lines.append(f"=== 候选{i+1}: {track.get('title', '?')} (ID: {track.get('id', '?')}) ===")
            lines.append(f"Stage2分数: {c.get('score', 0):.3f}")

            # 基本音频数据
            lines.append(f"BPM: {track.get('tempo', '?')}")
            lines.append(f"时长: {track.get('duration', '?')}s")
            lines.append(f"能量(百分位): {track.get('avg_energy', '?')}")
            lines.append(f"频谱质心: {track.get('spectral_centroid', '?')}Hz")

            # 人工标注字段
            if track.get("style_tags"):
                lines.append(f"风格: {track['style_tags']}")
            if track.get("emotion_tags"):
                lines.append(f"情绪: {track['emotion_tags']}")
            sc = track.get("scene_tags", {})
            if sc:
                if isinstance(sc, dict):
                    lines.append(f"适合场景: {sc.get('fit', [])}")
                    lines.append(f"不适合场景: {sc.get('unfit', [])}")
                elif isinstance(sc, list):
                    lines.append(f"场景: {sc}")
            if track.get("era"):
                lines.append(f"年代: {track['era']}")
            if track.get("instrumentation"):
                lines.append(f"乐器: {track['instrumentation']}")
            if track.get("arrangement_style"):
                lines.append(f"编曲风格: {track['arrangement_style']}")
            if track.get("vocal_character"):
                lines.append(f"人声: {track['vocal_character']}")
            if track.get("rhythm_drive"):
                lines.append(f"节奏驱动: {track['rhythm_drive']}")
            if track.get("cultural_context"):
                lines.append(f"文化语境: {track['cultural_context']}")
            if track.get("energy_shape"):
                lines.append(f"能量形状: {track['energy_shape']}")
            if track.get("has_clear_buildup") is not None:
                lines.append(f"有蓄势段: {'是' if track['has_clear_buildup'] else '否'}")
            if track.get("has_clear_climax") is not None:
                lines.append(f"有明确高潮: {'是' if track['has_clear_climax'] else '否'}")

            # constraints
            cons = track.get("constraints", {})
            if cons:
                lines.append(f"最佳切入点: {cons.get('best_entry_points', [])}")

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    async def _call_api(self, prompt: str) -> str:
        """调用MiMo API（OpenAI-compatible 格式）"""
        api_url = self.api_url.rstrip("/")
        if not api_url.endswith("/v1/chat/completions"):
            api_url += "/v1/chat/completions"

        payload = {
            "model": "mimo-v2.5",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            resp = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

        result = resp.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _parse_response(self, raw: str) -> dict:
        """解析MiMo返回的JSON"""
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {"rankings": []}

    def _merge_results(self, candidates: list, result: dict) -> list:
        """将MiMo排序结果合并回候选列表"""
        rankings = result.get("rankings", [])
        if not rankings:
            return self._fallback(candidates)

        # 构建 id → ranking 映射
        rank_map = {}
        for r in rankings:
            bgm_id = r.get("bgm_id", "")
            rank_map[bgm_id] = r

        # 按MiMo排序重排候选
        ranked = []
        for r in rankings:
            bgm_id = r.get("bgm_id", "")
            # 找到对应候选
            for c in candidates:
                track = c.get("track", c)
                if track.get("id") == bgm_id:
                    c["fine_rank"] = r.get("rank", 0)
                    c["fine_score"] = r.get("score", c.get("score", 0))
                    c["fine_reason"] = r.get("reason", "")
                    c["recommended_start_sec"] = r.get("recommended_start_sec", 0)
                    c["start_sec_reason"] = r.get("start_sec_reason", "")
                    ranked.append(c)
                    break

        # 未被MiMo排序的候选追加到末尾
        ranked_ids = {r.get("bgm_id") for r in rankings}
        for c in candidates:
            track = c.get("track", c)
            if track.get("id") not in ranked_ids:
                c["fine_rank"] = len(ranked) + 1
                c["fine_score"] = c.get("score", 0)
                c["fine_reason"] = ""
                ranked.append(c)

        return ranked

    def _fallback(self, candidates: list) -> list:
        """降级：按Stage 2分数排序"""
        for i, c in enumerate(candidates):
            c["fine_rank"] = i + 1
            c["fine_score"] = c.get("score", 0)
            c["fine_reason"] = ""  # 不设置技术描述，让系统用Stage 2理由
        return candidates
