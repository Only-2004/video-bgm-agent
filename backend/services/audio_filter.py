"""
Stage 2: 纯代码逻辑筛选候选 BGM

输入：视频分析结果（来自 Stage 1）+ 硬过滤后的候选列表（来自 Stage 0）
输出：Top-5 候选（带匹配分数和理由）

不调用任何 LLM API，完全基于 librosa 客观特征 + 视频需求对比。
"""

from typing import List, Dict, Optional, Tuple
import numpy as np


# 情绪标签 → 视频 primary_mood 的映射
MOOD_EMOTION_MAP = {
    "热血": {"epic", "tension", "joy"},
    "激昂": {"epic", "tension", "joy"},
    "紧张": {"tension", "epic"},
    "平静": {"calm", "nostalgic"},
    "舒缓": {"calm", "romantic"},
    "温馨": {"romantic", "joy", "calm"},
    "浪漫": {"romantic", "calm"},
    "悲伤": {"sadness", "nostalgic"},
    "欢乐": {"joy", "epic"},
    "史诗": {"epic", "tension"},
    "悬疑": {"mysterious", "tension"},
    "神秘": {"mysterious", "tension"},
    "怀旧": {"nostalgic", "sadness"},
    "治愈": {"calm", "romantic"},
    "动感": {"joy", "epic"},
}

# 风格标签 → BGM style_tags 的映射
STYLE_KEYWORDS = {
    "电子": {"Electronic", "EDM", "Synthpop", "House", "Techno", "Trance", "Dubstep"},
    "摇滚": {"Rock", "Metal", "Punk", "Alternative"},
    "流行": {"Pop", "Dance Pop", "K-pop"},
    "古典": {"Classical", "Orchestral", "Symphony", "Chamber"},
    "民谣": {"Folk", "Acoustic", "Indie Folk"},
    "嘻哈": {"Hip-Hop", "Rap", "Trap"},
    "爵士": {"Jazz", "Swing", "Bossa Nova"},
    "R&B": {"R&B", "Soul", "Funk"},
    "轻音乐": {"Easy Listening", "Ambient", "New Age"},
    "管弦乐": {"Orchestral", "Classical", "Symphony"},
    "史诗": {"Epic", "Cinematic", "Trailer"},
    "励志": {"Epic", "Cinematic", "Uplifting"},
}


