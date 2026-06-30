from fastapi import APIRouter, HTTPException
from models.schemas import VideoAnalysisResult
from services.keyframe_extractor import KeyFrameExtractor
from services.mimo_analyzer import MiMoAnalyzer
from services.cv_analyzer import CVAnalyzer
from config import UPLOAD_DIR
import uuid
import os
import asyncio
import math
from datetime import datetime


# ─── 关键词→类型映射（MiMo失败时的启发式降级）───
_ACTIVITY_GENRE = {
    "滑雪": "极限运动", "滑板": "极限运动", "冲浪": "极限运动", "攀岩": "极限运动",
    "跳伞": "极限运动", "蹦极": "极限运动", "骑行": "运动", "跑步": "运动",
    "游泳": "运动", "篮球": "运动", "足球": "运动", "健身": "运动",
    "做饭": "美食", "烘焙": "美食", "烹饪": "美食", "吃播": "美食",
    "旅行": "旅行", "旅游": "旅行", "自驾": "旅行", "露营": "旅行",
    "开箱": "评测", "评测": "评测", "测评": "评测", "数码": "评测",
    "婚礼": "剧情", "毕业": "剧情", "生日": "剧情",
}


def _heuristic_fallback(cv_data: dict, frames: list) -> dict:
    """
    MiMo 失败时的启发式降级：从 CV 客观数据推断基本语义。
    不调用任何 LLM，纯代码逻辑。
    """
    # 从 activity 关键词推断 genre
    activity = cv_data.get("activity", "") or ""
    genre = ""
    for kw, g in _ACTIVITY_GENRE.items():
        if kw in activity:
            genre = g
            break

    # 从 tension 推断 energy
    tension_curve = cv_data.get("tension_curve", [])
    if tension_curve:
        avg_tension = sum(t["tension"] for t in tension_curve) / len(tension_curve)
        max_tension = max(t["tension"] for t in tension_curve)
    else:
        avg_tension = 0.5
        max_tension = 0.5

    # 从 transitions 推断 alignment
    transitions = cv_data.get("transitions", [])
    n_trans = len(transitions)
    if avg_tension > 0.6 and n_trans >= 3:
        alignment = "full_beat_sync"
    elif avg_tension > 0.3 and n_trans >= 2:
        alignment = "partial_alignment"
    else:
        alignment = "ambient_only"

    # 推断 mood
    if avg_tension > 0.7:
        mood = "热血激昂"
    elif avg_tension > 0.5:
        mood = "紧张专注"
    elif avg_tension > 0.3:
        mood = "平静治愈"
    else:
        mood = "安静放松"

    # 推断 energy_level
    energy_level = min(1.0, avg_tension * 1.1)

    print(f"[启发式降级] genre={genre}, mood={mood}, energy={energy_level:.2f}, alignment={alignment}")

    return {
        "visual": {
            "scene": "未知", "objects": [], "people_count": "未知",
            "activity": activity or "未知", "color_tone": "中性",
            "lighting": "自然光", "visual_style": "写实",
        },
        "text": {
            "has_subtitles": False, "subtitle_text": "",
            "on_screen_text": [], "text_sentiment": "中性",
        },
        "semantic": {
            "video_description": f"(启发式推断) {activity}" if activity else "",
            "video_genre": genre,
            "overall_atmosphere": {
                "primary_mood": mood, "secondary_mood": "",
                "description": f"(启发式推断) 平均张力{avg_tension:.2f}",
            },
            "music_imagination": {
                "recommended_styles": [],
                "recommended_characteristics": {"energy_range": [energy_level * 0.7, energy_level]},
                "reference_description": "",
            },
            "key_matching_points": [],
            "video_imagination": "",
            "ideal_bgm_profile": "",
            "narrative_arc": {
                "arc_type": "渐强型" if avg_tension > 0.5 else "平稳型",
                "climax_position": 0.7, "opening_mood": "平静", "closing_mood": mood,
            },
            "scene_analysis": {
                "scene_type": genre or "未知", "scene_description": "",
                "mood": mood, "visual_energy": energy_level,
            },
            "alignment_strategy": alignment,
        },
        "_heuristic_fallback": True,
    }


