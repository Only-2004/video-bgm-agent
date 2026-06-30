"""
分段推荐服务 — 将视频切成多段，每段独立匹配 BGM

输入: 视频分析结果（cv_data + semantic 分析）
输出: 每段推荐的 BGM + 理由
"""
from typing import Optional


def recommend_segments(video_analysis: dict, candidates: list,
                       max_segments: int = 3) -> list:
    """
    基于视频分析结果，将视频切成多段，每段推荐最匹配的 BGM。

    Args:
        video_analysis: 视频分析结果 dict（包含 cv_data, scene, emotion 等）
        candidates: 候选 BGM 列表（来自 search_bgm 的结果）
        max_segments: 最大分段数（默认 3）

    Returns:
        分段推荐列表:
        [
            {
                "segment_id": 1,
                "start_sec": 0.0,
                "end_sec": 12.5,
                "mood": "平静",
                "energy": 0.3,
                "scene_desc": "海边散步",
                "recommended_bgm": {...},
                "reason": "这段平静的开场适合...",
            },
            ...
        ]
    """
    cv_data = video_analysis.get("cv_data", {})
    emotion = video_analysis.get("emotion", {})
    scene = video_analysis.get("scene", {})

    # 1. 提取视频时长和转场点
    duration = _estimate_duration(video_analysis, cv_data)
    transitions = cv_data.get("transitions", [])
    tension_curve = cv_data.get("tension_curve", [])

    # 2. 切分段落
    segments = _split_segments(duration, transitions, tension_curve, max_segments)

    # 3. 为每段分析情绪和场景
    segments = _enrich_segments(segments, emotion, scene, tension_curve)

    # 4. 为每段匹配最佳 BGM
    segments = _match_segment_bgm(segments, candidates)

    return segments


def _estimate_duration(video_analysis: dict, cv_data: dict) -> float:
    """估算视频时长"""
    # 优先从 tension_curve 或 transitions 推算
    tension = cv_data.get("tension_curve", [])
    if tension:
        last_ts = max(p.get("timestamp", 0) for p in tension) if tension else 0
        if last_ts > 0:
            return last_ts

    transitions = cv_data.get("transitions", [])
    if transitions:
        last_ts = max(t.get("timestamp", 0) for t in transitions) if transitions else 0
        if last_ts > 0:
            return last_ts + 3  # 最后一段大约 3 秒

    return 30.0  # 默认 30 秒


def _split_segments(duration: float, transitions: list,
                    tension_curve: list, max_segments: int) -> list:
    """
    基于转场点和张力曲线将视频切成段落。
    策略：
    - 找转场点作为候选切分点
    - 选择张力变化最大的切分点（即情绪转折最明显的点）
    - 限制段落数不超过 max_segments
    """
    if duration <= 10 or max_segments <= 1:
        # 视频太短，不分段
        return [{"start_sec": 0, "end_sec": duration, "segment_id": 1}]

    # 收集所有候选切分点（来自转场）
    cut_candidates = []
    for t in transitions:
        ts = t.get("timestamp", 0)
        if 2 < ts < duration - 2:  # 不切开头和结尾
            cut_candidates.append(ts)

    # 从张力曲线找情绪变化点
    if len(tension_curve) >= 3:
        for i in range(1, len(tension_curve) - 1):
            ts = tension_curve[i].get("timestamp", 0)
            t_before = tension_curve[i - 1].get("tension", 0.5)
            t_after = tension_curve[i + 1].get("tension", 0.5)
            delta = abs(t_after - t_before)
            if delta > 0.15 and 2 < ts < duration - 2:
                cut_candidates.append(ts)

    # 去重 + 排序
    cut_candidates = sorted(set(round(c, 1) for c in cut_candidates))

    # 选择最均匀的切分点（避免段落太短或太长）
    if len(cut_candidates) > max_segments - 1:
        # 选间隔最均匀的
        cuts = _select_even_cuts(cut_candidates, duration, max_segments - 1)
    else:
        cuts = cut_candidates[:max_segments - 1]

    # 构建段落
    boundaries = [0] + cuts + [duration]
    segments = []
    for i in range(len(boundaries) - 1):
        segments.append({
            "segment_id": i + 1,
            "start_sec": round(boundaries[i], 1),
            "end_sec": round(boundaries[i + 1], 1),
        })

    return segments


