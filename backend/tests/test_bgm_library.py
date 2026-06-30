import json
import os


def test_bgm_library_exists():
    assert os.path.exists("data/bgm_library.json")


def test_bgm_library_structure():
    with open("data/bgm_library.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "bgm_list" in data
    assert len(data["bgm_list"]) > 0


def test_bgm_library_has_required_fields():
    with open("data/bgm_library.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    for bgm in data["bgm_list"]:
        assert "id" in bgm
        assert "title" in bgm
        assert "style_tags" in bgm
        assert "emotion" in bgm
        assert "duration" in bgm
        assert "preview_url" in bgm