def normalize_text(raw: dict) -> dict:
    """标准化MiMo返回的text数据到TextResult schema"""

    def _to_bool(val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "yes", "是", "有")
        return bool(val)

    return {
        "has_subtitles": _to_bool(raw.get("has_subtitles", False)),
        "subtitle_content": raw.get("subtitle_text", raw.get("subtitle_content", "")),
        "on_screen_text": raw.get("on_screen_text", []),
        "text_sentiment": raw.get("text_sentiment", "中性"),
    }


def normalize_semantic(raw: dict) -> dict:
    """标准化MiMo返回的video_analysis/semantic数据到SemanticResult schema"""
    result = {
        "narrative_position": raw.get("narrative_position", "发展"),
        "emotion": raw.get("emotion", "平静"),
        "emotion_curve": [raw.get("emotion", "平静")],
        "theme": raw.get("theme", "未知"),
        "purpose": raw.get("purpose", "未知"),
        "emotion_intensity": raw.get("emotion_intensity", 0.5),
    }

    # 音乐想象描述（字符串，兼容旧格式）
    music_imag = raw.get("music_imagination", "")
    if isinstance(music_imag, str):
        result["music_imagination"] = music_imag
    elif isinstance(music_imag, dict):
        # 新格式：嵌套对象，取 reference_description 作为字符串
        result["music_imagination"] = music_imag.get("reference_description", "")
        result["music_imagination_obj"] = music_imag

    # 视频叙事描述
    if "video_description" in raw:
        result["video_description"] = raw["video_description"]

    # 三阶段闭环新字段
    if "video_structure" in raw and isinstance(raw["video_structure"], dict):
        result["video_structure"] = raw["video_structure"]
    if "overall_atmosphere" in raw and isinstance(raw["overall_atmosphere"], dict):
        result["overall_atmosphere"] = raw["overall_atmosphere"]
    if "key_matching_points" in raw and isinstance(raw["key_matching_points"], list):
        result["key_matching_points"] = raw["key_matching_points"]
    # CV 管线数据
    if "color_mood" in raw and isinstance(raw["color_mood"], dict):
        result["color_mood"] = raw["color_mood"]

    # CV+AI 语义分析新字段
    if "scene_descriptions" in raw and isinstance(raw["scene_descriptions"], list):
        result["scene_descriptions"] = raw["scene_descriptions"]
    if "emotion_journey" in raw:
        result["emotion_journey"] = raw["emotion_journey"]

    # 8维闭环新字段
    if "alignment_strategy" in raw:
        result["alignment_strategy"] = raw["alignment_strategy"]
    if "video_imagination" in raw:
        result["video_imagination"] = raw["video_imagination"]
    if "ideal_bgm_profile" in raw:
        result["ideal_bgm_profile"] = raw["ideal_bgm_profile"]
    if "camera_motion_type" in raw:
        result["camera_motion_type"] = raw["camera_motion_type"]
    if "video_genre" in raw:
        result["video_genre"] = raw["video_genre"]
    if "rhythm_pattern" in raw and isinstance(raw["rhythm_pattern"], dict):
        result["rhythm_pattern"] = raw["rhythm_pattern"]
    if "narrative_arc" in raw and isinstance(raw["narrative_arc"], dict):
        result["narrative_arc"] = raw["narrative_arc"]

    # 结构化需求
    for key in ["bpm_range", "vocal_ok", "culture_preference", "avoid", "reference_tracks"]:
        if key in raw:
            result[key] = raw[key]

    # emotion_scores → target_emotion
    emotion_data = raw.get("target_emotion") or raw.get("emotion_scores")
    if emotion_data and isinstance(emotion_data, dict):
        result["emotion_scores"] = emotion_data
        scores = emotion_data
        if scores:
            emotion_labels = ["平静", "愉快", "兴奋", "悲伤", "紧张", "激昂", "温馨", "搞笑"]
            score_keys = ["calm", "joy", "tension", "sadness", "tension", "epic", "romantic", "mysterious"]
            best_idx = max(range(len(score_keys)), key=lambda i: scores.get(score_keys[i], 0))
            result["emotion"] = emotion_labels[best_idx] if best_idx < len(emotion_labels) else result["emotion"]

    # 场景分析
    if "scene_analysis" in raw and isinstance(raw["scene_analysis"], dict):
        result["scene_analysis"] = raw["scene_analysis"]

    # BGM 建议（兼容旧格式）
    if "bgm_suggestion" in raw and isinstance(raw["bgm_suggestion"], dict):
        bgm_sug = raw["bgm_suggestion"].copy()
        if "rhythm_suggestion" in bgm_sug and isinstance(bgm_sug["rhythm_suggestion"], dict):
            if "rhythm_suggestion" not in result:
                result["rhythm_suggestion"] = bgm_sug.pop("rhythm_suggestion")
            else:
                bgm_sug.pop("rhythm_suggestion")
        result["bgm_suggestion"] = bgm_sug

    # 节奏建议
    if "rhythm_suggestion" in raw and isinstance(raw["rhythm_suggestion"], dict):
        result["rhythm_suggestion"] = raw["rhythm_suggestion"]

    return result


