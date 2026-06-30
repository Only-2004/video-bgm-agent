"""
从网易云音乐热歌榜批量下载BGM到本地库

数据来源：网易云音乐官方热歌榜 (id=3778678)
所有文件存储在D盘，不占C盘空间

用法：
  python tools/netease_hot_fetcher.py
  python tools/netease_hot_fetcher.py --num 100
  python tools/netease_hot_fetcher.py --chart 3778678  # 热歌榜
  python tools/netease_hot_fetcher.py --chart 3779629  # 新歌榜
"""

import argparse
import json
import os
import random
import sys
import time
import uuid

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"

# 网易云音乐榜单ID
CHARTS = {
    "热歌榜": 3778678,
    "新歌榜": 3779629,
    "飙升榜": 19723756,
    "原创榜": 3778678,
}

# 情绪推断
EMOTION_KEYWORDS = {
    "平静": ["舒缓", "轻音乐", "钢琴", "安静", "放松", "冥想", "月光", "小夜曲", "摇篮曲", "大海", "天空", "雨", "风"],
    "愉快": ["欢快", "开心", "阳光", "快乐", "活泼", "夏天", "甜蜜", "微笑", "晴天"],
    "兴奋": ["嗨", "DJ", "蹦迪", "电音", "燃", "热血", "动感", "摇滚", "battle"],
    "悲伤": ["伤感", "忧伤", "emo", "哭", "失恋", "离别", "孤独", "寂寞", "遗憾"],
    "紧张": ["悬疑", "紧张", "惊悚", "暗", "黑"],
    "激昂": ["励志", "震撼", "史诗", "运动", "战斗", "冠军", "怒放", "飞"],
    "温馨": ["温暖", "治愈", "温柔", "甜蜜", "浪漫", "爱", "家", "母亲", "童年"],
    "搞笑": ["搞笑", "沙雕", "鬼畜", "魔性", "哈哈"],
}

EMOTION_VECTORS = {
    "平静": [0.8, 0.2, 0.1, 0.3, 0.1, 0.1, 0.6, 0.2],
    "愉快": [0.2, 0.8, 0.6, 0.1, 0.2, 0.4, 0.5, 0.7],
    "兴奋": [0.1, 0.6, 0.9, 0.1, 0.3, 0.8, 0.2, 0.6],
    "悲伤": [0.3, 0.1, 0.1, 0.9, 0.6, 0.1, 0.2, 0.1],
    "紧张": [0.2, 0.2, 0.4, 0.5, 0.8, 0.6, 0.1, 0.2],
    "激昂": [0.1, 0.5, 0.7, 0.1, 0.5, 0.9, 0.2, 0.4],
    "温馨": [0.7, 0.5, 0.3, 0.2, 0.1, 0.2, 0.8, 0.4],
    "搞笑": [0.2, 0.7, 0.5, 0.1, 0.2, 0.4, 0.4, 0.9],
}

ENERGY_CURVES = {
    "平静": [0.2, 0.3, 0.3, 0.4, 0.3, 0.2, 0.2],
    "愉快": [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3],
    "兴奋": [0.4, 0.7, 0.9, 1.0, 0.9, 0.6, 0.3],
    "悲伤": [0.3, 0.2, 0.3, 0.4, 0.5, 0.3, 0.2],
    "紧张": [0.5, 0.7, 0.8, 0.9, 0.8, 0.6, 0.4],
    "激昂": [0.4, 0.7, 0.9, 1.0, 0.8, 0.5, 0.3],
    "温馨": [0.2, 0.3, 0.4, 0.5, 0.5, 0.3, 0.2],
    "搞笑": [0.3, 0.6, 0.8, 0.9, 0.7, 0.5, 0.3],
}


def infer_emotion(name, artist=""):
    text = name + " " + artist
    for emo, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return emo
    return "温馨"


def add_noise(vec, amp=0.05):
    return [max(0, min(1, v + random.uniform(-amp, amp))) for v in vec]


