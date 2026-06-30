"""
Agent 工具执行器 — 将现有服务包装为 FC 工具
"""
import asyncio
import json
import os
import sys
import traceback
from typing import Any
from config import LIBRARY_PATH, UPLOAD_DIR

# ──────────────────────────────────────────
# 动态导入（延迟加载，避免循环依赖）
# ──────────────────────────────────────────
_imported = {}


def _lazy_import(name: str):
    if name not in _imported:
        if name == "KeyFrameExtractor":
            from services.keyframe_extractor import KeyFrameExtractor
            _imported[name] = KeyFrameExtractor
        elif name == "CVAnalyzer":
            from services.cv_analyzer import CVAnalyzer
            _imported[name] = CVAnalyzer
        elif name == "MiMoAnalyzer":
            from services.mimo_analyzer import MiMoAnalyzer
            _imported[name] = MiMoAnalyzer
        elif name == "AudioFilter":
            from services.audio_filter import AudioFilter
            _imported[name] = AudioFilter
        elif name == "MiMoFineRanker":
            from services.mimo_fine_ranker import MiMoFineRanker
            _imported[name] = MiMoFineRanker
        elif name == "VolumeAdjuster":
            from services.volume_adjuster import VolumeAdjuster
            _imported[name] = VolumeAdjuster
        elif name == "ConflictDetector":
            from services.conflict_detector import ConflictDetector
            _imported[name] = ConflictDetector
        elif name == "BGMMatcher":
            from services.bgm_matcher import BGMMatcher
            _imported[name] = BGMMatcher
    return _imported[name]


# ──────────────────────────────────────────
# 共享内存状态（和 routers/analyze.py 共享）
# ──────────────────────────────────────────
analysis_tasks: dict = {}
"""analysis_id → { status, progress, result }"""


# ──────────────────────────────────────────
# 工具执行器
# ──────────────────────────────────────────
TOOL_EXECUTORS = {}


def _register(fn):
    TOOL_EXECUTORS[fn.__name__] = fn
    return fn


@_register
async def analyze_video(video_path: str, analysis_id: str = "") -> dict:
    """
    分析视频的画面内容、情绪、节奏等特征。

    内部流程：
    1. 提取关键帧 → 2. CV 分析 → 3. MiMo 语义分析 → 4. 合并结果
    """
    try:
        # 验证路径
        if not os.path.isfile(video_path):
            # 尝试拼接 UPLOAD_DIR
            full_path = os.path.join(UPLOAD_DIR, os.path.basename(video_path))
            if os.path.isfile(full_path):
                video_path = full_path
            else:
                return {"error": f"视频文件不存在: {video_path}"}

        # 1. 提取关键帧（同步 → executor）
        KeyFrameExtractor_cls = _lazy_import("KeyFrameExtractor")
        extractor = KeyFrameExtractor_cls()
        loop = asyncio.get_event_loop()
        frames = await loop.run_in_executor(None, extractor.extract, video_path)
        if not frames:
            frames = []

        # 2. CV 分析（同步 → executor）
        CVAnalyzer_cls = _lazy_import("CVAnalyzer")
        cv = CVAnalyzer_cls()
        cv_data = await loop.run_in_executor(None, cv.analyze, video_path)

        # 3. MiMo 语义分析（原生异步）
        MiMoAnalyzer = _lazy_import("MiMoAnalyzer")
        analyzer = MiMoAnalyzer()
        analysis = await analyzer.analyze_video(frames, cv_data=cv_data)

        result = {
            "video_path": video_path,
            "scene": {
                "description": analysis.get("visual", {}).get("scene", ""),
                "objects": analysis.get("visual", {}).get("objects", []),
                "activity": analysis.get("visual", {}).get("activity", ""),
                "color_tone": analysis.get("visual", {}).get("color_tone", ""),
                "lighting": analysis.get("visual", {}).get("lighting", ""),
            },
            "emotion": {
                "mood": analysis.get("semantic", {}).get("overall_atmosphere", ""),
                "energy_level": float(cv_data.get("energy_level", 0.5) if cv_data else 0.5),
                "narrative_arc": analysis.get("semantic", {}).get("narrative_arc", ""),
            },
            "audio": {
                "has_speech": bool(cv_data.get("has_speech", False) if cv_data else False),
            },
            "cv_data": {
                "tension_curve": (cv_data or {}).get("tension_curve", []),
                "transitions": (cv_data or {}).get("transitions", []),
                "bpm": (cv_data or {}).get("bpm", 0),
                "rhythm_pattern": (cv_data or {}).get("rhythm_pattern", ""),
            },
            "raw_analysis": analysis,
            "raw_cv": cv_data,
        }

        # 保存到共享状态
        if analysis_id:
            analysis_tasks[analysis_id] = result

        return result

    except Exception as e:
        return {
            "error": f"视频分析失败: {str(e)}",
            "traceback": traceback.format_exc(),
        }


