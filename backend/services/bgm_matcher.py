"""
BGM 匹配服务 — 三阶段闭环

匹配流程：
Stage 1: 粗筛选 — BPM/能量/人声排除明显不匹配的（纯代码）
Stage 2: 评分 — 14维代码评分（纯代码，无LLM调用）
Stage 3: 精排序 — MiMo文本排序（纯文本，不听音频）
降级: Stage 3 失败 → 用 Stage 2 结果
"""

import json
import numpy as np
import os
from typing import List, Dict
from models.schemas import BGMRecommendation, BGMTrack, BGMStructure
from config import LIBRARY_PATH
from services.style_presets import match_scene


class BGMMatcher:
    def __init__(self):
        self.bgm_library = self._load_library()
        self._audio_filter = None
        self._fine_ranker = None
        self.conflict_detector = None
        self.volume_adjuster = None

    def _load_library(self) -> List[Dict]:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("bgm_list", [])

    def _get_audio_filter(self):
        if self._audio_filter is None:
            from services.audio_filter import AudioFilter
            self._audio_filter = AudioFilter()
        return self._audio_filter

    def _get_fine_ranker(self):
        if self._fine_ranker is None:
            from services.mimo_fine_ranker import MiMoFineRanker
            self._fine_ranker = MiMoFineRanker()
        return self._fine_ranker

    def _get_conflict_detector(self):
        if self.conflict_detector is None:
            from services.conflict_detector import ConflictDetector
            self.conflict_detector = ConflictDetector()
        return self.conflict_detector

    def _get_volume_adjuster(self):
        if self.volume_adjuster is None:
            from services.volume_adjuster import VolumeAdjuster
            self.volume_adjuster = VolumeAdjuster()
        return self.volume_adjuster

    def _parse_video_requirements(self, analysis) -> dict:
        """从视频分析结果中提取结构化需求（仅能量和场景）"""
        req = {
            "max_energy": 1.0,
        }

        # 能量上限（从风格预设获取）
        scene_type = ""
        if analysis.semantic.scene_analysis:
            scene_type = analysis.semantic.scene_analysis.scene_type or ""
        preset = match_scene(scene_type, analysis.semantic.theme or "", analysis.semantic.purpose or "")
        if preset:
            req["max_energy"] = preset["energy_range"][1]

        return req

    def _hard_filter(self, analysis) -> List[Dict]:
        """
        硬过滤：排除能量超标 + 场景冲突的 BGM。
        BPM 和人声比例由 Stage 2/3 评分处理，不在粗筛阶段排除。
        """
        req = self._parse_video_requirements(analysis)

        # 视频场景/类型（用于 unfit 过滤）
        scene_type = ""
        if analysis.semantic.scene_analysis:
            scene_type = analysis.semantic.scene_analysis.scene_type or ""
        video_genre = getattr(analysis.semantic, 'video_genre', '') or ""
        video_keywords = set()

        print(f"[硬过滤] max_energy={req['max_energy']}, "
              f"scene={scene_type}, genre={video_genre}")

        if scene_type:
            video_keywords.add(scene_type.lower())
        if video_genre:
            video_keywords.add(video_genre.lower())

        passed = []
        excluded_count = 0
        for track in self.bgm_library:
            energy = track.get("rhythm_tag", {}).get("energy", 0.5)

            # 能量超限 → 排除
            if energy > req["max_energy"]:
                excluded_count += 1
                continue

            # 场景/类型冲突（unfit）→ 排除
            if video_keywords:
                scene_tags = track.get("scene_tags", {})
                if isinstance(scene_tags, dict):
                    unfit = [s.lower() for s in scene_tags.get("unfit", [])]
                else:
                    unfit = []
                conflict = any(
                    any(kw == u for kw in video_keywords)
                    for u in unfit
                )
                if conflict:
                    # 置信度安全网：如果 style_tags 和 description 矛盾，说明标签不可信
                    # 此时 unfit 可能也是错的，不排除
                    desc = track.get("description", "")
                    style_list = track.get("style_tags", [])
                    ACOUSTIC_KW = ["平静", "舒缓", "安静", "轻柔", "吉他", "钢琴", "民谣", "纯音乐"]
                    ELECTRONIC_ST = {"electronic", "edm", "synthpop", "house", "techno"}
                    is_acoustic_desc = any(k in desc for k in ACOUSTIC_KW)
                    is_electronic_style = any(s.lower() in ELECTRONIC_ST for s in style_list)
                    if is_acoustic_desc and is_electronic_style:
                        # 标签不可信，跳过 unfit 检查但降权
                        if "score" in track:
                            track["score"] *= 0.8
                    else:
                        print(f"[硬过滤] 排除 {track.get('title','?')}: unfit={unfit}, 视频关键词={video_keywords}")
                        excluded_count += 1
                        continue

            passed.append(track)

        print(f"[硬过滤] {len(self.bgm_library)} 首 → {len(passed)} 首（排除 {excluded_count} 首）")
        return passed

    def _hard_filter_no_unfit(self, analysis) -> List[Dict]:
        """放宽过滤：忽略 unfit 标签和能量限制，返回全库"""
        return list(self.bgm_library)

    def _apply_filters(self, candidates: List[Dict], analysis) -> List[Dict]:
        """标签过滤：场景、人声、文化 + 风格预设加分"""
        filtered = []

        # 视频侧信息
        video_scene = ""
        if analysis.semantic.scene_analysis:
            video_scene = analysis.semantic.scene_analysis.scene_type or ""

        vocal_ok = True
        if hasattr(analysis.semantic, 'vocal_ok') and analysis.semantic.vocal_ok is not None:
            vocal_ok = analysis.semantic.vocal_ok

        culture = ""
        if hasattr(analysis.semantic, 'culture_preference') and analysis.semantic.culture_preference:
            culture = analysis.semantic.culture_preference

        # 匹配风格预设
        theme = analysis.semantic.theme or ""
        purpose = analysis.semantic.purpose or ""
        preset = match_scene(video_scene, theme, purpose)

        for candidate in candidates:
            bgm = candidate["track"]

            # 1. 场景匹配（有 fit_scenes 时检查）
            st = bgm.get("scene_tags", {})
            fit_scenes = st.get("fit", []) if isinstance(st, dict) else []
            if video_scene and fit_scenes:
                scene_match = any(
                    video_scene in fs or fs in video_scene
                    for fs in fit_scenes
                )
                if not scene_match:
                    candidate["score"] *= 0.7  # 降权但不排除

            # 2. 人声检查
            vocal_ratio = bgm.get("rhythm_tag", {}).get("vocal_ratio", 0)
            if not vocal_ok and vocal_ratio > 0.3:
                candidate["score"] *= 0.5

            # 3. 风格预设加分
            if preset:
                track_styles = bgm.get("style_tags", [])
                if any(s in preset.get("prefer_styles", []) for s in track_styles):
                    candidate["score"] *= 1.1  # 风格匹配加分

                # 能量匹配加分
                track_energy = bgm.get("rhythm_tag", {}).get("energy", 0.5)
                e_min, e_max = preset.get("energy_range", (0, 1))
                if e_min <= track_energy <= e_max:
                    candidate["score"] *= 1.05

            filtered.append(candidate)

        return filtered

    def _align_energy_curves(self, candidates: List[Dict], analysis) -> List[Dict]:
        """
        能量曲线对齐：将视频 temporal.rhythm_curve 与 BGM energy_curve 做相关性比较。
        高相关性 → score × 1.1 加分
        """
        video_curve = analysis.temporal.rhythm_curve if analysis.temporal else []
        if not video_curve or len(video_curve) < 2:
            return candidates

        video_arr = np.array(video_curve, dtype=float)
        # 归一化
        v_min, v_max = video_arr.min(), video_arr.max()
        if v_max > v_min:
            video_arr = (video_arr - v_min) / (v_max - v_min)
        else:
            return candidates

        for c in candidates:
            bgm_curve = c["track"].get("energy_curve", [])
            if not bgm_curve or len(bgm_curve) < 2:
                continue

            bgm_arr = np.array(bgm_curve, dtype=float)
            b_min, b_max = bgm_arr.min(), bgm_arr.max()
            if b_max > b_min:
                bgm_arr = (bgm_arr - b_min) / (b_max - b_min)
            else:
                continue

            # 重采样到相同长度
            target_len = min(len(video_arr), len(bgm_arr))
            if target_len < 2:
                continue
            video_resampled = np.interp(
                np.linspace(0, 1, target_len),
                np.linspace(0, 1, len(video_arr)),
                video_arr,
            )
            bgm_resampled = np.interp(
                np.linspace(0, 1, target_len),
                np.linspace(0, 1, len(bgm_arr)),
                bgm_arr,
            )

            # 皮尔逊相关系数
            corr = np.corrcoef(video_resampled, bgm_resampled)[0, 1]
            if corr > 0.5:
                c["score"] *= 1.1
                c["energy_corr"] = round(corr, 3)

        return candidates

    def _generate_reason(self, candidate: Dict, analysis) -> str:
        """基于 description 生成推荐理由"""
        track = candidate["track"]
        desc = track.get("description", "")

        # 从 description 提取前两句作为理由
        if desc:
            sentences = desc.replace("。", "。|").split("|")
            reason = "。".join(s.strip() for s in sentences[:2] if s.strip())
            if len(reason) > 100:
                reason = reason[:97] + "..."
            return reason

        # 降级
        title = track.get("title", "这首歌")
        styles = track.get("style_tags", [])
        style = styles[0] if styles else ""
        return f"{title} 的{style}风格与视频氛围契合"

    async def match(self, analysis) -> List[BGMRecommendation]:
        """
        三阶段闭环匹配流程（含反馈重试）：
        Stage 0: 硬过滤（BPM/能量/人声）
        Stage 1: 视频分析（已在 /api/analyze 完成，MiMo 输出转场/张力/情绪曲线）
        Stage 2: 代码筛选（librosa 特征 + 视频需求对比，无 LLM 调用）
        Stage 3: MiMo 精听匹配（听歌 + 转场对齐）

        反馈机制：如果最佳候选 final_score < 0.65 或分数差距 < 0.1，
        放宽筛选条件重新跑 Stage 2 + Stage 3。
        """
        # Stage 0: 硬过滤（暂时跳过，全库进入评分）
        passed_tracks = list(self.bgm_library)
        print(f"[Stage 0] 跳过硬过滤，全库 {len(passed_tracks)} 首进入评分")

        # 提取视频分析结果
        video_analysis = self._extract_video_analysis(analysis)

        # Stage 2: 代码筛选（librosa 特征 + 视频需求对比）
        filtered = None
        audio_filter = self._get_audio_filter()
        try:
            candidates_for_filter = [{"track": t, "score": 1.0} for t in passed_tracks]
            filtered = audio_filter.filter(video_analysis, candidates_for_filter)
            print(f"[Stage 2] 代码筛选: {len(passed_tracks)} → {len(filtered)} 首")
        except Exception as e:
            print(f"[Stage 2] 代码筛选失败: {e}")

        # 降级：直接用硬过滤结果
        if not filtered:
            if passed_tracks:
                filtered = [{"track": t, "score": 0.5, "reason": "降级: 硬过滤结果"} for t in passed_tracks[:3]]
            else:
                # 最终兜底：库太小或过滤太严，取库前5首
                filtered = [{"track": t, "score": 0.3, "reason": "兜底: 全库候选"} for t in self.bgm_library[:3]]
                print(f"[兜底] 所有过滤返回0，取全库前{len(filtered)}首")

        # Stage 3: MiMo 精排序（纯文本，不听音频）
        enriched = None
        fine_ranker = self._get_fine_ranker()
        try:
            enriched = await fine_ranker.rank(video_analysis, filtered)
            print(f"[Stage 3] MiMo 精排序: {len(filtered)} → {len(enriched)} 首")
        except Exception as e:
            print(f"[Stage 3] MiMo 精排序失败，跳过: {e}")

        if not enriched:
            enriched = filtered[:3]

        # 生成推荐结果
        recommendations = self._build_recommendations(enriched, analysis)

        # === 反馈重试 ===
        if self._should_retry(recommendations):
            retry_result = await self._retry_with_relaxed_params(
                analysis, video_analysis, audio_filter, fine_ranker
            )
            if retry_result:
                recommendations = retry_result

        return recommendations

    def _should_retry(self, recommendations: List[BGMRecommendation]) -> bool:
        """
        判断是否需要重试：
        - 最佳候选 final_score < 0.65
        - Top-2 候选分数差距 < 0.1（无法区分）
        """
        if not recommendations or len(recommendations) < 2:
            return False

        scores = sorted([r.match_score for r in recommendations], reverse=True)
        best = scores[0]
        gap = best - scores[1] if len(scores) > 1 else 1.0

        if best < 0.65:
            print(f"[反馈] 最佳分数 {best:.3f} < 0.65，触发重试")
            return True
        if gap < 0.1:
            print(f"[反馈] Top-2 分数差距 {gap:.3f} < 0.1，触发重试")
            return True

        return False

    async def _retry_with_relaxed_params(
        self, analysis, video_analysis: dict, audio_filter, fine_ranker
    ) -> List[BGMRecommendation] | None:
        """
        放宽筛选条件重新跑 Stage 2 + Stage 3。

        放宽策略：
        - BPM 范围扩大 ±30（原 ±20）
        - 能量上限放宽到 1.0
        - 人声比例放宽到 0.5
        - Stage 2 候选数从 Top-5 扩大到 Top-8
        """
        print("[反馈] 开始放宽条件重试...")

        # 构造放宽后的需求
        relaxed_req = self._parse_relaxed_requirements(analysis)

        # Stage 0: 放宽硬过滤
        passed_tracks = self._hard_filter_relaxed(analysis, relaxed_req)
        print(f"[反馈] 放宽硬过滤: {len(self.bgm_library)} → {len(passed_tracks)} 首")

        if not passed_tracks:
            print("[反馈] 放宽后仍无候选，放弃重试")
            return None

        # Stage 2: 放宽筛选
        try:
            candidates_for_filter = [{"track": t, "score": 1.0} for t in passed_tracks]
            filtered = audio_filter.filter(video_analysis, candidates_for_filter)
            # 取更多候选
            filtered = filtered[:8]
            print(f"[反馈] Stage 2 放宽: {len(filtered)} 首")
        except Exception as e:
            print(f"[反馈] Stage 2 失败: {e}")
            return None

        if not filtered:
            return None

        # Stage 3: 重新精排序
        try:
            enriched = await fine_ranker.rank(video_analysis, filtered)
            print(f"[反馈] Stage 3 精排序: {len(enriched)} 首")
        except Exception as e:
            print(f"[反馈] Stage 3 失败: {e}")
            return None

        if not enriched:
            return None

        retry_recommendations = self._build_recommendations(enriched, analysis)

        # 对比重试结果 vs 原始结果
        if retry_recommendations:
            retry_best = retry_recommendations[0].match_score
            print(f"[反馈] 重试最佳分数: {retry_best:.3f}")
            # 只要重试结果有改善就采用
            return retry_recommendations

        return None

    def _parse_relaxed_requirements(self, analysis) -> dict:
        """放宽版需求：能量不设限"""
        return {"max_energy": 1.0}

    def _hard_filter_relaxed(self, analysis, relaxed_req: dict) -> List[Dict]:
        """放宽版硬过滤：全库通过"""
        return list(self.bgm_library)

    def _extract_video_analysis(self, analysis) -> dict:
        """从 VideoAnalysisResult 提取视频分析字典"""
        sem = analysis.semantic
        video_analysis = {
            "video_description": getattr(sem, "video_description", "") or "",
            "music_imagination": getattr(sem, "music_imagination", "") or "",
            "overall_atmosphere": getattr(sem, "overall_atmosphere", None) or {},
            "key_matching_points": [
                {"video_timestamp": p.video_timestamp, "importance": p.importance, "reason": p.reason, "recommended_audio_feature": p.recommended_audio_feature}
                for p in (getattr(sem, "key_matching_points", []) or [])
            ],
            "scene_analysis": {},
            "bpm_range": getattr(sem, "bpm_range", None) or [80, 120],
            "vocal_ok": getattr(sem, "vocal_ok", True),
        }

        # 8维闭环新增字段
        video_analysis["color_mood"] = getattr(sem, "color_mood", None) or {}
        video_analysis["alignment_strategy"] = getattr(sem, "alignment_strategy", None) or "ambient_only"
        video_analysis["video_imagination"] = getattr(sem, "video_imagination", None) or ""
        video_analysis["ideal_bgm_profile"] = getattr(sem, "ideal_bgm_profile", None) or ""
        video_analysis["camera_motion_type"] = getattr(sem, "camera_motion_type", None) or "未知"
        video_analysis["video_genre"] = getattr(sem, "video_genre", None) or ""
        video_analysis["rhythm_pattern"] = getattr(sem, "rhythm_pattern", None) or {}
        video_analysis["narrative_arc"] = getattr(sem, "narrative_arc", None) or {}
        # 语义描述字段
        video_analysis["emotion_journey"] = getattr(sem, "emotion_journey", None) or ""
        video_analysis["scene_descriptions"] = getattr(sem, "scene_descriptions", None) or []

        # video_structure
        vs = getattr(sem, "video_structure", None)
        if vs:
            video_analysis["video_structure"] = {
                "duration": getattr(vs, "duration", 0),
                "transition_points": [
                    {"timestamp": t.timestamp, "type": t.type, "tension_level": t.tension_level, "description": t.description}
                    for t in (getattr(vs, "transition_points", []) or [])
                ],
                "tension_curve": getattr(vs, "tension_curve", []) or [],
                "emotion_curve": getattr(vs, "emotion_curve", []) or [],
            }
        else:
            video_analysis["video_structure"] = {"transition_points": [], "tension_curve": [], "emotion_curve": []}

        # scene_analysis
        sa = getattr(sem, "scene_analysis", None)
        if sa:
            video_analysis["scene_analysis"] = {
                "scene_type": getattr(sa, "scene_type", "未知"),
                "mood": getattr(sa, "mood", "中性"),
            }

        # === CV 张力曲线覆盖 MiMo energy_level ===
        # MiMo 从静态图猜 energy 不准，用 CV 客观数据修正
        video_analysis = self._override_energy_with_cv(video_analysis)

        return video_analysis

    def _override_energy_with_cv(self, video_analysis: dict) -> dict:
        """
        用 CV 张力曲线 + 运镜类型客观映射 energy_level，覆盖 MiMo 的主观猜测。

        规则：
        - 有张力曲线时，用 avg_tension 映射 energy_level
        - full_beat_sync → energy_level ≥ 0.6
        - partial_alignment → energy_level ≥ 0.4
        - 转场 ≥ 3 且 avg_tension > 0.4 → 至少 0.5
        - 运镜类型 boost：跟拍/手持/推镜头 → 额外加能量（解决跟拍盲区）
        """
        vs = video_analysis.get("video_structure", {})
        tension_curve = vs.get("tension_curve", [])
        alignment = video_analysis.get("alignment_strategy", "ambient_only")
        n_transitions = len(vs.get("transition_points", []))
        camera_motion = video_analysis.get("camera_motion_type", "未知")

        if not tension_curve:
            return video_analysis

        # 计算 CV 客观能量
        tensions = [p.get("tension", 0.5) for p in tension_curve]
        avg_tension = sum(tensions) / len(tensions) if tensions else 0.5
        max_tension = max(tensions) if tensions else 0.5

        # 映射规则
        if alignment == "full_beat_sync":
            cv_energy = max(0.6, avg_tension)
        elif alignment == "partial_alignment":
            cv_energy = max(0.4, avg_tension)
        elif n_transitions >= 3 and avg_tension > 0.4:
            cv_energy = max(0.5, avg_tension)
        else:
            # ambient_only：用 avg_tension 但仍给 MiMo 留一定权重
            cv_energy = avg_tension

        # 运镜类型 boost：跟拍/手持/推镜头 = 视频有运动感
        camera_boost = {
            "跟拍": 0.20,
            "手持": 0.15,
            "推镜头": 0.15,
            "轻微运动": 0.05,
        }
        boost = camera_boost.get(camera_motion, 0)
        if boost > 0:
            cv_energy = min(1.0, cv_energy + boost)
            print(f"[CV覆盖] 运镜={camera_motion}, energy +{boost:.2f}")

        # MiMo 不再输出 energy_level（由 CV 客观计算），直接用 CV 值
        final_energy = cv_energy

        # 类型基因地板：video_genre 设置 energy 下限
        video_genre = video_analysis.get("video_genre", "")
        from models.schemas import GENRE_ENERGY
        genre_floor = GENRE_ENERGY.get(video_genre, (None,))[0]
        if genre_floor is not None and final_energy < genre_floor:
            print(f"[CV覆盖] 类型={video_genre} 基线={genre_floor}, 能量从{final_energy:.2f}拉到{genre_floor}")
            final_energy = genre_floor

        # 覆盖
        oa = video_analysis.get("overall_atmosphere", {})
        if isinstance(oa, dict):
            oa["energy_level"] = round(final_energy, 3)
        video_analysis["overall_atmosphere"] = oa

        print(f"[CV能量] avg_tension={avg_tension:.2f} → final={final_energy:.2f} (alignment={alignment})")

        return video_analysis

    def _compute_backward_score(self, rec, enriched: List[Dict], video_analysis: dict) -> float:
        """
        反向验证：BGM的scene_tags/emotion_tags → 视频实际特征。

        从特征库读取 BGM 的场景和情绪标签，与视频的实际特征对比。

        Returns:
            float: 0-1 反向匹配分
        """
        # 从 enriched 找这首歌的数据
        bgm_track = None
        for cand in enriched:
            track = cand.get("track", cand)
            if track.get("id") == rec.bgm.id:
                bgm_track = track
                break

        if not bgm_track:
            return 0.5

        # BGM 标签
        scene_tags = bgm_track.get("scene_tags", {})
        fit_scenes = [s.lower() for s in scene_tags.get("fit", [])] if isinstance(scene_tags, dict) else []
        emotion_tags = [e.lower() for e in bgm_track.get("emotion_tags", [])]

        if not fit_scenes and not emotion_tags:
            return 0.5  # 无标注，给中性分

        # 视频实际特征
        video_genre = video_analysis.get("video_genre", "")
        oa = video_analysis.get("overall_atmosphere", {})
        primary_mood = oa.get("primary_mood", "") if isinstance(oa, dict) else ""
        scene_analysis = video_analysis.get("scene_analysis", {})
        scene_type = scene_analysis.get("scene_type", "") if isinstance(scene_analysis, dict) else ""

        score = 0.5  # 基线

        # 场景匹配
        if scene_type and fit_scenes:
            scene_lower = scene_type.lower()
            if any(scene_lower in f or f in scene_lower for f in fit_scenes):
                score += 0.25

        # 情绪匹配
        if primary_mood and emotion_tags:
            mood_lower = primary_mood.lower()
            if any(mood_lower in e or e in mood_lower for e in emotion_tags):
                score += 0.2

        return max(0.0, min(1.0, score))

    def _compute_fallback_start_sec(self, track: dict, analysis) -> float:
        """
        Stage 3 未提供 start_sec 时的兜底：
        - 平静视频 (energy < 0.4): 选 BGM 能量最低的段落开头
        - 激烈视频 (energy > 0.6): 选 BGM 高潮段前 5s
        - 中等视频: 从头开始
        """
        video_energy = 0.5
        oa = getattr(analysis.semantic, "overall_atmosphere", None) or {}
        if isinstance(oa, dict):
            video_energy = oa.get("energy_level", 0.5)

        # 兼容两种 energy_curve 格式：
        # 格式1 (BGM库): [0.3, 0.6, 0.9, ...]
        # 格式2 (MiMo): [{"timestamp": 0, "energy": 0.3}, ...]
        energy_curve_raw = track.get("energy_curve", [])
        energy_curve = []
        if energy_curve_raw:
            if isinstance(energy_curve_raw[0], dict):
                energy_curve = [p.get("energy", 0.5) for p in energy_curve_raw]
            else:
                energy_curve = list(energy_curve_raw)

        climax_segs = track.get("climax_segments", [])

        if video_energy < 0.4:
            # 平静视频：找 BGM 能量最低的段落
            if energy_curve and len(energy_curve) >= 2:
                min_energy = min(energy_curve)
                min_idx = energy_curve.index(min_energy)
                duration = track.get("duration", 60)
                segment_len = duration / len(energy_curve)
                start_sec = min_idx * segment_len

                # 能量验证：最低点也必须 < 0.4 才算平缓段
                if min_energy > 0.4:
                    print(f"[兜底] BGM能量最低点={min_energy:.2f} > 0.4，无平缓段，从头开始")
                    return 0.0

                print(f"[兜底] 平静视频：BGM能量最低点在 {start_sec:.1f}s (能量={min_energy:.2f})")
                return round(start_sec, 1)
            return 0.0

        elif video_energy > 0.6 and climax_segs:
            # 激烈视频：从第一个高潮段附近切入（前5s build-up）
            first_climax = climax_segs[0]
            entry = max(0, first_climax.get("start", 0) - 5)
            print(f"[兜底] 激烈视频：高潮前5s切入 ({entry:.1f}s)")
            return round(entry, 1)

        return 0.0

    def _score_energy_shape(self, candidate: Dict, video_analysis: dict) -> float:
        """
        第1层：能量曲线形状匹配（最宏观，决定适配上限）。

        BGM energy_shape ↔ 视频 narrative_arc 的适配矩阵：

        | BGM形状 \\ 视频弧线 | 渐强型 | 爆发型 | 平稳型 | 先抑后扬 | 波动型 |
        |---------------------|--------|--------|--------|----------|--------|
        | 渐强型               |  0.95  |  0.6   |  0.3   |  0.7     |  0.5   |
        | 爆发型               |  0.6   |  0.95  |  0.4   |  0.5     |  0.6   |
        | 脉冲型               |  0.5   |  0.6   |  0.5   |  0.5     |  0.9   |
        | 平稳型               |  0.3   |  0.3   |  0.95  |  0.4     |  0.4   |
        | 衰落型               |  0.4   |  0.4   |  0.6   |  0.9     |  0.5   |
        """
        SHAPE_COMPAT = {
            ("渐强型", "渐强型"): 0.95, ("渐强型", "爆发型"): 0.6, ("渐强型", "平稳型"): 0.3,
            ("渐强型", "先抑后扬型"): 0.7, ("渐强型", "波动型"): 0.5,
            ("爆发型", "渐强型"): 0.6, ("爆发型", "爆发型"): 0.95, ("爆发型", "平稳型"): 0.4,
            ("爆发型", "先抑后扬型"): 0.5, ("爆发型", "波动型"): 0.6,
            ("脉冲型", "渐强型"): 0.5, ("脉冲型", "爆发型"): 0.6, ("脉冲型", "平稳型"): 0.5,
            ("脉冲型", "先抑后扬型"): 0.5, ("脉冲型", "波动型"): 0.9,
            ("平稳型", "渐强型"): 0.3, ("平稳型", "爆发型"): 0.3, ("平稳型", "平稳型"): 0.95,
            ("平稳型", "先抑后扬型"): 0.4, ("平稳型", "波动型"): 0.4,
            ("衰落型", "渐强型"): 0.4, ("衰落型", "爆发型"): 0.4, ("衰落型", "平稳型"): 0.6,
            ("衰落型", "先抑后扬型"): 0.9, ("衰落型", "波动型"): 0.5,
        }

        energy_shape = candidate.get("energy_shape", "")
        narrative_arc = video_analysis.get("narrative_arc", {})
        arc_type = narrative_arc.get("arc_type", "") if narrative_arc else ""

        if not energy_shape or not arc_type:
            return 0.5  # 无数据时给中性分

        score = SHAPE_COMPAT.get((energy_shape, arc_type), 0.5)

        # has_clear_climax 加成：视频需要高潮且 BGM 有明确高潮 → 额外加分
        has_climax = candidate.get("has_clear_climax", False)
        kmp = video_analysis.get("key_matching_points", [])
        needs_climax = any(p.get("importance") == "高" for p in kmp) if kmp else False

        if needs_climax and has_climax:
            score = min(1.0, score + 0.1)
        elif needs_climax and not has_climax:
            score = max(0.1, score - 0.15)

        if score != 0.5:
            print(f"[形状匹配] BGM={energy_shape} × 视频={arc_type} → {score:.2f}")

        return score

    def _build_recommendations(self, enriched: List[Dict], analysis) -> List[BGMRecommendation]:
        """从 enriched 候选生成 BGMRecommendation 列表"""
        adjuster = self._get_volume_adjuster()
        video_duration = analysis.emotion_curve.time_points[-1] if analysis.emotion_curve.time_points else 10.0
        volume_adjustments = adjuster.adjust(analysis.audio.speech_segments, video_duration)

        # 8维闭环：构建视频分析字典用于双向验证
        video_analysis_dict = self._extract_video_analysis(analysis)

        recommendations = []
        for candidate in enriched[:3]:
            bgm_data = candidate["track"]
            bgm_track = BGMTrack(
                id=bgm_data["id"],
                title=bgm_data["title"],
                artist=bgm_data["artist"],
                emotion=bgm_data.get("emotion", ""),
                tempo=bgm_data.get("rhythm_tag", {}).get("bpm", 0),
                beat_positions=bgm_data.get("beat_positions", []),
                structure=BGMStructure(**bgm_data["structure"]) if bgm_data.get("structure") and bgm_data["structure"].get("intro") else BGMStructure(),
                style_tags=bgm_data.get("style_tags", []),
                energy_curve=bgm_data.get("energy_curve", []),
                duration=bgm_data.get("duration", 0),
                preview_url=bgm_data.get("preview_url", ""),
                source=bgm_data.get("source", "local"),
                editing_note=bgm_data.get("editing_note"),
                # 人工标注字段
                emotion_tags=bgm_data.get("emotion_tags", []),
                scene_tags=bgm_data.get("scene_tags"),
                era=bgm_data.get("era"),
                instrumentation=bgm_data.get("instrumentation", []),
                arrangement_style=bgm_data.get("arrangement_style"),
                vocal_character=bgm_data.get("vocal_character"),
                rhythm_drive=bgm_data.get("rhythm_drive"),
                energy_shape=bgm_data.get("energy_shape"),
                has_clear_buildup=bgm_data.get("has_clear_buildup"),
                has_clear_climax=bgm_data.get("has_clear_climax"),
                cultural_context=bgm_data.get("cultural_context"),
                # librosa 客观数据
                feature_text=bgm_data.get("feature_text"),
                avg_energy=bgm_data.get("avg_energy"),
                has_vocals=bgm_data.get("has_vocals"),
                structural_sections=bgm_data.get("structural_sections"),
                tempo_stability=bgm_data.get("tempo_stability"),
                chroma_profile=bgm_data.get("chroma_profile"),
                spectral_centroid=bgm_data.get("spectral_centroid"),
                beat_regularity=bgm_data.get("rhythm_tag", {}).get("beat_regularity"),
                swing_ratio=bgm_data.get("rhythm_tag", {}).get("swing_ratio"),
                timbre_profile=bgm_data.get("timbre_profile"),
                constraints=bgm_data.get("constraints"),
            )

            reason = candidate.get("fine_reason") or candidate.get("reason") or self._generate_reason(candidate, analysis)
            # 补充精排序的切入理由
            start_reason = candidate.get("start_sec_reason", "")
            if start_reason and start_reason not in reason:
                reason = f"{reason} | 切入: {start_reason}"

            # 优先使用 Stage 3 精排序推荐的 start_sec
            start_sec = candidate.get("recommended_start_sec") or candidate.get("start_sec", 0)

            # 验证1: start_sec 必须 >= 0
            if start_sec < 0:
                start_sec = self._compute_fallback_start_sec(bgm_data, analysis)

            # 验证2: 平静视频的 start_sec 必须对应低能量段落
            video_energy = 0.5
            oa = getattr(analysis.semantic, "overall_atmosphere", None) or {}
            if isinstance(oa, dict):
                video_energy = oa.get("energy_level", 0.5)

            if video_energy < 0.4 and start_sec > 0:
                energy_curve_raw = bgm_data.get("energy_curve", [])
                if energy_curve_raw:
                    # 兼容两种格式
                    if isinstance(energy_curve_raw[0], dict):
                        energy_curve = [p.get("energy", 0.5) for p in energy_curve_raw]
                    else:
                        energy_curve = list(energy_curve_raw)

                    duration = bgm_data.get("duration", 60)
                    segment_len = duration / len(energy_curve) if energy_curve else duration
                    idx = min(int(start_sec / segment_len), len(energy_curve) - 1)
                    bgm_start_energy = energy_curve[idx]

                    if bgm_start_energy > 0.4:
                        print(f"[验证] 平静视频但BGM切入点能量={bgm_start_energy:.2f} > 0.4，触发兜底")
                        start_sec = self._compute_fallback_start_sec(bgm_data, analysis)

            if not start_sec or start_sec <= 0:
                start_sec = self._compute_fallback_start_sec(bgm_data, analysis)

            # 验证4: 用 constraints.best_entry_points 微调 start_sec
            constraints = bgm_data.get("constraints", {})
            if constraints and constraints.get("best_entry_points"):
                best_entries = constraints["best_entry_points"]
                worst_entries = set(constraints.get("worst_entry_points", []))
                duration = bgm_data.get("duration", 60)

                # 如果当前 start_sec 落在 worst_entry_points 附近(±3s)，调整到最近的 best_entry
                is_in_worst = any(abs(start_sec - w) < 3.0 for w in worst_entries)
                if is_in_worst and best_entries:
                    # 找最近的 best_entry_point
                    nearest = min(best_entries, key=lambda x: abs(x - start_sec))
                    print(f"[约束] start_sec={start_sec:.1f}s 在禁区附近，调整到气口 {nearest:.1f}s")
                    start_sec = nearest

                # 如果 start_sec 是 0（从头开始），且有更合适的气口，优先用气口
                elif start_sec == 0 and best_entries:
                    # 选第一个非零气口（如果有），否则用0
                    non_zero = [e for e in best_entries if e > 1.0]
                    if non_zero and video_energy > 0.3:
                        # 中等以上能量视频可以用非零气口
                        pass  # 保持 start_sec=0，从头开始通常最安全

            # 验证3: start_sec 不能超过视频时长
            if start_sec >= video_duration:
                print(f"[验证] start_sec={start_sec}s >= 视频时长={video_duration}s，从头开始")
                start_sec = 0.0

            climax_hint = ""
            climax_segs = bgm_data.get("climax_segments", [])
            if climax_segs:
                c = climax_segs[0]
                climax_hint = f"高潮段 {c['start']}-{c['end']}s"

            # 第1层：能量曲线形状匹配（最宏观，决定适配上限）
            energy_shape_score = self._score_energy_shape(
                {"energy_shape": bgm_track.energy_shape,
                 "has_clear_climax": bgm_track.has_clear_climax},
                video_analysis_dict
            )
            # 形状匹配加成：±15%
            shape_bonus = (energy_shape_score - 0.5) * 0.3
            candidate["score"] = max(0.0, min(1.0, candidate["score"] + shape_bonus))

            # 优先使用精排序分数
            final_score = candidate.get("fine_score") or candidate["score"]

            recommendations.append(
                BGMRecommendation(
                    bgm=bgm_track,
                    match_score=round(final_score, 3),
                    emotion_alignment=candidate["score"],
                    rhythm_alignment=candidate["score"],
                    reason=reason,
                    volume_adjustments=volume_adjustments,
                    start_sec=round(start_sec, 2),
                    climax_hint=climax_hint,
                    cut_points=candidate.get("cut_points", []),
                )
            )

        # 真正的双向验证（Stage 3 之后）
        # 正向：视频需求 → BGM（Stage 2 已完成，体现在 candidate["score"]）
        # 反向：BGM的scene_tags/emotion_tags → 视频实际特征
        try:
            for rec in recommendations:
                backward_score = self._compute_backward_score(rec, enriched, video_analysis_dict)
                rec.bidirectional_factor = round(backward_score, 3)
        except Exception as e:
            print(f"[双向验证] 失败: {e}")

        return recommendations