def _select_even_cuts(candidates: list, duration: float, n: int) -> list:
    """从候选切分点中选择 n 个，使段落最均匀"""
    if len(candidates) <= n:
        return candidates

    ideal_step = duration / (n + 1)
    scored = []
    for c in candidates:
        # 计算离最近的理想切分点的距离
        nearest_ideal = round(c / ideal_step) * ideal_step
        scored.append((abs(c - nearest_ideal), c))
    scored.sort()
    return sorted(c for _, c in scored[:n])


def _enrich_segments(segments: list, emotion: dict, scene: dict,
                     tension_curve: list) -> list:
    """为每个段落添加情绪和场景信息"""
    overall_mood = emotion.get("mood", "")
    overall_energy = emotion.get("energy_level", 0.5)

    for seg in segments:
        start = seg["start_sec"]
        end = seg["end_sec"]

        # 从张力曲线计算该段平均能量
        seg_tensions = [
            p.get("tension", 0.5) for p in tension_curve
            if start <= p.get("timestamp", 0) <= end
        ]
        if seg_tensions:
            seg["energy"] = round(sum(seg_tensions) / len(seg_tensions), 2)
        else:
            seg["energy"] = overall_energy

        # 推断情绪
        seg["mood"] = _infer_mood(seg["energy"], overall_mood)
        seg["scene_desc"] = scene.get("description", "")

    return segments


def _infer_mood(energy: float, fallback: str = "") -> str:
    """基于能量值推断情绪"""
    if energy < 0.3:
        return "平静"
    elif energy < 0.5:
        return "温馨"
    elif energy < 0.7:
        return "欢快"
    elif energy < 0.85:
        return "热血"
    else:
        return "激烈"


def _match_segment_bgm(segments: list, candidates: list) -> list:
    """为每个段落匹配最合适的 BGM"""
    if not candidates:
        for seg in segments:
            seg["recommended_bgm"] = None
            seg["reason"] = "暂无匹配的 BGM"
        return segments

    used_ids = set()
    for seg in segments:
        energy = seg.get("energy", 0.5)
        mood = seg.get("mood", "")

        best = None
        best_score = -1

        for c in candidates:
            bgm_id = c.get("bgm_id", c.get("id", ""))
            if bgm_id in used_ids:
                continue

            track_energy = c.get("energy", c.get("avg_energy", 0.5))
            if isinstance(track_energy, (int, float)):
                energy_diff = abs(track_energy - energy)
                score = 1.0 - energy_diff
            else:
                score = 0.5

            # 情绪匹配加分
            tags = [str(t) for t in (c.get("emotion_tags", []) or [])]
            if mood and any(mood in t for t in tags):
                score += 0.3

            if score > best_score:
                best_score = score
                best = c

        if best:
            bgm_id = best.get("bgm_id", best.get("id", ""))
            used_ids.add(bgm_id)
            seg["recommended_bgm"] = {
                "bgm_id": bgm_id,
                "title": best.get("title", ""),
                "artist": best.get("artist", ""),
                "preview_url": best.get("preview_url", ""),
                "energy": best.get("energy", best.get("avg_energy", 0.5)),
            }
            seg["reason"] = _generate_reason(seg, best)
        else:
            seg["recommended_bgm"] = None
            seg["reason"] = "暂无匹配的 BGM"

    return segments


def _generate_reason(segment: dict, bgm: dict) -> str:
    """生成推荐理由"""
    mood = segment.get("mood", "")
    energy = segment.get("energy", 0.5)
    title = bgm.get("title", "")
    tags = [str(t) for t in (bgm.get("emotion_tags", []) or [])]

    parts = []
    if mood:
        parts.append(f"这段{mood}的氛围")
    if energy is not None:
        if energy < 0.3:
            parts.append("节奏舒缓")
        elif energy < 0.6:
            parts.append("节奏适中")
        else:
            parts.append("节奏有力")
    if title:
        parts.append(f"《{title}》的{'、'.join(tags[:2]) if tags else '风格'}与之匹配")

    return "，".join(parts) if parts else "风格匹配"