@_register
async def search_bgm(mood: str = "", energy_range: str = "", genre: str = "", limit: int = 10) -> dict:
    """
    从 BGM 曲库搜索符合条件的配乐。
    """
    try:
        if not os.path.isfile(LIBRARY_PATH):
            return {"error": f"曲库文件不存在: {LIBRARY_PATH}", "candidates": []}

        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            library = json.load(f)

        tracks = library if isinstance(library, list) else library.get("bgm_list", library.get("tracks", []))

        # 解析能量范围
        energy_low, energy_high = 0.0, 1.0
        if energy_range:
            try:
                parts = energy_range.split("-")
                energy_low = float(parts[0])
                energy_high = float(parts[1])
            except (ValueError, IndexError):
                pass

        scored = []
        for t in tracks:
            score = 0.0
            reasons = []

            # 情绪匹配（scene_tags可能是dict或list）
            emotion_tags = t.get("emotion_tags", []) or []
            scene_tags_raw = t.get("scene_tags", []) or []
            if isinstance(scene_tags_raw, dict):
                scene_tags_flat = []
                for v in scene_tags_raw.values():
                    if isinstance(v, list):
                        scene_tags_flat.extend(v)
                scene_tags_raw = scene_tags_flat
            all_tags = [str(s) for s in emotion_tags + scene_tags_raw]
            if mood and any(mood in tag for tag in all_tags):
                score += 0.4
                reasons.append(f"情绪匹配: {mood}")

            # 能量匹配
            energy = t.get("avg_energy", t.get("energy", 0.5))
            if isinstance(energy, (int, float)):
                if energy_low <= energy <= energy_high:
                    score += 0.3
                    reasons.append(f"能量匹配: {energy:.2f} [{energy_low}-{energy_high}]")
                elif abs(energy - (energy_low + energy_high) / 2) < 0.2:
                    score += 0.1
                    reasons.append(f"能量接近: {energy:.2f}")

            # 风格匹配
            bgm_genre = (t.get("genre", "") or "").lower()
            if genre and genre.lower() in bgm_genre:
                score += 0.2
                reasons.append(f"风格匹配: {genre}")

            if score > 0:
                scored.append((score, t, reasons))

        scored.sort(key=lambda x: -x[0])
        top = scored[:limit]

        candidates = [
            {
                "bgm_id": t.get("id", t.get("title", f"bgm_{i}")),
                "title": t.get("title", ""),
                "artist": t.get("artist", ""),
                "genre": t.get("genre", ""),
                "energy": t.get("avg_energy", t.get("energy", 0.5)),
                "duration": t.get("duration", 0),
                "preview_url": t.get("preview_url", t.get("audio_file", "")),
                "emotion_tags": t.get("emotion_tags", []),
                "match_score": round(s, 2),
            }
            for i, (s, t, _) in enumerate(top)
        ]

        return {
            "total_candidates": len(candidates),
            "candidates": candidates,
            "search_params": {
                "mood": mood,
                "energy_range": energy_range,
                "genre": genre,
            },
        }

    except Exception as e:
        return {"error": f"搜索失败: {str(e)}", "candidates": []}


