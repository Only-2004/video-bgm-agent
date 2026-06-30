"""
批量导入歌曲到本地BGM库

用法:
  1. 从文件夹批量导入已有MP3:
     python tools/batch_download.py --import-dir "C:/Users/32364/Music"

  2. 从URL列表下载 (需网络):
     python tools/batch_download.py --urls urls.txt

  3. 单首下载:
     python tools/batch_download.py --url "https://www.youtube.com/watch?v=xxx"

  4. 抖音下载需要cookies:
     python tools/batch_download.py --urls urls.txt --cookies cookies.txt

  5. 导出浏览器cookies (用于抖音/B站):
     yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://www.douyin.com
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import AUDIO_DIR, LIBRARY_PATH

EMOTION_MAP = {
    "平静": [0.8, 0.2, 0.1, 0.3, 0.1, 0.1, 0.6, 0.2],
    "愉快": [0.2, 0.8, 0.6, 0.1, 0.2, 0.4, 0.5, 0.7],
    "兴奋": [0.1, 0.6, 0.9, 0.1, 0.3, 0.8, 0.2, 0.6],
    "悲伤": [0.3, 0.1, 0.1, 0.9, 0.6, 0.1, 0.2, 0.1],
    "紧张": [0.2, 0.2, 0.4, 0.5, 0.8, 0.6, 0.1, 0.2],
    "激昂": [0.1, 0.5, 0.7, 0.1, 0.5, 0.9, 0.2, 0.4],
    "温馨": [0.7, 0.5, 0.3, 0.2, 0.1, 0.2, 0.8, 0.4],
    "搞笑": [0.2, 0.7, 0.5, 0.1, 0.2, 0.4, 0.4, 0.9],
}

EMOTION_KEYWORDS = {
    "平静": ["舒缓", "轻音乐", "钢琴", "安静", "放松", "冥想"],
    "愉快": ["欢快", "开心", "阳光", "快乐", "活泼"],
    "兴奋": ["嗨", "DJ", "蹦迪", "电音", "燃", "热血", "动感"],
    "悲伤": ["伤感", "忧伤", "emo", "哭", "失恋", "离别"],
    "紧张": ["悬疑", "紧张", "惊悚", "恐怖"],
    "激昂": ["励志", "震撼", "史诗", "运动", "战斗"],
    "温馨": ["温暖", "治愈", "温柔", "甜蜜", "浪漫"],
    "搞笑": ["搞笑", "沙雕", "鬼畜", "魔性", "搞笑BGM"],
}


def infer_emotion(title: str, tags: str = "") -> str:
    text = (title + " " + tags).lower()
    for emo, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return emo
    return "愉快"


def get_audio_info(filepath: str) -> dict:
    cmd = [
        "yt-dlp", "--dump-json", "--no-download",
        "--print", "duration", "--print", "title",
        filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {}
    except Exception:
        return {}


def download_one(url: str, output_dir: str, cookies: str = None) -> dict | None:
    os.makedirs(output_dir, exist_ok=True)

    filename = f"bgm_{uuid.uuid4().hex[:8]}"

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "192K",
        "-o", os.path.join(output_dir, f"{filename}.%(ext)s"),
        "--no-playlist",
        "--print", "title",
        "--print", "duration",
    ]

    if cookies and os.path.exists(cookies):
        cmd.extend(["--cookies", cookies])

    cmd.append(url)

    print(f"  下载中: {url[:60]}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            print(f"  失败: {result.stderr[:200]}")
            return None

        lines = result.stdout.strip().split("\n")
        title = lines[0] if lines else filename
        duration_str = lines[1] if len(lines) > 1 else "0"

        mp3_path = os.path.join(output_dir, f"{filename}.mp3")
        if not os.path.exists(mp3_path):
            for f in os.listdir(output_dir):
                if f.startswith(filename) and f.endswith(".mp3"):
                    mp3_path = os.path.join(output_dir, f)
                    break

        if not os.path.exists(mp3_path):
            print(f"  MP3文件未找到")
            return None

        try:
            duration = int(float(duration_str))
        except (ValueError, IndexError):
            duration = 180

        return {
            "filename": filename,
            "title": title,
            "duration": duration,
            "mp3_path": mp3_path,
        }
    except subprocess.TimeoutExpired:
        print(f"  超时 (180s)")
        return None
    except Exception as e:
        print(f"  错误: {e}")
        return None


def build_bgm_entry(info: dict, emotion: str = None) -> dict:
    title = info["title"]
    duration = info["duration"]
    if not emotion:
        emotion = infer_emotion(title)

    bpm = 100
    beat_interval = 60.0 / bpm
    beats = []
    t = 0.0
    while t <= duration:
        beats.append(round(t, 2))
        t += beat_interval

    intro_end = duration * 0.15
    buildup_end = duration * 0.35
    climax_end = duration * 0.80

    energy_profiles = {
        "平静": [0.2, 0.3, 0.3, 0.4, 0.3, 0.2, 0.2],
        "愉快": [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3],
        "兴奋": [0.4, 0.7, 0.9, 1.0, 0.9, 0.6, 0.3],
        "悲伤": [0.3, 0.2, 0.3, 0.4, 0.5, 0.3, 0.2],
        "紧张": [0.5, 0.7, 0.8, 0.9, 0.8, 0.6, 0.4],
        "激昂": [0.4, 0.7, 0.9, 1.0, 0.8, 0.5, 0.3],
        "温馨": [0.2, 0.3, 0.4, 0.5, 0.5, 0.3, 0.2],
        "搞笑": [0.3, 0.6, 0.8, 0.9, 0.7, 0.5, 0.3],
    }

    return {
        "id": info["filename"],
        "title": title,
        "artist": "抖音热门",
        "emotion": emotion,
        "tempo": bpm,
        "beat_positions": beats,
        "structure": {
            "intro": [0, round(intro_end, 1)],
            "build_up": [round(intro_end, 1), round(buildup_end, 1)],
            "climax": [round(buildup_end, 1), round(climax_end, 1)],
            "outro": [round(climax_end, 1), float(duration)],
        },
        "style_tags": ["抖音", "热门"],
        "energy_curve": energy_profiles.get(emotion, [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3]),
        "duration": duration,
        "preview_url": f"/audio/{info['filename']}.mp3",
    }


def load_library() -> list:
    if os.path.exists(LIBRARY_PATH):
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("bgm_list", [])
    return []


def save_library(bgm_list: list):
    os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump({"bgm_list": bgm_list}, f, ensure_ascii=False, indent=2)


def get_mp3_duration(filepath: str) -> int:
    try:
        from mutagen.mp3 import MP3
        audio = MP3(filepath)
        return int(audio.info.length)
    except Exception:
        pass
    try:
        import struct, wave
        with wave.open(filepath, 'r') as w:
            return int(w.getnframes() / w.getframerate())
    except Exception:
        pass
    return 180


def import_from_dir(search_dir: str):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    library = load_library()
    existing_titles = {item["title"] for item in library}

    audio_exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
    files = []
    for root, dirs, fnames in os.walk(search_dir):
        for fname in fnames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in audio_exts:
                files.append(os.path.join(root, fname))

    if not files:
        print(f"未找到音频文件: {search_dir}")
        return

    print(f"找到 {len(files)} 个音频文件\n")
    os.makedirs(AUDIO_DIR, exist_ok=True)

    import shutil
    success = 0
    skip = 0

    for i, filepath in enumerate(files, 1):
        basename = os.path.basename(filepath)
        title = os.path.splitext(basename)[0]
        ext = os.path.splitext(basename)[1]

        if title in existing_titles:
            print(f"[{i}/{len(files)}] 跳过 (已存在): {title}")
            skip += 1
            continue

        print(f"[{i}/{len(files)}] 导入: {title}")

        filename = f"bgm_{uuid.uuid4().hex[:8]}"
        dest = os.path.join(AUDIO_DIR, f"{filename}{ext}")
        shutil.copy2(filepath, dest)

        # Convert to mp3 if not already
        if ext.lower() != ".mp3":
            mp3_path = os.path.join(AUDIO_DIR, f"{filename}.mp3")
            try:
                subprocess.run(
                    ["ffmpeg", "-i", dest, "-codec:a", "libmp3lame", "-q:a", "2", mp3_path, "-y"],
                    capture_output=True, timeout=60
                )
                os.remove(dest)
                dest = mp3_path
            except Exception:
                pass

        duration = get_mp3_duration(dest)
        emotion = infer_emotion(title)

        entry = build_bgm_entry({
            "filename": filename,
            "title": title,
            "duration": duration,
        }, emotion=emotion)
        entry["preview_url"] = f"/audio/{filename}{ext}"

        library.append(entry)
        existing_titles.add(title)
        success += 1
        print(f"  完成: {title} ({duration}s, {emotion})")

    save_library(library)
    print(f"\n导入完成! 新增: {success}, 跳过: {skip}, 库总数: {len(library)}")


def main():
    parser = argparse.ArgumentParser(description="批量导入歌曲到本地BGM库")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--import-dir", help="从文件夹批量导入已有MP3/音频文件")
    group.add_argument("--url", help="单个音乐URL")
    group.add_argument("--urls", help="URL列表文件 (每行一个)")
    group.add_argument("--search", help="歌名搜索列表文件 (每行一首)")
    parser.add_argument("--cookies", help="Cookie文件路径 (抖音需要)")
    args = parser.parse_args()

    if args.import_dir:
        import_from_dir(args.import_dir)
        return

    urls = []
    if args.url:
        urls = [args.url]
    elif args.urls:
        with open(args.urls, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif args.search:
        with open(args.search, "r", encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        for name in names:
            urls.append(f"ytsearch:{name}")

    print(f"共 {len(urls)} 首歌待下载\n")

    library = load_library()
    existing_ids = {item["id"] for item in library}

    success = 0
    fail = 0

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url[:80]}")

        info = download_one(url, AUDIO_DIR, cookies=args.cookies)
        if not info:
            fail += 1
            continue

        if info["filename"] in existing_ids:
            print(f"  跳过 (已存在)")
            continue

        entry = build_bgm_entry(info)
        library.append(entry)
        existing_ids.add(info["filename"])
        success += 1
        print(f"  完成: {info['title']} ({info['duration']}s)")

    save_library(library)
    print(f"\n完成! 成功: {success}, 失败: {fail}, 库总数: {len(library)}")


if __name__ == "__main__":
    main()
