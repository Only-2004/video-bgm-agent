import pytest


def test_volume_adjuster_initialization():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    assert adjuster is not None


def test_adjust_no_speech():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    adjustments = adjuster.adjust([], 30.0)
    assert len(adjustments) == 0


def test_adjust_with_speech():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[5.0, 10.0], [20.0, 25.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    assert len(adjustments) > 0
    assert any(a["reason"] == "人声区域" for a in adjustments)


def test_adjust_speech_region_volume_ratio():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[5.0, 10.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    speech_adj = [a for a in adjustments if a["reason"] == "人声区域"]
    assert len(speech_adj) == 1
    assert speech_adj[0]["volume_ratio"] == 0.125


def test_adjust_transition_before_speech():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[5.0, 10.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    pre_adj = [a for a in adjustments if a["reason"] == "人声前过渡"]
    assert len(pre_adj) == 1
    assert pre_adj[0]["start"] == 4.5
    assert pre_adj[0]["end"] == 5.0
    assert pre_adj[0]["volume_ratio"] == 0.5


def test_adjust_transition_after_speech():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[5.0, 10.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    post_adj = [a for a in adjustments if a["reason"] == "人声后过渡"]
    assert len(post_adj) == 1
    assert post_adj[0]["start"] == 10.0
    assert post_adj[0]["end"] == 10.5
    assert post_adj[0]["volume_ratio"] == 0.5


def test_adjust_no_transition_at_start():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[0.0, 5.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    pre_adj = [a for a in adjustments if a["reason"] == "人声前过渡"]
    assert len(pre_adj) == 0


def test_adjust_no_transition_at_end():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[25.0, 30.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    post_adj = [a for a in adjustments if a["reason"] == "人声后过渡"]
    assert len(post_adj) == 0


def test_adjust_sorted_by_start():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[20.0, 25.0], [5.0, 10.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    starts = [a["start"] for a in adjustments]
    assert starts == sorted(starts)


def test_adjust_malformed_segment_skipped():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    speech_segments = [[1.0], [5.0, 10.0]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    # Only the second segment is valid
    speech_adj = [a for a in adjustments if a["reason"] == "人声区域"]
    assert len(speech_adj) == 1
    assert speech_adj[0]["start"] == 5.0


def test_adjust_transition_clamped_to_duration():
    from services.volume_adjuster import VolumeAdjuster
    adjuster = VolumeAdjuster()
    # Speech near the end but not at the very end - post-transition end should clamp
    speech_segments = [[27.0, 29.5]]
    adjustments = adjuster.adjust(speech_segments, 30.0)
    post_adj = [a for a in adjustments if a["reason"] == "人声后过渡"]
    assert len(post_adj) == 1
    assert post_adj[0]["end"] <= 30.0
    # The transition extends 0.5s past 29.5, which is 30.0, clamped to video_duration
    assert post_adj[0]["end"] == 30.0