@_register
async def score_and_rank(candidate_ids: list, video_analysis_id: str = "") -> dict:
    """
    对候选 BGM 进行多维度评分和精排序。

    使用现有的 AudioFilter（14维评分）和 MiMoFineRanker（LLM精排）。
    """
    try:
        # 获取视频分析结果
        video_analysis = None
        if video_analysis_id and video_analysis_id in analysis_tasks:
            video_analysis = analysis_tasks[video_analysis_id]

        # 加载曲库
        if not os.path.isfile(LIBRARY_PATH):
            return {"error": f"曲库文件不存在: {LIBRARY_PATH}", "recommendations": []}

        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            library = json.load(f)

        tracks = library if isinstance(library, list) else library.get("bgm_list", library.get("tracks", []))

        # 筛选候选
        candidates = [t for t in tracks if t.get("id") in candidate_ids]
        if not candidates:
            # 用 title 或 bgm_id 兜底匹配
            candidates = [t for t in tracks if t.get("title") in candidate_ids or t.get("id") in candidate_ids]

        if not candidates:
            return {"error": "未找到匹配的候选BGM", "recommendations": []}

        # 构建完整的 video_analysis dict（兼容现有服务接口）
        analysis_dict = {}
        if video_analysis:
            ra = video_analysis.get("raw_analysis", {})
            cv = video_analysis.get("raw_cv", {})
            analysis_dict = {
                "visual": ra.get("visual", {}),
                "semantic": ra.get("semantic", {}),
                "audio": ra.get("audio", {}),
                "temporal": ra.get("temporal", {}),
                "text": ra.get("text", {}),
                "cv_data": cv,
            }

        # Stage 2: AudioFilter 评分
        AudioFilter = _lazy_import("AudioFilter")
        filter_instance = AudioFilter()

        # 构造兼容的格式
        from models.schemas import VideoAnalysisResult
        analysis_obj = VideoAnalysisResult(**analysis_dict) if analysis_dict else None

        # Stage 2: AudioFilter 评分
        stage2 = []
        try:
            stage2 = filter_instance.filter(analysis_obj, candidates) if analysis_dict else candidates[:5]
        except Exception as e:
            print(f"[score_and_rank] AudioFilter error: {e}")
            stage2 = candidates[:5]

        # Stage 3: MiMoFineRanker 精排
        ranked = []
        try:
            MiMoFineRanker = _lazy_import("MiMoFineRanker")
            ranker = MiMoFineRanker()
            ranked = await ranker.rank(analysis_dict or {}, stage2)
        except Exception as e:
            print(f"[score_and_rank] MiMoFineRanker error: {e}")

        if not ranked:
            ranked = stage2

        # 确保每个item有fine_score
        for item in ranked:
            if "fine_score" not in item or not item.get("fine_score"):
                if "score" in item and item.get("score"):
                    item["fine_score"] = item["score"]
                elif "match_score" in item:
                    item["fine_score"] = item["match_score"]
                else:
                    item["fine_score"] = 0.5

        recommendations = []
        for item in ranked:
            track = item.get("track", item)
            recommendations.append({
                "rank": item.get("fine_rank", item.get("rank", 1)),
                "bgm_id": track.get("id", ""),
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "score": item.get("fine_score", item.get("score", 0.5)),
                "reason": item.get("fine_reason", item.get("reason", "")),
                "recommended_start_sec": item.get("recommended_start_sec", 0),
                "preview_url": track.get("preview_url", track.get("audio_file", "")),
                "genre": track.get("genre", ""),
                "energy": track.get("avg_energy", track.get("energy", 0.5)),
                "emotion_tags": track.get("emotion_tags", []),
            })

        return {"recommendations": recommendations}

    except Exception as e:
        return {
            "error": f"评分排序失败: {str(e)}",
            "traceback": traceback.format_exc(),
            "recommendations": [],
        }


@_register
async def adjust_volume(bgm_id: str, analysis_id: str = "") -> dict:
    """为 BGM 生成音量调整方案"""
    try:
        VolumeAdjuster = _lazy_import("VolumeAdjuster")
        adjuster = VolumeAdjuster()
        result = adjuster.adjust(bgm_id, analysis_id)
        return {"bgm_id": bgm_id, "volume_adjustments": result}
    except Exception as e:
        return {"bgm_id": bgm_id, "error": str(e), "volume_adjustments": []}


@_register
async def detect_conflict(bgm_id: str, video_analysis_id: str = "", recommended_start_sec: float = 0) -> dict:
    """检测音画冲突"""
    try:
        ConflictDetector = _lazy_import("ConflictDetector")
        detector = ConflictDetector()

        video_analysis = {}
        if video_analysis_id and video_analysis_id in analysis_tasks:
            video_analysis = analysis_tasks[video_analysis_id]

        result = detector.detect(bgm_id, video_analysis, recommended_start_sec)
        return {
            "bgm_id": bgm_id,
            "has_conflict": result.get("has_conflict", False),
            "conflicts": result.get("conflicts", []),
        }
    except Exception as e:
        return {"bgm_id": bgm_id, "has_conflict": False, "error": str(e)}


TOOL_NAME_MAP = {fn.__name__: fn for fn in TOOL_EXECUTORS.values()}


async def execute_tool(name: str, args: dict) -> Any:
    """根据名称和参数调用对应的工具"""
    fn = TOOL_NAME_MAP.get(name)
    if not fn:
        return {"error": f"未知工具: {name}"}
    return await fn(**args)
