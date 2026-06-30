import pytest


def test_conflict_detector_initialization():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    assert detector is not None


def test_detect_no_conflict():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 120, "energy_curve": [0.3, 0.5, 0.7, 0.5, 0.3]}
    analysis_audio = {"speech_segments": [], "ambient_noise_level": "安静"}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is False


def test_detect_conflict_short_speech_high_tempo():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 150, "energy_curve": [0.3, 0.5, 0.7, 0.5, 0.3]}
    analysis_audio = {"speech_segments": [[5.0, 6.0]], "ambient_noise_level": "安静"}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is True


def test_detect_no_conflict_long_speech():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 150, "energy_curve": [0.3, 0.5, 0.7, 0.5, 0.3]}
    analysis_audio = {"speech_segments": [[5.0, 10.0]], "ambient_noise_level": "嘈杂"}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is False


def test_detect_no_conflict_low_tempo():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 100, "energy_curve": [0.3, 0.5, 0.7, 0.5, 0.3]}
    analysis_audio = {"speech_segments": [[5.0, 6.0]], "ambient_noise_level": "安静"}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is False


def test_detect_no_speech_key_missing():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 200}
    analysis_audio = {"ambient_noise_level": "安静"}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is False


def test_emotion_mismatch():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    assert detector.has_emotion_mismatch("悲伤", "兴奋") is True
    assert detector.has_emotion_mismatch("兴奋", "悲伤") is True
    assert detector.has_emotion_mismatch("紧张", "温馨") is True
    assert detector.has_emotion_mismatch("温馨", "紧张") is True


def test_emotion_no_mismatch():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    assert detector.has_emotion_mismatch("平静", "愉快") is False
    assert detector.has_emotion_mismatch("兴奋", "激昂") is False
    assert detector.has_emotion_mismatch("悲伤", "悲伤") is False


def test_detect_multiple_segments_one_conflict():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 160}
    analysis_audio = {"speech_segments": [[5.0, 10.0], [20.0, 21.0]]}
    has_conflict = detector.detect(bgm, analysis_audio)
    assert has_conflict is True


def test_detect_malformed_segment():
    from services.conflict_detector import ConflictDetector
    detector = ConflictDetector()
    bgm = {"tempo": 160}
    analysis_audio = {"speech_segments": [[1.0], [5.0, 6.0]]}
    has_conflict = detector.detect(bgm, analysis_audio)
    # Only the second segment (5.0, 6.0) is valid; it's <2s with high tempo
    assert has_conflict is True
