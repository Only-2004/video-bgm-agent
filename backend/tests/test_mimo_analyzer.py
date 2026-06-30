import pytest
import json
import os


def test_mimo_analyzer_initialization():
    """测试 MiMoAnalyzer 能正常初始化"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    assert analyzer is not None
    assert analyzer.prompts is not None


def test_load_prompt():
    """测试 prompt 加载"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    prompt = analyzer._load_prompt("visual")
    assert "视觉内容" in prompt


def test_load_all_prompts():
    """测试所有 prompt 都已加载"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    for dim in ["visual", "audio", "temporal", "text", "semantic"]:
        assert dim in analyzer.prompts, f"Missing prompt for {dim}"
        assert len(analyzer.prompts[dim]) > 0, f"Empty prompt for {dim}"


def test_parse_response():
    """测试 JSON 响应解析"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    test_response = '{"scene": "海边", "objects": ["海浪"]}'
    result = analyzer._parse_response(test_response)
    assert result["scene"] == "海边"


def test_parse_response_with_markdown():
    """测试解析带 markdown 代码块的响应"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    test_response = '```json\n{"scene": "室内", "objects": ["桌子"]}\n```'
    result = analyzer._parse_response(test_response)
    assert result["scene"] == "室内"
    assert "桌子" in result["objects"]


def test_parse_response_invalid():
    """测试解析无效 JSON"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    result = analyzer._parse_response("this is not json at all")
    assert result == {}


def test_default_results():
    """测试各维度的默认降级结果"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    for dim in ["visual", "audio", "temporal", "text", "semantic"]:
        default = analyzer._get_default_result(dim)
        assert isinstance(default, dict)
        assert len(default) > 0


def test_default_visual_result():
    """测试 visual 维度默认结果结构"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    result = analyzer._get_default_result("visual")
    assert "scene" in result
    assert "objects" in result
    assert "people_count" in result
    assert "activity" in result


def test_default_audio_result():
    """测试 audio 维度默认结果结构"""
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    result = analyzer._get_default_result("audio")
    assert "has_speech" in result
    assert "emotional_tone" in result
    assert "audio_events" in result


def test_analyze_video_empty_frames():
    """测试空帧列表时返回默认结果"""
    import asyncio
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer()
    result = asyncio.get_event_loop().run_until_complete(
        analyzer.analyze_video([])
    )
    assert "visual" in result
    assert "audio" in result
    assert "temporal" in result
    assert "text" in result
    assert "semantic" in result
    # 空帧时应返回默认值
    assert result["visual"]["scene"] == "未知"


def test_analyze_video_no_api_key():
    """测试无 API key 时的降级行为"""
    import asyncio
    from services.mimo_analyzer import MiMoAnalyzer

    analyzer = MiMoAnalyzer(api_key="")
    # 即使有帧路径，无 API key 也应返回默认结果（不会抛异常）
    result = asyncio.get_event_loop().run_until_complete(
        analyzer.analyze_video(["nonexistent.jpg"])
    )
    assert "visual" in result
    assert "semantic" in result