class AudioFilter:
    def __init__(self):
        pass

    def filter(self, video_analysis: dict, candidates: List[dict]) -> List[dict]:
        """
        纯代码逻辑筛选候选 BGM。

        Args:
            video_analysis: 视频分析结果（来自 Stage 1 的结构化 dict）
            candidates: 硬过滤后的候选列表，每个 {"track": dict, "score": float}

        Returns:
            Top-5 候选，每个包含 track, score, reason
        """
        if not candidates:
            return []

        reqs = self._extract_requirements(video_analysis)
        print(f"[AudioFilter] 视频需求: BPM={reqs['bpm_min']}-{reqs['bpm_max']}, "
              f"energy={reqs['energy_min']:.1f}-{reqs['energy_max']:.1f}, "
              f"transitions={reqs['n_transitions']}, vocal_ok={reqs['vocal_ok']}, "
              f"mood={reqs['primary_mood']}, styles={reqs['recommended_styles']}")

        scored = []
        for cand in candidates:
            track = cand["track"]
            score, reason_parts = self._score_track(track, reqs)
            scored.append({
                "track": track,
                "score": round(score, 4),
                "reason": "; ".join(reason_parts) if reason_parts else "综合匹配",
                "original_score": cand.get("score", 1.0),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top3 = scored[:3]

        for i, s in enumerate(top3):
            t = s["track"]
            print(f"[AudioFilter] #{i+1} {t.get('title', '?')} "
                  f"score={s['score']:.3f} | {s['reason'][:80]}")

        return top3

    # genre → energy_level 映射（从 schemas.GENRE_ENERGY 单一数据源读取）
    @staticmethod
    def _get_genre_energy_map():
        from models.schemas import GENRE_ENERGY
        return {genre: ref for genre, (_, ref) in GENRE_ENERGY.items()}

    # mood → energy_level 映射
    MOOD_ENERGY_MAP = {
        "热血激昂": 0.85,
        "紧张悬疑": 0.70,
        "自由畅快": 0.65,
        "动感活力": 0.70,
        "温暖感人": 0.45,
        "平静治愈": 0.25,
        "孤独忧郁": 0.30,
        "神秘莫测": 0.50,
        "欢乐愉快": 0.60,
        "史诗磅礴": 0.75,
    }

    def _extract_requirements(self, video_analysis: dict) -> dict:
        """从视频分析结果中提取结构化筛选需求"""
        reqs = {
            "bpm_min": 60,
            "bpm_max": 160,
            "energy_min": 0.0,
            "energy_max": 1.0,
            "energy_level": 0.5,
            "vocal_ok": True,
            "max_vocal_ratio": 100,
            "n_transitions": 0,
            "needs_climax": False,
            "primary_mood": "",
            "recommended_styles": [],
            "emotion_curve_type": "",
            "tension_values": [],
            "key_timestamps": [],
        }

        # BPM 范围
        bpm_range = video_analysis.get("bpm_range")
        if bpm_range and len(bpm_range) == 2:
            reqs["bpm_min"] = bpm_range[0]
            reqs["bpm_max"] = bpm_range[1]

        # 人声要求
        vocal_ok = video_analysis.get("vocal_ok")
        if vocal_ok is not None:
            reqs["vocal_ok"] = vocal_ok
            if not vocal_ok:
                reqs["max_vocal_ratio"] = 20

        # overall_atmosphere
        oa = video_analysis.get("overall_atmosphere", {})
        if oa:
            reqs["primary_mood"] = oa.get("primary_mood", "")

        # === 能量需求推导 ===
        # 优先级：music_imagination.energy_range > CV energy_level > genre/mood 推导 > 默认 0.5
        genre = video_analysis.get("video_genre", "")
        primary_mood = reqs["primary_mood"]

        # 先用 genre/mood 推导基线
        genre_energy = self._get_genre_energy_map().get(genre, None)
        mood_energy = self.MOOD_ENERGY_MAP.get(primary_mood, None)

        if genre_energy is not None and mood_energy is not None:
            derived_energy = max(genre_energy, mood_energy)
        elif genre_energy is not None:
            derived_energy = genre_energy
        elif mood_energy is not None:
            derived_energy = mood_energy
        else:
            derived_energy = 0.5

        # 如果 bgm_matcher 的 CV 覆盖已经设置了 energy_level，用它（更精确）
        cv_energy = oa.get("energy_level") if oa else None
        if cv_energy is not None and cv_energy != 0.5:
            # CV 覆盖值可用，取 CV 和 genre 推导的平均（兼顾客观测量和类型常识）
            reqs["energy_level"] = round((cv_energy + derived_energy) / 2, 3)
        else:
            reqs["energy_level"] = derived_energy

        el = reqs["energy_level"]
        # 宽范围：±0.20
        reqs["energy_min"] = max(0, el - 0.20)
        reqs["energy_max"] = min(1.0, el + 0.20)

        # music_imagination（可能是 dict 或 str）
        mi = video_analysis.get("music_imagination", {})
        if isinstance(mi, dict):
            reqs["recommended_styles"] = mi.get("recommended_styles", [])
            chars = mi.get("recommended_characteristics", {})
            if chars:
                # 如果 MiMo 提供了 energy_range，用它覆盖（最精确）
                er = chars.get("energy_range")
                if er and len(er) == 2:
                    reqs["energy_min"] = er[0]
                    reqs["energy_max"] = er[1]
                br = chars.get("bpm_range")
                if br and len(br) == 2:
                    reqs["bpm_min"] = br[0]
                    reqs["bpm_max"] = br[1]
                reqs["needs_climax"] = chars.get("has_climax", False)
                reqs["emotion_curve_type"] = chars.get("emotion_curve_type", "")
        elif isinstance(mi, str) and mi:
            # music_imagination 是字符串时，从中提取风格关键词
            for style_key in STYLE_KEYWORDS:
                if style_key in mi:
                    reqs["recommended_styles"].append(style_key)

        # video_structure
        vs = video_analysis.get("video_structure", {})
        if vs:
            transitions = vs.get("transition_points", [])
            reqs["n_transitions"] = len(transitions)
            reqs["key_timestamps"] = [t.get("timestamp", 0) for t in transitions[:8]]

            tension_curve = vs.get("tension_curve", [])
            if tension_curve:
                reqs["tension_values"] = [t.get("tension", 0.5) for t in tension_curve]

        # key_matching_points
        kmp = video_analysis.get("key_matching_points", [])
        if kmp:
            # 如果有高重要性匹配点，标记需要高潮
            high_importance = [p for p in kmp if p.get("importance") == "高"]
            if high_importance:
                reqs["needs_climax"] = True
            # 补充时间戳
            if not reqs["key_timestamps"]:
                reqs["key_timestamps"] = [p.get("video_timestamp", 0) for p in kmp[:5]]

        # 8维闭环新增字段
        reqs["color_mood"] = video_analysis.get("color_mood", {})
        reqs["alignment_strategy"] = video_analysis.get("alignment_strategy", "ambient_only")
        reqs["video_imagination"] = video_analysis.get("video_imagination", "")
        reqs["video_genre"] = video_analysis.get("video_genre", "")
        reqs["rhythm_pattern"] = video_analysis.get("rhythm_pattern", {})
        reqs["scene_analysis"] = video_analysis.get("scene_analysis", {})

        return reqs

    def _score_track(self, track: dict, reqs: dict) -> Tuple[float, List[str]]:
        """
        对单首 BGM 进行多维度打分。

        Returns:
            (总分, 理由列表)
        """
        scores = {}
        reasons = []

        # 1. BPM 匹配 (权重 0.25)
        bpm_score, bpm_reason = self._score_bpm(track, reqs)
        scores["bpm"] = bpm_score
        if bpm_reason:
            reasons.append(bpm_reason)

        # 2. 能量匹配 (权重 0.20)
        energy_score, energy_reason = self._score_energy(track, reqs)
        scores["energy"] = energy_score
        if energy_reason:
            reasons.append(energy_reason)

        # 3. 风格匹配 (权重 0.20)
        style_score, style_reason = self._score_style(track, reqs)
        scores["style"] = style_score
        if style_reason:
            reasons.append(style_reason)

        # 4. 情绪匹配 (权重 0.15)
        emotion_score, emotion_reason = self._score_emotion(track, reqs)
        scores["emotion"] = emotion_score
        if emotion_reason:
            reasons.append(emotion_reason)

        # 5. 高潮段匹配 (权重 0.10)
        climax_score, climax_reason = self._score_climax(track, reqs)
        scores["climax"] = climax_score
        if climax_reason:
            reasons.append(climax_reason)

        # 6. 人声兼容 (权重 0.05)
        vocal_score, vocal_reason = self._score_vocal(track, reqs)
        scores["vocal"] = vocal_score
        if vocal_reason:
            reasons.append(vocal_reason)

        # 7. 能量动态匹配 (权重 0.07)
        dynamics_score, dynamics_reason = self._score_dynamics(track, reqs)
        scores["dynamics"] = dynamics_score
        if dynamics_reason:
            reasons.append(dynamics_reason)

        # 8. 转场对齐匹配 (权重 0.10) [8维新增]
        transition_score, transition_reason = self._score_transition_alignment(track, reqs)
        scores["transition"] = transition_score
        if transition_reason:
            reasons.append(transition_reason)

        # 9. 色调情绪匹配 (权重 0.10) [8维新增]
        color_score, color_reason = self._score_color_mood(track, reqs)
        scores["color"] = color_score
        if color_reason:
            reasons.append(color_reason)

        # 10. 前向需求匹配 (权重 0.10) [Stage 2 代码筛选，非真正双向]
        forward_score, forward_reason = self._score_forward_match(track, reqs)
        scores["forward_match"] = forward_score
        if forward_reason:
            reasons.append(forward_reason)

        # 11. 剪辑节奏匹配 (权重 0.08) [新增]
        rhythm_score, rhythm_reason = self._score_rhythm_pattern(track, reqs)
        scores["rhythm"] = rhythm_score
        if rhythm_reason:
            reasons.append(rhythm_reason)

        # 12. 音色匹配 (权重 0.05) [新增]
        timbre_score, timbre_reason = self._score_timbre(track, reqs)
        scores["timbre"] = timbre_score
        if timbre_reason:
            reasons.append(timbre_reason)

        # 13. 文化语境匹配 (权重 0.05) [新增]
        cultural_score, cultural_reason = self._score_cultural_context(track, reqs)
        scores["cultural"] = cultural_score
        if cultural_reason:
            reasons.append(cultural_reason)

        # 14. 约束满足度 (权重 0.08) [新增]
        constraint_score, constraint_reason = self._score_constraints(track, reqs)
        scores["constraints"] = constraint_score
        if constraint_reason:
            reasons.append(constraint_reason)

        # 加权总分（14维）
        weights = {
            "bpm": 0.05,
            "energy": 0.08,
            "style": 0.11,
            "emotion": 0.18,
            "climax": 0.06,
            "vocal": 0.05,
            "dynamics": 0.05,
            "transition": 0.08,
            "color": 0.07,
            "forward_match": 0.10,
            "rhythm": 0.03,
            "timbre": 0.05,
            "cultural": 0.04,
            "constraints": 0.05,
        }
        total = sum(scores[k] * weights[k] for k in weights)

        return total, reasons

    def _score_bpm(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """BPM 匹配：精确匹配在范围内得满分，越偏离越低"""
        rt = track.get("rhythm_tag", {})
        bpm = rt.get("bpm", 0)
        if bpm <= 0:
            return 0.5, ""

        bpm_min, bpm_max = reqs["bpm_min"], reqs["bpm_max"]
        bpm_center = (bpm_min + bpm_max) / 2
        bpm_range_half = max((bpm_max - bpm_min) / 2, 10)

        if bpm_min <= bpm <= bpm_max:
            return 1.0, f"BPM {bpm} 在范围内"
        else:
            # 范围外按距离衰减
            dist = min(abs(bpm - bpm_min), abs(bpm - bpm_max))
            penalty = dist / bpm_range_half
            score = max(0, 1.0 - penalty * 0.5)
            return score, f"BPM {bpm} 偏离范围{bpm_min}-{bpm_max}"

    def _score_energy(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """能量匹配：track energy 落在视频 energy_range 内得满分。
        额外检查 energy_baseline（BGM能量下限）和 energy_peak（BGM能量上限）"""
        rt = track.get("rhythm_tag", {})
        energy = rt.get("energy", 0.5)

        e_min, e_max = reqs["energy_min"], reqs["energy_max"]
        video_energy = reqs.get("energy_level", 0.5)

        # 基础分：整体能量是否在范围内
        if e_min <= energy <= e_max:
            base_score = 1.0
        else:
            if energy < e_min:
                dist = e_min - energy
            else:
                dist = energy - e_max
            base_score = max(0, 1.0 - dist * 2)

        # energy_baseline 检查：BGM能量下限 vs 视频能量
        # 如果 BGM 的 baseline 太高，平静视频会觉得吵
        es = track.get("energy_shape", {})
        baseline = es.get("energy_baseline", None) if isinstance(es, dict) else None
        peak = es.get("energy_peak", None) if isinstance(es, dict) else None

        bonus = 0
        reasons = []

        if baseline is not None and video_energy < 0.4:
            # 平静视频 + BGM baseline 高 → 扣分
            if baseline > 0.3:
                penalty = min(0.2, (baseline - 0.3) * 0.5)
                bonus -= penalty
                reasons.append(f"baseline={baseline:.2f}偏高")
            elif baseline < 0.15:
                bonus += 0.05
                reasons.append(f"baseline={baseline:.2f}适合平静视频")

        # energy_peak 检查：BGM能量上限 vs 视频最大张力
        tension_values = reqs.get("tension_values", [])
        if peak is not None and tension_values:
            max_tension = max(tension_values)
            # BGM peak 远高于视频最大张力 → 可能太猛
            if peak > max_tension + 0.3:
                penalty = min(0.15, (peak - max_tension - 0.3) * 0.5)
                bonus -= penalty
                reasons.append(f"peak={peak:.2f}超过视频张力{max_tension:.2f}")

        score = max(0.1, min(1.0, base_score + bonus))
        reason = "; ".join(reasons) if reasons else (f"能量 {energy:.2f} 偏离范围" if base_score < 0.8 else "")
        return score, reason

    def _score_style(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """风格匹配：video recommended_styles vs track style_tags"""
        rec_styles = reqs.get("recommended_styles", [])
        if not rec_styles:
            return 0.6, ""  # 无推荐风格时给中等分

        style_tags = track.get("style_tags", [])
        instrumentation = track.get("instrumentation", [])
        all_track_styles = set(style_tags)

        # 检查直接匹配
        matched = []
        for rs in rec_styles:
            rs_upper = rs.upper()
            # 直接匹配
            if any(ts.upper() == rs_upper for ts in all_track_styles):
                matched.append(rs)
                continue
            # 关键词映射匹配
            keywords = STYLE_KEYWORDS.get(rs, set())
            if any(ts in keywords for ts in all_track_styles):
                matched.append(rs)
                continue
            # 子串匹配（中文风格名 vs 英文标签）
            if any(rs in ts or ts in rs for ts in all_track_styles):
                matched.append(rs)

        if matched:
            ratio = len(matched) / len(rec_styles)
            score = 0.5 + 0.5 * ratio

            # 幻觉防御：如果匹配到 Electronic/EDM 类，但乐器全是原声的，降分
            ACOUSTIC_INSTRUMENTS = {"吉他", "guitar", "钢琴", "piano", "指弹", "acoustic", "小提琴", "violin", "大提琴"}
            ELECTRONIC_STYLES = {"electronic", "edm", "synthpop", "house", "techno", "trance", "dubstep"}
            if any(ts.lower() in ELECTRONIC_STYLES for ts in all_track_styles):
                if instrumentation and all(any(ai in inst.lower() for ai in ACOUSTIC_INSTRUMENTS) for inst in instrumentation):
                    score *= 0.5
                    return score, f"风格标签疑似误判(电子但乐器全原声): {', '.join(matched[:3])}"

            return score, f"风格匹配: {', '.join(matched[:3])}"
        else:
            return 0.3, "风格不太匹配"

    def _score_emotion(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """情绪匹配：video primary_mood vs track emotion_tags"""
        mood = reqs.get("primary_mood", "")
        if not mood:
            return 0.5, ""

        emotion_tags = [t.lower() for t in track.get("emotion_tags", [])]
        if not emotion_tags:
            return 0.5, ""

        # 直接匹配：emotion_tags 与 primary_mood 的重叠
        mood_lower = mood.lower()
        matched = [t for t in emotion_tags if t in mood_lower or mood_lower in t]

        # 矛盾检测：平静/孤独情绪 vs 热血/激昂标签
        calm_moods = {"平静", "治愈", "温暖", "放松", "舒缓", "孤独", "寂寥", "忧郁", "安静", "低落"}
        intense_emotions = {"热血", "兴奋", "动感", "激昂", "摇滚", "炸裂", "爆发"}
        is_calm_mood = any(m in mood for m in calm_moods)
        is_intense_tag = any(t in intense_emotions for t in emotion_tags)

        if is_calm_mood and is_intense_tag:
            return 0.1, f"情绪矛盾: 视频{mood} vs BGM{emotion_tags}"

        if matched:
            ratio = len(matched) / max(len(emotion_tags), 1)
            score = 0.7 + 0.3 * ratio
            return min(1.0, score), f"情绪匹配: {matched[:3]}"

        # 部分匹配：mood关键词在emotion_tags中
        for tag in emotion_tags:
            if any(m in tag or tag in m for m in mood.split("/")):
                return 0.6, f"情绪部分匹配: {tag}"

        # 不匹配：严重惩罚
        return 0.15, f"情绪不匹配: 视频{mood} vs BGM{emotion_tags[:3]}"

    def _score_climax(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """高潮段匹配：有高潮段 vs 视频需要高潮"""
        climax_segs = track.get("climax_segments", [])
        needs_climax = reqs.get("needs_climax", False)
        n_transitions = reqs.get("n_transitions", 0)

        if needs_climax:
            if climax_segs:
                # 高潮段数量 vs 转场点数量
                n_climax = len(climax_segs)
                if n_climax >= n_transitions:
                    return 1.0, f"{n_climax}个高潮段覆盖{n_transitions}个转场"
                elif n_climax > 0:
                    return 0.7, f"{n_climax}个高潮段"
                else:
                    return 0.4, ""
            else:
                return 0.2, "视频需要高潮但歌曲缺少"
        else:
            # 视频不需要高潮，有太多高潮反而不好
            if climax_segs and len(climax_segs) > 3:
                return 0.5, "歌曲高潮偏多"
            return 0.7, ""

    def _score_vocal(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """人声兼容性"""
        rt = track.get("rhythm_tag", {})
        vocal_ratio = rt.get("vocal_ratio", 0)

        if not reqs["vocal_ok"]:
            if vocal_ratio <= 20:
                return 1.0, "纯音乐"
            elif vocal_ratio <= 50:
                return 0.5, f"人声占比{vocal_ratio}%偏高"
            else:
                return 0.2, f"人声占比{vocal_ratio}%过高"
        else:
            return 0.8, ""

    def _score_dynamics(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """能量动态匹配：视频张力曲线 vs BGM 能量曲线 + arc_type一致性检查"""
        tension_values = reqs.get("tension_values", [])
        if not tension_values or len(tension_values) < 2:
            # 即使没有张力曲线，也检查 arc_type 一致性
            return self._check_arc_consistency(track)

        energy_curve = track.get("energy_curve", [])
        if not energy_curve or len(energy_curve) < 2:
            return self._check_arc_consistency(track)

        try:
            video_arr = np.array(tension_values, dtype=float)
            bgm_arr = np.array(energy_curve, dtype=float)

            # 归一化
            v_min, v_max = video_arr.min(), video_arr.max()
            b_min, b_max = bgm_arr.min(), bgm_arr.max()
            if v_max > v_min:
                video_arr = (video_arr - v_min) / (v_max - v_min)
            if b_max > b_min:
                bgm_arr = (bgm_arr - b_min) / (b_max - b_min)

            # 重采样到相同长度
            target_len = min(len(video_arr), len(bgm_arr))
            if target_len < 2:
                return 0.5, ""

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
            if np.isnan(corr):
                return 0.5, ""

            if corr > 0.6:
                return 0.9, f"能量曲线高相关({corr:.2f})"
            elif corr > 0.3:
                return 0.7, ""
            elif corr > 0:
                return 0.5, ""
            else:
                return 0.3, f"能量曲线负相关({corr:.2f})"
        except Exception:
            return 0.5, ""

    def _check_arc_consistency(self, track: dict) -> Tuple[float, str]:
        """
        能量形状一致性检查（无张力曲线时的兜底）。
        只检查 energy_shape 是否合理。
        """
        shape = track.get("energy_shape", "")
        if not shape:
            return 0.5, ""

        # 有明确能量形状标注 → 给中等分
        return 0.6, f"能量形状: {shape}"

    # ============ 8维闭环新增维度 ============

    def _score_transition_alignment(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        D1: 转场对齐匹配 — BGM高潮段 + 节拍规律性 vs 视频转场点。

        full_beat_sync: 需要BGM高潮段覆盖转场点 + 高节拍规律性
        partial_alignment: 部分对齐即可
        ambient_only: 不需要精确对齐，给中性分

        beat_regularity:
        - full_beat_sync 时，规律性高 → 加分（适合卡点），低 → 扣分（不适合硬卡点）
        - ambient_only 时，规律性不影响
        """
        alignment = reqs.get("alignment_strategy", "ambient_only")
        n_transitions = reqs.get("n_transitions", 0)
        climax_segs = track.get("climax_segments", [])
        beat_regularity = track.get("rhythm_tag", {}).get("beat_regularity")

        if alignment == "full_beat_sync":
            if not climax_segs:
                return 0.2, "视频需精确对齐但歌曲无高潮段"
            # 高潮段数量应 ≥ 转场数
            coverage = min(len(climax_segs) / max(n_transitions, 1), 1.0)
            score = 0.3 + 0.7 * coverage

            # 节拍规律性修正：full_beat_sync 需要规律节拍
            if beat_regularity is not None:
                if beat_regularity > 0.85:
                    score = min(1.0, score + 0.1)
                    return score, f"转场对齐: {len(climax_segs)}个高潮+节拍极规律({beat_regularity:.2f})"
                elif beat_regularity < 0.6:
                    score = max(0.1, score - 0.15)
                    return score, f"转场对齐: {len(climax_segs)}个高潮但节拍自由({beat_regularity:.2f})"

            return score, f"转场对齐: {len(climax_segs)}个高潮覆盖{n_transitions}个转场"
        elif alignment == "partial_alignment":
            if climax_segs:
                return 0.7, "部分对齐，有高潮段可用"
            return 0.5, "部分对齐但无高潮段"
        else:
            # ambient_only: 不需要对齐，给中性偏高分
            return 0.6, ""

    def _score_color_mood(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        D4: 色调情绪匹配 — 视频色调 vs BGM调性。

        视频暖色调 → BGM大调更匹配
        视频暗色调 → BGM小调或低能量更匹配
        """
        color_mood = reqs.get("color_mood", {})
        if not color_mood:
            return 0.5, ""

        warm_ratio = color_mood.get("warm_ratio", 0.3)
        dark_ratio = color_mood.get("dark_ratio", 0.3)

        # BGM调性
        chroma = track.get("chroma_profile", {})
        key_mode = chroma.get("key_mode", "unknown")

        if key_mode == "unknown":
            return 0.5, ""

        score = 0.5
        if warm_ratio > 0.4 and key_mode == "major":
            score = 0.8
        elif dark_ratio > 0.4 and key_mode == "minor":
            score = 0.8
        elif warm_ratio > 0.4 and key_mode == "minor":
            score = 0.4
        elif dark_ratio > 0.4 and key_mode == "major":
            score = 0.4

        mood_desc = color_mood.get("mood_tendency", "")
        return score, f"色调{mood_desc}" if score != 0.5 else ""

    def _score_forward_match(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        D10: 前向需求匹配 — 视频需求 → BGM静态标签。

        Stage 2 代码筛选，检查BGM的scene_tags.fit/unfit是否匹配视频场景类型。
        注意：这不是双向验证。反向验证在 _build_recommendations 中完成。
        """
        scene_analysis = reqs.get("scene_analysis", {})
        video_scene = ""
        if isinstance(scene_analysis, dict):
            video_scene = scene_analysis.get("scene_type", "")

        # BGM适合/不适合的场景
        scene_tags = track.get("scene_tags", {})
        fit_scenes = []
        unfit_scenes = []
        if isinstance(scene_tags, dict):
            fit_scenes = [s.lower() for s in scene_tags.get("fit", [])]
            unfit_scenes = [s.lower() for s in scene_tags.get("unfit", [])]

        if not video_scene:
            return 0.5, ""

        video_scene_lower = video_scene.lower()

        # 优先检查 unfit — BGM 明确不适合的场景，直接扣分
        for unfit in unfit_scenes:
            if video_scene_lower in unfit or unfit in video_scene_lower:
                return 0.15, f"场景冲突: BGM不适合{video_scene}"

        if not fit_scenes:
            return 0.5, ""

        for fit in fit_scenes:
            if video_scene_lower in fit or fit in video_scene_lower:
                return 0.9, f"场景匹配: {video_scene}"

        # 部分匹配
        return 0.4, f"场景不太匹配: {video_scene}"

    def _score_rhythm_pattern(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        剪辑节奏匹配 — 视频剪辑模式 vs BGM结构。

        加速型/爆发型 → 需要有 build-up → climax 结构的 BGM
        匀速型 → 需要能量稳定的 BGM
        减速型 → 需要有渐弱/收尾结构的 BGM
        """
        rhythm_pattern = reqs.get("rhythm_pattern", {})
        if not rhythm_pattern:
            return 0.5, ""

        pattern = rhythm_pattern.get("pattern", "未知")
        if pattern == "未知":
            return 0.5, ""

        # BGM结构信息
        climax_segs = track.get("climax_segments", [])
        energy_curve = track.get("energy_curve", [])
        structural_sections = track.get("structural_sections", [])
        avg_energy = track.get("avg_energy", 0.5)

        # 加速型/爆发型：需要 build-up → climax
        if pattern in ("加速型", "爆发型"):
            if climax_segs:
                # 有高潮段 = 有 climax，加分
                # 如果高潮段在后半段（build-up在前），更匹配
                duration = track.get("duration", 60)
                late_climax = [c for c in climax_segs if c.get("start", 0) > duration * 0.4]
                if late_climax:
                    return 0.9, f"{pattern}: 有后段高潮build-up"
                return 0.7, f"{pattern}: 有高潮段"
            # 无高潮段但能量递增也算匹配
            if energy_curve and len(energy_curve) >= 3:
                first_half = sum(energy_curve[:len(energy_curve)//2]) / max(len(energy_curve)//2, 1)
                second_half = sum(energy_curve[len(energy_curve)//2:]) / max(len(energy_curve) - len(energy_curve)//2, 1)
                if second_half > first_half * 1.2:
                    return 0.7, f"{pattern}: 能量递增"
            return 0.3, f"{pattern}: 缺少build-up结构"

        # 匀速型：能量稳定
        if pattern == "匀速型":
            if energy_curve and len(energy_curve) >= 3:
                variance = np.var(energy_curve)
                if variance < 0.03:
                    return 0.9, "匀速: 能量稳定"
                elif variance < 0.08:
                    return 0.7, "匀速: 能量较稳定"
            # 无能量曲线时看 avg_energy 是否中等
            if 0.3 <= avg_energy <= 0.7:
                return 0.6, "匀速: 中等能量"
            return 0.5, ""

        # 减速型：需要收尾
        if pattern == "减速型":
            if energy_curve and len(energy_curve) >= 3:
                # 能量递减 = 有收尾
                first_half = sum(energy_curve[:len(energy_curve)//2]) / max(len(energy_curve)//2, 1)
                second_half = sum(energy_curve[len(energy_curve)//2:]) / max(len(energy_curve) - len(energy_curve)//2, 1)
                if second_half < first_half * 0.8:
                    return 0.8, "减速: 有能量收尾"
            return 0.5, ""

        return 0.5, ""

    def _score_timbre(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        音色匹配 — 视频情绪 vs BGM 音色质感。

        平静/温馨视频 → 偏好温暖(centroid<0.3)、干声(reverb<0.5)
        史诗/运动视频 → 偏好明亮(centroid>0.4)、层次分明(contrast>0.4)
        Vlog/日常 → 偏好纯净(bandwidth<0.3)、近场(reverb<0.4)
        """
        tp = track.get("timbre_profile")
        if not tp:
            return 0.5, ""

        centroid = tp.get("centroid_mean", 0.5)
        bandwidth = tp.get("bandwidth_mean", 0.5)
        contrast = tp.get("contrast_mean", 0.5)
        reverb = tp.get("reverb_estimate", 0.5)

        energy_level = reqs.get("energy_level", 0.5)

        # 平静型视频 (energy < 0.4)
        if energy_level < 0.4:
            score = 0.5
            if centroid < 0.3:
                score += 0.2  # 温暖音色
            if reverb < 0.5:
                score += 0.15  # 近场感
            if bandwidth < 0.3:
                score += 0.1  # 纯净
            score = min(1.0, score)
            if score > 0.6:
                return score, f"音色温暖适合平静视频"
            return score, ""

        # 激烈型视频 (energy > 0.6)
        if energy_level > 0.6:
            score = 0.5
            if centroid > 0.4:
                score += 0.15  # 明亮
            if contrast > 0.4:
                score += 0.2  # 层次分明
            if reverb > 0.4:
                score += 0.1  # 空间感
            score = min(1.0, score)
            if score > 0.6:
                return score, f"音色明亮适合激烈视频"
            return score, ""

        # 中等能量视频
        return 0.5, ""

    def _score_cultural_context(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        文化语境匹配 — 视频类型/场景 vs BGM 文化联想。

        日本旅行视频 + "日系,和风" cultural_context = 高匹配
        极限运动视频 + "美式街头,Trap" = 高匹配
        """
        cultural = track.get("cultural_context", "")
        if not cultural:
            return 0.5, ""

        video_genre = reqs.get("video_genre", "")
        video_scene = reqs.get("scene_analysis", {})
        scene_type = video_scene.get("scene_type", "") if isinstance(video_scene, dict) else ""

        # 文化语境关键词 → 视频类型/场景的映射
        CULTURAL映射 = {
            # 东亚文化
            "日系": {"旅行", "日本", "动漫", "校园", "和风", "Vlog"},
            "日系摇滚": {"旅行", "日本", "动漫", "运动"},
            "和风": {"旅行", "日本", "古风"},
            "中国风": {"旅行", "中国", "古风", "国风"},
            "国风": {"旅行", "中国", "古风"},
            # 西方文化
            "美式街头": {"极限运动", "运动", "都市", "街舞"},
            "Trap": {"极限运动", "运动", "都市", "街舞"},
            "凯尔特": {"旅行", "田园", "自然", "风景"},
            "拉丁": {"旅行", "舞蹈", "派对", "美食"},
            "非洲": {"旅行", "自然", "动物"},
            # 情绪文化
            "热血": {"运动", "极限运动", "竞技", "旅行"},
            "治愈": {"风景", "美食", "Vlog", "日常"},
            "文艺": {"Vlog", "日常", "旅行", "美食"},
            "复古": {"Vlog", "日常", "怀旧"},
            "赛博朋克": {"都市", "夜景", "科技"},
            # 场景文化
            "史诗": {"旅行", "风景", "运动", "极限运动"},
            "电影感": {"旅行", "风景", "剧情", "广告"},
            "田园": {"旅行", "风景", "美食", "自然"},
            "都市": {"Vlog", "日常", "旅行", "美食"},
        }

        # 解析 cultural_context 为关键词列表
        cultural_keywords = [k.strip() for k in cultural.replace("，", ",").split(",")]

        # 收集视频侧所有关键词
        video_keywords = set()
        if video_genre:
            video_keywords.add(video_genre)
        if scene_type:
            video_keywords.add(scene_type)

        # 检查匹配
        matched = []
        for ck in cultural_keywords:
            # 直接匹配
            if ck in video_keywords:
                matched.append(ck)
                continue
            # 通过映射表匹配
            mapped_scenes = CULTURAL映射.get(ck, set())
            if mapped_scenes & video_keywords:
                matched.append(ck)

        if matched:
            ratio = len(matched) / len(cultural_keywords) if cultural_keywords else 0
            score = 0.5 + 0.45 * ratio  # 最高 0.95
            return score, f"文化匹配: {', '.join(matched[:3])}"

        # 无匹配但有文化标签 → 给中性分
        if cultural_keywords:
            return 0.45, ""

        return 0.5, ""

    def _score_constraints(self, track: dict, reqs: dict) -> Tuple[float, str]:
        """
        约束满足度 — 这首BGM"要求"什么才能生效。

        检查：
        1. min_video_energy vs 视频 energy_level（能量基线兼容性）
        2. requires_buildup vs 视频是否有蓄势段
        3. has_lyrics vs 视频是否有对话
        """
        constraints = track.get("constraints")
        if not constraints:
            return 0.5, ""

        video_energy = reqs.get("energy_level", 0.5)
        min_video_energy = constraints.get("min_video_energy", 0)
        requires_buildup = constraints.get("requires_buildup", False)
        has_lyrics = constraints.get("has_lyrics", False)

        # 幻觉防御：min_video_energy 应该 ≤ BGM 自身能量
        # 如果 MiMo 标的基线比 librosa 实测能量还高，说明标错了
        track_avg_energy = track.get("avg_energy", 0)
        if track_avg_energy > 0 and min_video_energy > track_avg_energy * 2:
            min_video_energy = round(track_avg_energy * 0.8, 3)

        score = 0.5
        reasons = []

        # 1. 能量基线兼容性（最关键）
        # BGM 要求的最低视频能量 vs 实际视频能量
        if min_video_energy > 0:
            # 如果视频能量 < BGM要求的最低能量 → BGM太吵，会抢戏
            if video_energy < min_video_energy:
                penalty = min(0.3, (min_video_energy - video_energy) * 2)
                score -= penalty
                reasons.append(f"BGM能量基线{min_video_energy:.2f} > 视频能量{video_energy:.2f}")
            else:
                # 视频能量 >= BGM要求 → 兼容
                bonus = min(0.2, (video_energy - min_video_energy) * 0.5)
                score += bonus

        # 2. 蓄势段需求
        if requires_buildup:
            # 检查视频是否有转场点（有转场 = 有结构变化 = 可能有蓄势段）
            n_transitions = reqs.get("n_transitions", 0)
            if n_transitions >= 2:
                score += 0.1  # 视频有结构，能满足蓄势需求
            else:
                score -= 0.1  # 视频太平，蓄势感出不来
                reasons.append("视频缺少蓄势段")

        # 3. 人声干扰
        if has_lyrics:
            vocal_ok = reqs.get("vocal_ok", True)
            if not vocal_ok:
                score -= 0.25  # 有歌词但视频不允许人声 → 严重扣分
                reasons.append("有歌词但视频不允许人声")
            else:
                score += 0.05  # 有歌词且视频允许 → 小加分

        score = max(0.1, min(1.0, score))
        reason = "; ".join(reasons) if reasons else ""
        return score, reason
