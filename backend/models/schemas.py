from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class VisualResult(BaseModel):
    scene: str
    objects: List[str]
    people_count: str
    activity: str
    color_tone: str
    lighting: str
    visual_style: str


class AudioResult(BaseModel):
    has_speech: bool = False
    speech_segments: List[List[float]] = []
    ambient_noise_level: str = "中等"
    music_playing: bool = False
    emotional_tone: str = "平静"
    audio_events: List[str] = []


class TemporalResult(BaseModel):
    scene_changes: int = 0
    editing_rhythm: str = "中等"
    key_moments: List[float] = []
    narrative_pace: str = "平缓"
    rhythm_curve: List[float] = [0.5]
    scene_change_detected: Optional[bool] = None
    key_moment_score: Optional[float] = None


class TextResult(BaseModel):
    has_subtitles: bool = False
    subtitle_content: str = ""
    subtitle_text: Optional[str] = None
    on_screen_text: List[str] = []
    text_sentiment: str = "中性"


class SceneAnalysis(BaseModel):
    scene_type: str = "未知"
    scene_description: str = ""
    mood: str = "中性"
    visual_energy: float = 0.5


class BGMSuggestion(BaseModel):
    primary_emotion: str = "平静"
    energy_level: str = "中等"
    style_tags: List[str] = []
    reasoning: str = ""


class RhythmSuggestion(BaseModel):
    tempo_range: str = "80-120"
    rhythm_style: str = "中等"
    sync_points: str = ""


class SemanticResult(BaseModel):
    narrative_structure: str = "线性叙事"
    emotion: str = "平静"
    emotion_curve: List[str] = ["平静"]
    theme: str = "未知"
    purpose: str = "未知"
    narrative_position: Optional[str] = None
    emotion_intensity: Optional[float] = None
    scene_analysis: Optional[SceneAnalysis] = None
    bgm_suggestion: Optional[BGMSuggestion] = None
    rhythm_suggestion: Optional[RhythmSuggestion] = None
    music_imagination: Optional[str] = None
    target_emotion: Optional[dict] = None
    bpm_range: Optional[list] = None
    vocal_ok: Optional[bool] = None
    culture_preference: Optional[str] = None
    avoid: Optional[list] = None
    reference_tracks: Optional[list] = None
    # 三阶段闭环新增字段
    video_structure: Optional["VideoStructure"] = None
    overall_atmosphere: Optional[dict] = None
    music_imagination_obj: Optional["MusicImaginationObj"] = None
    key_matching_points: List["KeyMatchingPoint"] = []
    # 8维闭环新增字段
    alignment_strategy: Optional[str] = None  # full_beat_sync / partial_alignment / ambient_only
    camera_motion_type: Optional[str] = None  # 跟拍/手持/推镜头/固定机位/轻微运动
    video_imagination: Optional[str] = None  # 视频渴望什么配乐的灵魂画像
    ideal_bgm_profile: Optional[str] = None  # 理想BGM的自然语言画像（用于Embedding语义检索）
    video_genre: Optional[str] = None  # 视频类型：极限运动/运动/剧情/Vlog/广告/MV/风景/旅行/美食/评测
    rhythm_pattern: Optional[dict] = None  # 剪辑节奏模式：{pattern, intervals, slope, variance, avg_interval}
    narrative_arc: Optional[dict] = None  # 叙事弧线：{arc_type, climax_position, opening_mood, closing_mood}
    video_description: Optional[str] = None  # 视频内容描述（1-2句话）
    emotion_journey: Optional[str] = None  # 情绪旅程（如"从平静→渐渐紧张→高潮爆发→回归温暖"）
    scene_descriptions: Optional[list] = None  # 逐场景描述 [{timestamp, description}]


# ============ 三阶段闭环新增模型 ============

class TransitionPoint(BaseModel):
    timestamp: float
    type: str = ""
    duration: float = 0
    tension_level: float = 0.5
    description: str = ""


class KeyMatchingPoint(BaseModel):
    video_timestamp: float
    importance: str = "中"
    reason: str = ""
    recommended_audio_feature: str = ""