def estimate_beats(bpm, duration):
    if bpm <= 0:
        bpm = 100
    interval = 60.0 / bpm
    beats, t = [], 0.0
    while t <= duration:
        beats.append(round(t, 2))
        t += interval
    return beats


def build_structure(dur):
    return {
        "intro": [0, round(dur * 0.15, 1)],
        "build_up": [round(dur * 0.15, 1), round(dur * 0.35, 1)],
        "climax": [round(dur * 0.35, 1), round(dur * 0.80, 1)],
        "outro": [round(dur * 0.80, 1), float(dur)],
    }


def get_chart_tracks(chart_id):
    """获取榜单歌曲列表"""
    url = "https://music.163.com/api/playlist/detail"
    r = requests.get(url, params={"id": chart_id}, timeout=15)
    if r.status_code != 200:
        return []
    data = r.json()
    return data.get("result", {}).get("tracks", [])


def download_song(song_id, output_dir):
    """下载单曲MP3"""
    filename = f"bgm_{uuid.uuid4().hex[:8]}"
    filepath = os.path.join(output_dir, f"{filename}.mp3")

    url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                         timeout=30, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 50000:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return filepath, filename, len(r.content)
    except Exception:
        pass
    return None, None, 0


def load_library():
    if os.path.exists(LIBRARY_PATH):
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("bgm_list", [])
    return []


def save_library(bgm_list):
    os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump({"bgm_list": bgm_list}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="从网易云音乐下载热歌到本地BGM库")
    parser.add_argument("--num", type=int, default=100, help="下载数量 (默认100)")
    parser.add_argument("--chart", type=int, default=3778678, help="榜单ID (默认热歌榜)")
    args = parser.parse_args()

    os.makedirs(AUDIO_DIR, exist_ok=True)
    library = load_library()
    existing_titles = {item.get("title", "") for item in library}

    print(f"=" * 50)
    print(f"网易云音乐热歌下载工具")
    print(f"榜单ID: {args.chart} | 目标: {args.num} 首")
    print(f"存储: {AUDIO_DIR}")
    print(f"=" * 50)

    # 获取榜单
    print("\n获取榜单...")
    tracks = get_chart_tracks(args.chart)
    print(f"榜单共 {len(tracks)} 首")

    if not tracks:
        print("获取榜单失败!")
        return

    success = 0
    fail = 0
    skip = 0

    for i, track in enumerate(tracks):
        if success >= args.num:
            break

        name = track.get("name", "Unknown")
        artist = track.get("artists", [{}])[0].get("name", "Unknown")
        song_id = track.get("id")

        # 跳过已存在
        if name in existing_titles:
            skip += 1
            continue

        if not song_id:
            fail += 1
            continue

        print(f"[{success+1}/{args.num}] {name} - {artist}...", end=" ", flush=True)

        filepath, filename, size = download_song(song_id, AUDIO_DIR)
        if not filepath:
            fail += 1
            print("失败")
            continue

        emotion = infer_emotion(name, artist)
        duration = track.get("duration", 180000) // 1000  # ms → s
        bpm = random.randint(80, 130)

        entry = {
            "id": filename,
            "title": name,
            "artist": artist,
            "emotion": emotion,
            "tempo": bpm,
            "beat_positions": estimate_beats(bpm, duration),
            "structure": build_structure(duration),
            "style_tags": ["网易云", "热歌", "华语"],
            "energy_curve": ENERGY_CURVES.get(emotion, [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3]),
            "duration": duration,
            "preview_url": f"/audio/{filename}.mp3",
            "source": "netease",
        }

        library.append(entry)
        existing_titles.add(name)
        success += 1
        print(f"OK ({duration}s, {size//1024}KB, {emotion})")

        time.sleep(0.5)

    save_library(library)
    print(f"\n{'=' * 50}")
    print(f"完成! 成功: {success} | 跳过: {skip} | 失败: {fail}")
    print(f"库总数: {len(library)} 首")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
