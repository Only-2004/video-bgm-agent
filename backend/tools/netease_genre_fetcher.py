"""
从网易云音乐按风格分类下载BGM到本地库

覆盖12种视频常用风格：流行、电子、摇滚、民谣、说唱、爵士、古典、氛围、嘻哈、R&B、独立、中国风
所有文件存储在D盘，不占C盘空间

用法：
  python tools/netease_genre_fetcher.py
  python tools/netease_genre_fetcher.py --num 200
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

# 12种风格，每种对应搜索关键词和情绪标签
GENRE_CONFIG = {
    "pop": {
        "name": "流行 Pop",
        "searches": ["pop hit", "city pop", "synthpop", "K-pop", "流行热歌"],
        "emotion": "愉快",
        "tags": ["pop", "vlog", "时尚"],
    },
    "electronic": {
        "name": "电子 EDM",
        "searches": ["EDM", "house music", "lo-fi beats", "techno", "drum and bass", "synthwave"],
        "emotion": "兴奋",
        "tags": ["electronic", "dance", "科技"],
    },
    "epic": {
        "name": "管弦/史诗",
        "searches": ["epic orchestral", "cinematic trailer", "epic music", "trailer music", "battle music"],
        "emotion": "激昂",
        "tags": ["epic", "cinematic", "宣传片"],
    },
    "rock": {
        "name": "摇滚",
        "searches": ["rock", "alternative rock", "indie rock", "punk rock", "pop rock"],
        "emotion": "兴奋",
        "tags": ["rock", "极限", "热血"],
    },
    "folk": {
        "name": "民谣/原声",
        "searches": ["acoustic folk", "indie folk", "guitar acoustic", "singer songwriter", "campfire"],
        "emotion": "温馨",
        "tags": ["folk", "acoustic", "旅行"],
    },
    "hiphop": {
        "name": "嘻哈/说唱",
        "searches": ["hip hop beat", "trap beat", "lo-fi hip hop", "chill hop", "boom bap"],
        "emotion": "愉快",
        "tags": ["hiphop", "trap", "街拍"],
    },
    "jazz": {
        "name": "爵士/蓝调",
        "searches": ["jazz", "bossa nova", "smooth jazz", "blues", "swing jazz"],
        "emotion": "平静",
        "tags": ["jazz", "咖啡", "文艺"],
    },
    "chinese": {
        "name": "中国风",
        "searches": ["中国风", "古风", "guofeng chinese", "erhu", "pipa chinese"],
        "emotion": "平静",
        "tags": ["chinese", "guofeng", "古风"],
    },
    "ambient": {
        "name": "氛围/背景",
        "searches": ["ambient", "cinematic pad", "drone ambient", "post rock", "atmospheric"],
        "emotion": "平静",
        "tags": ["ambient", "background", "延时"],
    },
    "comedy": {
        "name": "搞笑/特殊",
        "searches": ["funny comedy", "8-bit chiptune", "pizzicato", "cartoon music", "quirky"],
        "emotion": "搞笑",
        "tags": ["comedy", "搞笑", "游戏"],
    },
    "piano": {
        "name": "钢琴/古典",
        "searches": ["piano solo", "modern classical", "neoclassical", "minimal piano", "emotional piano"],
        "emotion": "悲伤",
        "tags": ["piano", "classical", "婚礼"],
    },
    "world": {
        "name": "拉丁/世界",
        "searches": ["reggaeton", "afrobeats", "bollywood", "latin pop", "world music"],
        "emotion": "愉快",
        "tags": ["world", "latin", "舞蹈"],
    },
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


def search_netease(query, limit=10):
    """搜索网易云音乐"""
    url = "https://music.163.com/api/search/get"
    params = {"s": query, "type": 1, "limit": limit, "offset": 0}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return data.get("result", {}).get("songs", [])
    except Exception:
        return []


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
    parser = argparse.ArgumentParser(description="按风格从网易云下载BGM")
    parser.add_argument("--num", type=int, default=180, help="总下载数量 (默认180)")
    args = parser.parse_args()

    os.makedirs(AUDIO_DIR, exist_ok=True)
    library = load_library()
    existing_ids = {t.get("title", "") + t.get("artist", "") for t in library}

    genres = list(GENRE_CONFIG.keys())
    per_genre = max(args.num // len(genres), 8)

    print(f"=" * 55)
    print(f"网易云音乐 - 按风格下载BGM")
    print(f"风格: {len(genres)} 种 | 每种: ~{per_genre} 首 | 总目标: {args.num}")
    print(f"=" * 55)

    success = 0
    fail = 0
    skip = 0

    for genre_key in genres:
        if success >= args.num:
            break

        cfg = GENRE_CONFIG[genre_key]
        print(f"\n[{cfg['name']}] 搜索中...")

        # 搜索多个关键词
        all_songs = []
        seen_ids = set()
        for kw in cfg["searches"]:
            songs = search_netease(kw, limit=10)
            for s in songs:
                sid = s.get("id")
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    all_songs.append(s)
            time.sleep(0.3)

        print(f"  找到 {len(all_songs)} 首候选")

        downloaded = 0
        for song in all_songs:
            if downloaded >= per_genre or success >= args.num:
                break

            name = song.get("name", "Unknown")
            artist = song.get("artists", [{}])[0].get("name", "Unknown")
            song_id = song.get("id")
            key = name + artist

            if key in existing_ids or not song_id:
                skip += 1
                continue

            print(f"  [{success+1}/{args.num}] {name} - {artist}...", end=" ", flush=True)

            filepath, filename, size = download_song(song_id, AUDIO_DIR)
            if not filepath:
                fail += 1
                print("失败")
                continue

            duration = song.get("duration", 180000) // 1000
            bpm = random.randint(80, 130)

            entry = {
                "id": filename,
                "title": name,
                "artist": artist,
                "emotion": cfg["emotion"],
                "tempo": bpm,
                "beat_positions": estimate_beats(bpm, duration),
                "structure": build_structure(duration),
                "style_tags": cfg["tags"],
                "energy_curve": ENERGY_CURVES.get(cfg["emotion"], [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3]),
                "duration": duration,
                "preview_url": f"/audio/{filename}.mp3",
                "source": "netease",
                "genre": genre_key,
            }

            library.append(entry)
            existing_ids.add(key)
            success += 1
            downloaded += 1
            print(f"OK ({duration}s, {size//1024}KB)")

            time.sleep(0.5)

    save_library(library)
    print(f"\n{'=' * 55}")
    print(f"完成! 成功: {success} | 跳过: {skip} | 失败: {fail}")
    print(f"库总数: {len(library)} 首")

    # 统计风格分布
    genre_counts = {}
    for t in library:
        g = t.get("genre", t.get("style_tags", ["?"])[0] if t.get("style_tags") else "?")
        genre_counts[g] = genre_counts.get(g, 0) + 1
    print(f"\n风格分布:")
    for g, c in sorted(genre_counts.items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