def normalize_audio(raw: dict) -> dict:
    """标准化MiMo返回的audio数据到AudioResult schema"""

    def _to_bool(val) -> bool:
        """将MiMo返回的非布尔值强制转换为布尔值"""
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "yes", "是", "有", "有音乐", "有说话")
        return bool(val)

    segments = raw.get("speech_segments", [])
    normalized_segments = []
    for seg in segments:
        if isinstance(seg, list) and len(seg) == 2:
            normalized_segments.append(seg)
    return {
        "has_speech": _to_bool(raw.get("has_speech", False)),
        "speech_segments": normalized_segments,
        "ambient_noise_level": raw.get("ambient_noise_level", "中等"),
        "music_playing": _to_bool(raw.get("music_playing", False)),
        "emotional_tone": raw.get("emotional_tone", "平静"),
        "audio_events": raw.get("audio_events", []),
    }


# ============ 叙事弧线驱动的情绪曲线 ============

# 情绪标签 → 数值映射（用于曲线生成）
EMOTION_TO_VALUE = {
    "平静": 0.2, "舒缓": 0.25, "温馨": 0.35, "愉快": 0.4,
    "轻快": 0.45, "动感": 0.55, "紧张": 0.6, "热血": 0.75,
    "激昂": 0.8, "兴奋": 0.85, "爆发": 0.95, "悲伤": 0.15,
    "低落": 0.1, "期待": 0.5, "震撼": 0.9,
}
# 数值 → 情绪标签（反向映射）
VALUE_TO_EMOTION = [
    (0.9, "爆发"), (0.75, "热血"), (0.6, "紧张"), (0.5, "动感"),
    (0.4, "愉快"), (0.3, "温馨"), (0.2, "平静"), (0.0, "低落"),
]


def _value_to_emotion(val: float) -> str:
    """数值映射回情绪标签"""
    for threshold, label in VALUE_TO_EMOTION:
        if val >= threshold:
            return label
    return "平静"


