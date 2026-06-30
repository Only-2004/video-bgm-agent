"""
从 Jamendo 拉取免费BGM音乐并导入本地库

使用前：
  1. 访问 https://developer.jamendo.com/ 注册账号
  2. 创建应用，获取 client_id
  3. 运行：python tools/jamendo_fetcher.py --client-id YOUR_ID

存储位置：D:/video-bgm-data/audio/ (不占C盘)
"""

import argparse
import json
import os
import random
import sys
import time
import uuid

import requests

# Fix Windows GBK encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# D盘路径，不占C盘
AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"

# 情绪 → Jamendo tags 映射（按情绪搜索）
EMOTION_SEARCHES = {
    "平静": ["ambient", "calm", "relaxing", "meditation", "chillout"],
    "愉快": ["happy", "upbeat", "cheerful", "feel good", "summer"],
    "兴奋": ["energetic", "dance", "electronic", "party", "workout"],
    "悲伤": ["sad", "melancholic", "emotional", "lonely", "dark"],
    "紧张": ["suspense", "tension", "cinematic", "thriller", "mystery"],
    "激昂": ["epic", "powerful", "motivational", "trailer", "hero"],
    "温馨": ["gentle", "acoustic", "folk", "warm", "love"],
    "搞笑": ["funny", "quirky", "comedy", "playful", "cartoon"],
}

# 8维情绪向量
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

# 能量曲线
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


def add_noise(vec, amplitude=0.05):
    return [max(0, min(1, v + random.uniform(-amplitude, amplitude))) for v in vec]


def estimate_beats(bpm, duration):
    if bpm <= 0:
        bpm = 100
    interval = 60.0 / bpm
    beats = []
    t = 0.0
    while t <= duration:
        beats.append(round(t, 2))
        t += interval
    return beats


def build_structure(duration):
    return {
        "intro": [0, round(duration * 0.15, 1)],
        "build_up": [round(duration * 0.15, 1), round(duration * 0.35, 1)],
        "climax": [round(duration * 0.35, 1), round(duration * 0.80, 1)],
        "outro": [round(duration * 0.80, 1), float(duration)],
    }


def search_tracks(client_id, emotion, num=30):
    """搜索某个情绪的音乐"""
    keywords = EMOTION_SEARCHES.get(emotion, ["music"])
    keyword = random.choice(keywords)

    all_tracks = []
    seen_ids = set()

    for kw in [keyword] + random.sample(keywords, min(2, len(keywords) - 1)):
        try:
            r = requests.get("https://api.jamendo.com/v3.0/tracks/", params={
                "client_id": client_id,
                "format": "json",
                "limit": min(num, 50),
                "search": kw,
                "include": "musicinfo",
                "audioformat": "mp32",
                "order": "popularity_total",
            }, timeout=15)

            if r.status_code != 200:
                print(f"  API错误 {r.status_code}: {kw}")
                continue

            data = r.json()
            tracks = data.get("results", [])

            for t in tracks:
                tid = t.get("id")
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                # 过滤：只要音乐，不要音效
                duration = t.get("duration", 0)
                if duration < 30 or duration > 600:
                    continue
                if not t.get("audio"):
                    continue

                all_tracks.append(t)

            print(f"  搜索 '{kw}' → {len(tracks)} 结果，累计 {len(all_tracks)} 首")
            time.sleep(0.5)

        except Exception as e:
            print(f"  搜索失败 '{kw}': {e}")

    return all_tracks[:num]


def download_track(audio_url, output_dir):
    """下载单曲MP3"""
    filename = f"bgm_{uuid.uuid4().hex[:8]}"
    filepath = os.path.join(output_dir, f"{filename}.mp3")

    try:
        r = requests.get(audio_url, timeout=60, stream=True)
        if r.status_code != 200:
            return None

        with open(filepath, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        return filepath, filename
    except Exception as e:
        print(f"  下载失败: {e}")
        return None


def build_bgm_entry(track, filename, emotion):
    """构建 BGM 库条目"""
    title = track.get("name", "Unknown")
    artist = track.get("artist_name", "Unknown")
    duration = track.get("duration", 180)
    bpm = track.get("bpm", 0)
    if bpm <= 0:
        bpm = 100

    tags = []
    musicinfo = track.get("musicinfo", {})
    if isinstance(musicinfo, dict):
        tags = musicinfo.get("tags", {}).get("genres", [])

    return {
        "id": filename,
        "title": title,
        "artist": artist,
        "emotion": emotion,
        "tempo": bpm,
        "beat_positions": estimate_beats(bpm, duration),
        "structure": build_structure(duration),
        "style_tags": tags[:5] if tags else ["jamendo", "cc"],
        "energy_curve": ENERGY_CURVES.get(emotion, [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3]),
        "duration": duration,
        "preview_url": f"/audio/{filename}.mp3",
        "source": "jamendo",
    }


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
    parser = argparse.ArgumentParser(description="从Jamendo拉取免费BGM到本地库")
    parser.add_argument("--client-id", required=True, help="Jamendo API client_id")
    parser.add_argument("--num", type=int, default=200, help="目标下载数量 (默认200)")
    parser.add_argument("--emotion", help="只下载指定情绪 (平静/愉快/兴奋/悲伤/紧张/激昂/温馨/搞笑)")
    args = parser.parse_args()

    os.makedirs(AUDIO_DIR, exist_ok=True)
    library = load_library()
    existing_titles = {item.get("title", "") for item in library}

    target = args.num
    success = 0
    fail = 0
    skip = 0

    # 分配每种情绪的下载数
    emotions = [args.emotion] if args.emotion else list(EMOTION_SEARCHES.keys())
    per_emotion = max(target // len(emotions), 10)

    print(f"=" * 50)
    print(f"Jamendo BGM 拉取工具")
    print(f"目标: {target} 首 | 情绪: {len(emotions)} 种 | 每种: ~{per_emotion} 首")
    print(f"存储: {AUDIO_DIR}")
    print(f"=" * 50)

    for emotion in emotions:
        if success >= target:
            break

        print(f"\n[{emotion}] 搜索中...")
        tracks = search_tracks(args.client_id, emotion, per_emotion)
        print(f"  找到 {len(tracks)} 首候选")

        for i, track in enumerate(tracks):
            if success >= target:
                break

            title = track.get("name", "Unknown")
            if title in existing_titles:
                skip += 1
                continue

            audio_url = track.get("audio")
            if not audio_url:
                fail += 1
                continue

            print(f"  [{success+1}/{target}] {title} - {track.get('artist_name', '?')}...", end=" ")

            result = download_track(audio_url, AUDIO_DIR)
            if not result:
                fail += 1
                print("失败")
                continue

            filepath, filename = result
            entry = build_bgm_entry(track, filename, emotion)
            library.append(entry)
            existing_titles.add(title)
            success += 1
            print(f"OK ({track.get('duration', 0)}s)")

            time.sleep(0.3)

    # 保存
    save_library(library)
    print(f"\n{'=' * 50}")
    print(f"完成! 成功: {success} | 跳过: {skip} | 失败: {fail}")
    print(f"库总数: {len(library)} 首")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
