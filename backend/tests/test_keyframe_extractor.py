import pytest
import tempfile
import os
import cv2
import numpy as np


@pytest.fixture
def test_temp_dir():
    """Create a test-specific temporary directory and clean up after."""
    temp_dir = tempfile.mkdtemp(prefix="keyframe_test_")
    yield temp_dir
    # Clean up only within the test-specific directory
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_keyframe_extractor_initialization():
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()
    assert extractor is not None


def test_keyframe_extractor_custom_max_frames():
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor(max_frames=15)
    assert extractor.max_frames == 15


def test_extract_returns_list(test_temp_dir):
    """Test that extract() returns a list of file paths."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()

    # Create a simple test video
    video_path = os.path.join(test_temp_dir, "test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))
    for _ in range(30):  # 3 seconds at 10fps
        frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    result = extractor.extract(video_path)
    assert isinstance(result, list)
    assert len(result) > 0
    # Verify all returned paths are strings and exist
    for path in result:
        assert isinstance(path, str)
        assert os.path.exists(path)


def test_extract_with_empty_video(test_temp_dir):
    """Test that extract() raises FileNotFoundError for non-existent path."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()

    non_existent_path = os.path.join(test_temp_dir, "non_existent_video.mp4")
    with pytest.raises(FileNotFoundError):
        extractor.extract(non_existent_path)


def test_extract_file_not_found():
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract("/nonexistent/video.mp4")


def test_detect_scenes_returns_tuples(test_temp_dir):
    """Test that _detect_scenes returns list of (start, end) tuples."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()

    # Create a test video with scene change
    video_path = os.path.join(test_temp_dir, "test_scenes.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))

    # First scene: red
    for _ in range(25):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:, :, 2] = 255
        out.write(frame)

    # Second scene: blue
    for _ in range(25):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:, :, 0] = 255
        out.write(frame)

    out.release()

    scenes = extractor._detect_scenes(video_path)
    assert isinstance(scenes, list)
    assert len(scenes) > 0
    for scene in scenes:
        assert isinstance(scene, tuple)
        assert len(scene) == 2
        start, end = scene
        assert isinstance(start, (int, float))
        assert isinstance(end, (int, float))
        assert start < end


def test_uniform_sampling_short_scene(test_temp_dir):
    """Short scenes (<=6s) should produce exactly one frame (midpoint)."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()

    video_path = os.path.join(test_temp_dir, "short_scene.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))
    for _ in range(20):  # 2 seconds at 10fps
        frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    frames = extractor._uniform_sampling(video_path, [(0.0, 2.0)])
    assert isinstance(frames, list)
    assert len(frames) == 1  # short scene -> one midpoint frame
    assert os.path.exists(frames[0])


def test_uniform_sampling_long_scene(test_temp_dir):
    """Long scenes (>6s) should produce multiple frames (every 4s)."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor()

    video_path = os.path.join(test_temp_dir, "long_scene.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))
    for _ in range(100):  # 10 seconds at 10fps
        frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    frames = extractor._uniform_sampling(video_path, [(0.0, 10.0)])
    assert isinstance(frames, list)
    assert len(frames) >= 2  # 10s scene -> at least 2 frames (at 0s, 4s, 8s)
    for fp in frames:
        assert os.path.exists(fp)


def test_extract_with_real_video(test_temp_dir):
    """Full integration test: create a test video and extract keyframes."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor(max_frames=10)

    video_path = os.path.join(test_temp_dir, "test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))

    # First scene: red frames
    for _ in range(25):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:, :, 2] = 255  # Red
        out.write(frame)

    # Second scene: blue frames
    for _ in range(25):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # Blue
        out.write(frame)

    out.release()

    result = extractor.extract(video_path)
    assert isinstance(result, list)
    assert len(result) > 0
    assert len(result) <= extractor.max_frames
    for fp in result:
        assert os.path.exists(fp)


def test_max_frames_limit(test_temp_dir):
    """Output should never exceed max_frames."""
    from services.keyframe_extractor import KeyFrameExtractor
    extractor = KeyFrameExtractor(max_frames=3)

    video_path = os.path.join(test_temp_dir, "test_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))
    for i in range(100):
        frame = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        out.write(frame)
    out.release()

    result = extractor.extract(video_path)
    assert len(result) <= extractor.max_frames