class VideoStructure(BaseModel):
    duration: float = 0
    transition_points: List[TransitionPoint] = []
    tension_curve: List[dict] = []
    emotion_curve: List[dict] = []


class MusicImaginationObj(BaseModel):
    recommended_styles: List[str] = []
    recommended_characteristics: dict = {}
    reference_description: str = ""



class EmotionCurve(BaseModel):
    time_points: List[float]
    emotions: List[str]
    intensity: List[float]


class VideoAnalysisResult(BaseModel):
    video_id: str
    visual: VisualResult
    audio: AudioResult
    temporal: TemporalResult
    text: TextResult
    semantic: SemanticResult
    emotion_curve: EmotionCurve
    confidence: float
    created_at: datetime
    mimo_errors: List[str] = []  # MiMo 失败的维度列表


class BGMStructure(BaseModel):
    intro: List[float] = []
    build_up: List[float] = []
    climax: List[float] = []
    outro: List[float] = []


class BGMTrack(BaseModel):
    id: str
    title: str
    artist: str
    emotion: str
    tempo: float
    beat_positions: List[float]
    structure: BGMStructure
    style_tags: List[str]
    energy_curve: List[float]
    duration: float
    preview_url: str
    source: str = "local"
    # 人工标注字段（扁平schema）
    emotion_tags: List[str] = []
    scene_tags: Optional[dict] = None  # {"fit": [...], "unfit": [...]}
    era: Optional[str] = None  # 复古/现代/经典
    instrumentation: List[str] = []
    arrangement_style: Optional[str] = None  # 极简/层次丰富/单乐器主导/...
    vocal_character: Optional[str] = None  # 无人声/男声/女声/合唱/...
    rhythm_drive: Optional[str] = None  # 鼓点驱动/旋律驱动/氛围驱动/...
    energy_shape: Optional[str] = None  # 平稳/渐强/爆发/脉冲/衰落/先抑后扬/波动
    has_clear_buildup: Optional[bool] = None
    has_clear_climax: Optional[bool] = None
    cultural_context: Optional[str] = None
    # librosa 客观数据
    rhythm_tag: Optional[dict] = None  # bpm, energy, vocal_ratio, beat_regularity, swing_ratio
    feature_text: Optional[str] = None
    avg_energy: Optional[float] = None
    has_vocals: Optional[bool] = None
    structural_sections: Optional[list] = None
    tempo_stability: Optional[float] = None
    chroma_profile: Optional[dict] = None
    spectral_centroid: Optional[float] = None
    beat_regularity: Optional[float] = None
    swing_ratio: Optional[float] = None
    timbre_profile: Optional[dict] = None
    constraints: Optional[dict] = None
    editing_note: Optional[str] = None


class BGMRecommendation(BaseModel):
    bgm: BGMTrack
    match_score: float
    emotion_alignment: float
    rhythm_alignment: float
    reason: str
    volume_adjustments: List[dict]
    start_sec: float = 0
    climax_hint: str = ""
    # 三阶段闭环新增
    cut_points: List[dict] = []
    audio_match: Optional[dict] = None  # 已废弃，保留兼容
    # 8维闭环新增
    bidirectional_factor: Optional[float] = None  # 反向验证系数 0-1（BGM的video_imagination vs 视频实际特征）


class MatchRequest(BaseModel):
    analysis_id: str



# ─── 共享常量 ───

# 视频类型 → 能量参考值（单一数据源，避免重复定义）
# floor: 该类型视频的能量下限（低于此值BGM会"抢戏"）
# reference: 该类型视频的典型能量水平（用于评分匹配）
GENRE_ENERGY = {
    #           (floor, reference)
    "极限运动": (0.6,  0.80),
    "运动":     (0.5,  0.65),
    "剧情":     (0.4,  0.50),
    "广告":     (0.4,  0.55),
    "MV":       (0.4,  0.60),
    "Vlog":     (0.3,  0.45),
    "旅行":     (0.3,  0.45),
    "美食":     (0.3,  0.35),
    "风景":     (0.2,  0.25),
    "评测":     (0.35, 0.50),
}
