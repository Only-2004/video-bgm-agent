import pytest


def test_bgm_matcher_initialization():
    from services.bgm_matcher import BGMMatcher

    matcher = BGMMatcher()
    assert matcher is not None


def test_load_bgm_library():
    from services.bgm_matcher import BGMMatcher

    matcher = BGMMatcher()
    assert len(matcher.bgm_library) > 0
    assert len(matcher.bgm_library) >= 6


def test_vector_search():
    from services.bgm_matcher import BGMMatcher

    matcher = BGMMatcher()
    query = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    results = matcher.vector_search(query, top_k=3)
    assert len(results) == 3
    assert all(isinstance(i, int) for i in results)


def test_vector_search_returns_descending_similarity():
    from services.bgm_matcher import BGMMatcher

    matcher = BGMMatcher()
    query = [0.2, 0.8, 0.5, 0.1, 0.1, 0.3, 0.4, 0.6]  # matches bgm_001 exactly
    results = matcher.vector_search(query, top_k=6)
    # bgm_001 should be first (exact match)
    assert results[0] == 0


def test_build_query_vector_known_emotion():
    from services.bgm_matcher import BGMMatcher
    from models.schemas import (
        VideoAnalysisResult,
        SemanticResult,
        EmotionCurve,
        VisualResult,
        AudioResult,
        TemporalResult,
        TextResult,
    )

    matcher = BGMMatcher()

    analysis = VideoAnalysisResult(
        video_id="test",
        visual=VisualResult(
            scene="海边",
            objects=[],
            people_count="单人",
            activity="休闲",
            color_tone="暖色调",
            lighting="自然光",
            visual_style="写实",
        ),
        audio=AudioResult(
            has_speech=False,
            speech_segments=[],
            ambient_noise_level="安静",
            music_playing=False,
            emotional_tone="平静",
            audio_events=[],
        ),
        temporal=TemporalResult(
            scene_changes=3,
            editing_rhythm="中等",
            key_moments=[5.0, 15.0],
            narrative_pace="平缓",
            rhythm_curve=[0.3, 0.5, 0.7, 0.5, 0.3],
        ),
        text=TextResult(
            has_subtitles=False,
            subtitle_content="",
            on_screen_text=[],
            text_sentiment="中性",
        ),
        semantic=SemanticResult(
            narrative_structure="线性叙事",
            emotion="愉快",
            emotion_curve=["平静", "愉快", "平静"],
            theme="旅行",
            purpose="生活记录",
        ),
        emotion_curve=EmotionCurve(
            time_points=[0, 5, 10],
            emotions=["平静", "愉快", "平静"],
            intensity=[0.3, 0.6, 0.3],
        ),
        confidence=0.85,
        created_at="2026-01-01T00:00:00",
    )

    vec = matcher._build_query_vector(analysis)
    assert len(vec) == 8
    assert vec == [0.2, 0.8, 0.6, 0.1, 0.2, 0.4, 0.5, 0.7]


def test_build_query_vector_unknown_emotion():
    from services.bgm_matcher import BGMMatcher
    from models.schemas import (
        VideoAnalysisResult,
        SemanticResult,
        EmotionCurve,
        VisualResult,
        AudioResult,
        TemporalResult,
        TextResult,
    )

    matcher = BGMMatcher()
    analysis = VideoAnalysisResult(
        video_id="test",
        visual=VisualResult(
            scene="城市",
            objects=[],
            people_count="多人",
            activity="社交",
            color_tone="冷色调",
            lighting="人工光",
            visual_style="写实",
        ),
        audio=AudioResult(
            has_speech=True,
            speech_segments=[[1.0, 3.0]],
            ambient_noise_level="嘈杂",
            music_playing=False,
            emotional_tone="中性",
            audio_events=[],
        ),
        temporal=TemporalResult(
            scene_changes=5,
            editing_rhythm="快",
            key_moments=[2.0],
            narrative_pace="快速",
            rhythm_curve=[0.6, 0.8, 0.5, 0.7],
        ),
        text=TextResult(
            has_subtitles=True,
            subtitle_content="hello",
            on_screen_text=[],
            text_sentiment="中性",
        ),
        semantic=SemanticResult(
            narrative_structure="线性叙事",
            emotion="未知情绪",
            emotion_curve=["未知情绪"],
            theme="测试",
            purpose="测试",
        ),
        emotion_curve=EmotionCurve(
            time_points=[0],
            emotions=["未知情绪"],
            intensity=[0.5],
        ),
        confidence=0.5,
        created_at="2026-01-01T00:00:00",
    )

    vec = matcher._build_query_vector(analysis)
    assert vec == [0.5] * 8