def _build_narrative_emotion_curve(
    narrative_arc: dict, tension_curve: list, duration: float
) -> dict:
    """
    用叙事弧线约束情绪曲线形状，不再逐帧独立查表。

    narrative_arc: {arc_type, climax_position, opening_mood, closing_mood}
    tension_curve: CV张力数据，用于调制曲线细节
    duration: 视频时长

    Returns: EmotionCurve dict {time_points, emotions, intensity}
    """
    arc_type = narrative_arc.get("arc_type", "平稳型") if narrative_arc else "平稳型"
    climax_pos = narrative_arc.get("climax_position", 0.5) if narrative_arc else 0.5
    opening_mood = (narrative_arc or {}).get("opening_mood", "平静")
    closing_mood = (narrative_arc or {}).get("closing_mood", "平静")

    # 采样点数（每5秒一个点）
    if duration <= 0:
        duration = 30.0
    n_points = max(4, min(20, int(duration / 5) + 1))
    positions = [i / (n_points - 1) for i in range(n_points)]  # 0.0 ~ 1.0

    # 开头/结尾的数值锚点
    open_val = EMOTION_TO_VALUE.get(opening_mood, 0.3)
    close_val = EMOTION_TO_VALUE.get(closing_mood, 0.3)

    # 根据 arc_type 生成基础曲线（归一化到 [0, 1]）
    base_curve = []
    for pos in positions:
        if arc_type == "渐强型":
            # 从 open 到 climax 递增，climax 后略降
            if pos <= climax_pos:
                val = open_val + (1.0 - open_val) * (pos / max(climax_pos, 0.01))
            else:
                # 高潮后回落到 close_val
                decay = (pos - climax_pos) / (1.0 - climax_pos + 0.01)
                val = 1.0 - (1.0 - close_val) * decay
            base_curve.append(val)

        elif arc_type == "爆发型":
            # 前面平稳，climax 处突然跳高
            if pos < climax_pos * 0.8:
                val = open_val + (close_val - open_val) * 0.2
            elif pos < climax_pos:
                # build-up
                progress = (pos - climax_pos * 0.8) / (climax_pos * 0.2 + 0.01)
                val = open_val + 0.2 + 0.6 * progress
            elif pos < climax_pos + 0.05:
                # climax spike
                val = 0.95
            else:
                # 回落
                decay = (pos - climax_pos) / (1.0 - climax_pos + 0.01)
                val = 0.95 - (0.95 - close_val) * min(decay * 1.5, 1.0)
            base_curve.append(val)

        elif arc_type == "先抑后扬型":
            # 先下降到低谷，再上升
            dip_pos = climax_pos * 0.4  # 低谷在 climax 的 40% 位置
            if pos <= dip_pos:
                # 下降段
                val = open_val - (open_val - 0.1) * (pos / max(dip_pos, 0.01))
            elif pos <= climax_pos:
                # 上升段
                progress = (pos - dip_pos) / (climax_pos - dip_pos + 0.01)
                val = 0.1 + (1.0 - 0.1) * progress
            else:
                # 高潮后回落
                decay = (pos - climax_pos) / (1.0 - climax_pos + 0.01)
                val = 1.0 - (1.0 - close_val) * decay
            base_curve.append(val)

        elif arc_type == "波动型":
            # 多次起伏，用正弦波叠加
            wave1 = 0.3 * math.sin(2 * math.pi * 1.5 * pos)
            wave2 = 0.15 * math.sin(2 * math.pi * 3.0 * pos + 0.5)
            mid = (open_val + close_val) / 2
            val = mid + wave1 + wave2
            base_curve.append(max(0.05, min(0.95, val)))

        else:
            # 平稳型：波动不超过 ±0.15
            mid = (open_val + close_val) / 2
            wave = 0.1 * math.sin(2 * math.pi * pos)
            val = mid + wave
            base_curve.append(max(0.05, min(0.95, val)))

    # 用 CV 张力曲线调制细节（±10% 微调）
    if tension_curve and len(tension_curve) >= 2:
        cv_times = [p.get("timestamp", 0) for p in tension_curve]
        cv_tensions = [p.get("tension", 0.5) for p in tension_curve]
        for i, pos in enumerate(positions):
            t_sec = pos * duration
            # 找最近的 CV 张力值
            closest_idx = min(range(len(cv_times)), key=lambda j: abs(cv_times[j] - t_sec))
            cv_t = cv_tensions[closest_idx]
            # CV张力高 → 微调向上，低 → 微调向下
            delta = (cv_t - 0.5) * 0.1
            base_curve[i] = max(0.0, min(1.0, base_curve[i] + delta))

    # 生成 time_points
    time_points = [round(pos * duration, 1) for pos in positions]

    # 生成 emotions（标签）
    emotions = [_value_to_emotion(v) for v in base_curve]

    # intensity 跟随曲线形状
    intensity = [round(max(0.1, min(1.0, v)), 3) for v in base_curve]

    return {
        "time_points": time_points,
        "emotions": emotions,
        "intensity": intensity,
    }


router = APIRouter()

# 内存存储分析任务（生产环境应使用数据库）
analysis_tasks = {}


@router.post("/api/analyze")
async def analyze_video(request: dict):
    """
    启动视频分析
    请求体: {"video_id": "xxx", "file_path": "path/to/video.mp4"}
    返回：analysis_id, status
    """
    video_id = request.get("video_id")
    video_path = request.get("file_path")

    if not video_id or not video_path:
        raise HTTPException(status_code=400, detail="缺少 video_id 或 file_path")

    # C3: 防止路径遍历攻击
    real_upload_dir = os.path.realpath(UPLOAD_DIR)
    real_video_path = os.path.realpath(video_path)
    if not real_video_path.startswith(real_upload_dir + os.sep) and real_video_path != real_upload_dir:
        raise HTTPException(status_code=403, detail="文件路径不在允许的上传目录中")

    analysis_id = str(uuid.uuid4())

    # I6: 防止任务存储无限增长
    if len(analysis_tasks) > 100:
        oldest = min(analysis_tasks, key=lambda k: analysis_tasks[k]['created_at'])
        del analysis_tasks[oldest]

    # 创建分析任务
    task = {
        "analysis_id": analysis_id,
        "video_id": video_id,
        "status": "analyzing",
        "progress": 0.0,
        "result": None,
        "error": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    analysis_tasks[analysis_id] = task

    # 执行分析（CV + AI 两阶段）
    frame_paths = []
    try:
        loop = asyncio.get_event_loop()

        # 1. 并行：CV 管线 + 关键帧提取
        extractor = KeyFrameExtractor()
        cv_analyzer = CVAnalyzer()

        frames_coro = loop.run_in_executor(None, extractor.extract, video_path)
        cv_coro = loop.run_in_executor(None, cv_analyzer.analyze, video_path)
        frames, cv_data = await asyncio.gather(frames_coro, cv_coro)

        frame_paths = frames
        task["progress"] = 0.3
        print(f"[分析] CV 完成: {len(cv_data.get('transitions', []))} 转场, "
              f"{len(cv_data.get('tension_curve', []))} 张力点")

        # 2. MiMo 五维分析（传入 CV 数据作为上下文）
        analyzer = MiMoAnalyzer()
        analysis_result = await analyzer.analyze_video(frames, cv_data=cv_data)
        task["progress"] = 0.8

        # 检查 MiMo 失败维度
        failed_dims = analysis_result.pop("_failed_dimensions", [])
        critical_failed = [d for d in failed_dims if d in ("video_analysis", "visual")]
        if critical_failed:
            print(f"[分析] 关键维度失败: {critical_failed}，结果可能不准确")

        # 检查 MiMo 是否返回了默认/空结果 → 启发式降级
        semantic_check = analysis_result.get("semantic", {})
        genre_empty = not semantic_check.get("video_genre")
        mood_unknown = semantic_check.get("overall_atmosphere", {}).get("primary_mood", "") in ("", "未知")
        if genre_empty and mood_unknown:
            print(f"[分析] MiMo 返回默认结果，启用启发式降级")
            analysis_result = _heuristic_fallback(cv_data, frames)

        # 3. 合并 CV 数据到语义分析结果
        # CV 转场点比 MiMo 更精确，用 CV 数据覆盖
        semantic_raw = analysis_result["semantic"]
        if cv_data.get("transitions"):
            # 确保 video_structure 存在
            if "video_structure" not in semantic_raw or not isinstance(semantic_raw["video_structure"], dict):
                semantic_raw["video_structure"] = {}
            semantic_raw["video_structure"]["transition_points"] = cv_data["transitions"]
            semantic_raw["video_structure"]["duration"] = cv_data.get("duration", 0)

        if cv_data.get("tension_curve"):
            if "video_structure" not in semantic_raw or not isinstance(semantic_raw["video_structure"], dict):
                semantic_raw["video_structure"] = {}
            semantic_raw["video_structure"]["tension_curve"] = cv_data["tension_curve"]

        if cv_data.get("color_mood"):
            semantic_raw["color_mood"] = cv_data["color_mood"]

        if cv_data.get("alignment_strategy"):
            semantic_raw["alignment_strategy"] = cv_data["alignment_strategy"]

        if cv_data.get("camera_motion_type"):
            semantic_raw["camera_motion_type"] = cv_data["camera_motion_type"]

        if cv_data.get("rhythm_pattern"):
            semantic_raw["rhythm_pattern"] = cv_data["rhythm_pattern"]

        # 4. 标准化并构建结果
        # 用 narrative_arc 约束情绪曲线形状
        narrative_arc = semantic_raw.get("narrative_arc", {})
        duration = cv_data.get("duration", 0) if cv_data else 0
        tension_curve = []
        if cv_data and cv_data.get("tension_curve"):
            tension_curve = cv_data["tension_curve"]
        emotion_curve = _build_narrative_emotion_curve(
            narrative_arc, tension_curve, duration
        )
        # 音频分析：完全用 CV 客观数据，不再让 MiMo 看图猜
        audio_data = cv_data.get("video_audio") or {}
        audio_result = {
            "has_speech": audio_data.get("has_speech", False),
            "speech_segments": audio_data.get("speech_segments", []),
            "ambient_noise_level": audio_data.get("ambient_noise_level", "中等"),
            "music_playing": audio_data.get("music_playing", False),
            "emotional_tone": "平静",
            "audio_events": [],
        }

        # 时序分析：完全用 CV 客观数据，不再让 MiMo 看图猜
        transitions = cv_data.get("transitions", [])
        tension_curve = cv_data.get("tension_curve", [])
        rhythm_pattern = cv_data.get("rhythm_pattern", {})
        keyframe_ts = cv_data.get("keyframe_timestamps", [])

        # editing_rhythm: 从 rhythm_pattern 推导
        rp = rhythm_pattern.get("pattern", "") if rhythm_pattern else ""
        rhythm_map = {"加速型": "快", "爆发型": "快", "匀速型": "中等", "减速型": "慢"}
        editing_rhythm = rhythm_map.get(rp, "中等")

        # narrative_pace: 从 tension_curve 推导
        if tension_curve:
            tensions = [t.get("tension", 0.5) for t in tension_curve]
            avg_t = sum(tensions) / len(tensions)
            variance = sum((t - avg_t) ** 2 for t in tensions) / len(tensions)
            narrative_pace = "紧凑" if avg_t > 0.55 or variance > 0.04 else "平缓"
        else:
            narrative_pace = "平缓"

        # key_moment_score: 从 tension_curve 最高点推导
        if tension_curve:
            max_tension = max(t.get("tension", 0.5) for t in tension_curve)
            key_moment_score = round(max_tension, 2)
        else:
            key_moment_score = 0.5

        # rhythm_curve: 直接用 tension_curve 的值
        rhythm_curve = [t.get("tension", 0.5) for t in tension_curve] if tension_curve else [0.5]

        temporal_result = {
            "scene_changes": len(transitions),
            "editing_rhythm": editing_rhythm,
            "key_moments": keyframe_ts[:5] if keyframe_ts else [],
            "narrative_pace": narrative_pace,
            "rhythm_curve": rhythm_curve,
        }

        result = VideoAnalysisResult(
            video_id=video_id,
            visual=analysis_result["visual"],
            audio=normalize_audio(audio_result),
            temporal=temporal_result,
            text=normalize_text(analysis_result["text"]),
            semantic=normalize_semantic(analysis_result["semantic"]),
            emotion_curve=emotion_curve,
            confidence=0.85 if not critical_failed else 0.3,
            created_at=datetime.now(),
            mimo_errors=failed_dims,
        )

        task["result"] = result
        task["status"] = "completed"
        task["progress"] = 1.0

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
    finally:
        # I4: 清理临时帧文件
        for frame_path in frame_paths:
            try:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            except OSError:
                pass

    task["updated_at"] = datetime.now()

    return {
        "analysis_id": analysis_id,
        "status": task["status"],
    }


@router.get("/api/status/{analysis_id}")
async def get_analysis_status(analysis_id: str):
    """
    查询分析状态和进度
    """
    task = analysis_tasks.get(analysis_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "analysis_id": task["analysis_id"],
        "status": task["status"],
        "progress": task["progress"],
        "result": task["result"],
        "error": task["error"],
    }