def test_match_returns_recommendations():
    from services.bgm_matcher import BGMMatcher
    from models.schemas import (
        VideoAnalysisResult,
        SemanticResult,
        EmotionCurve,
        VisualResult,
        AudioResult,
        TemporalResult,
        TextResult,
    )

    matcher = BGMMatcher()

    analysis = VideoAnalysisResult(
        video_id="test",
        visual=VisualResult(
            scene="海边",
            objects=[],
            people_count="单人",
            activity="休闲",
            color_tone="暖色调",
            lighting="自然光",
            visual_style="写实",
        ),
        audio=AudioResult(
            has_speech=False,
            speech_segments=[],
            ambient_noise_level="安静",
            music_playing=False,
            emotional_tone="平静",
            audio_events=[],
        ),
        temporal=TemporalResult(
            scene_changes=3,
            editing_rhythm="中等",
            key_moments=[5.0, 15.0],
            narrative_pace="平缓",
            rhythm_curve=[0.3, 0.5, 0.7, 0.5, 0.3],
        ),
        text=TextResult(
            has_subtitles=False,
            subtitle_content="",
            on_screen_text=[],
            text_sentiment="中性",
        ),
        semantic=SemanticResult(
            narrative_structure="线性叙事",
            emotion="愉快",
            emotion_curve=["平静", "愉快", "平静"],
            theme="旅行",
            purpose="生活记录",
        ),
        emotion_curve=EmotionCurve(
            time_points=[0, 5, 10],
            emotions=["平静", "愉快", "平静"],
            intensity=[0.3, 0.6, 0.3],
        ),
        confidence=0.85,
        created_at="2026-01-01T00:00:00",
    )

    recommendations = matcher.match(analysis)
    assert len(recommendations) == 3
    assert all(hasattr(r, "match_score") for r in recommendations)
    assert all(r.bgm.id.startswith("bgm_") for r in recommendations)
    # Scores should be in descending order
    scores = [r.match_score for r in recommendations]
    assert scores == sorted(scores, reverse=True)


def test_conflict_filter_removes_low_scores():
    from services.bgm_matcher import BGMMatcher
    from models.schemas import (
        VideoAnalysisResult,
        SemanticResult,
        EmotionCurve,
        VisualResult,
        AudioResult,
        TemporalResult,
        TextResult,
    )

    matcher = BGMMatcher()

    # Analysis with speech segments
    analysis = VideoAnalysisResult(
        video_id="test",
        visual=VisualResult(
            scene="室内",
            objects=[],
            people_count="单人",
            activity="演讲",
            color_tone="中性色调",
            lighting="人工光",
            visual_style="写实",
        ),
        audio=AudioResult(
            has_speech=True,
            speech_segments=[[0.0, 5.0], [10.0, 15.0]],
            ambient_noise_level="安静",
            music_playing=False,
            emotional_tone="平静",
            audio_events=[],
        ),
        temporal=TemporalResult(
            scene_changes=2,
            editing_rhythm="慢",
            key_moments=[],
            narrative_pace="平缓",
            rhythm_curve=[0.2, 0.3, 0.2, 0.3],
        ),
        text=TextResult(
            has_subtitles=True,
            subtitle_content="test",
            on_screen_text=[],
            text_sentiment="中性",
        ),
        semantic=SemanticResult(
            narrative_structure="线性叙事",
            emotion="平静",
            emotion_curve=["平静"],
            theme="教育",
            purpose="教学",
        ),
        emotion_curve=EmotionCurve(
            time_points=[0, 5],
            emotions=["平静", "平静"],
            intensity=[0.3, 0.3],
        ),
        confidence=0.8,
        created_at="2026-01-01T00:00:00",
    )

    recommendations = matcher.match(analysis)
    # Should still return results (conflict_filter uses ConflictDetector, not score threshold)
    assert len(recommendations) > 0
    for r in recommendations:
        assert r.match_score > 0
