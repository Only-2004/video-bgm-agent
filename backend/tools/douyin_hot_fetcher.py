"""
从YouTube搜索下载抖音热歌到本地BGM库

原理：抖音热歌在YouTube上有大量搬运，通过ytsearch搜索下载MP3
所有文件存储在D盘，不占C盘空间

用法：
  python tools/douyin_hot_fetcher.py
  python tools/douyin_hot_fetcher.py --num 50
"""

import argparse
import json
import os
import random
import subprocess
import sys
import uuid

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"

# 抖音热歌列表（持续更新）
DOUYIN_HOT_SONGS = [
    # 2025-2026 抖音热门
    "孤勇者 陈奕迅",
    "错位时空 艾辰",
    "踏山河 是七叔呢",
    "白月光与朱砂痣 大籽",
    "云与海 阿YueYue",
    "半生雪 是七叔呢",
    "星辰大海 黄霄雲",
    "踏雪 等什么君",
    "千千万万 深海鱼子酱",
    "漠河舞厅 柳爽",
    "可可托海的牧羊人 王琪",
    "往后余生 马良",
    "你的答案 阿冗",
    "飞鸟和蝉 任然",
    "一路生花 温奕心",
    "少年 刘大壮",
    "微微 傅如乔",
    "想见你想见你想见你 八三夭",
    "下雨天 薛之谦",
    "阿拉斯加海湾 菲道尔",
    # 经典抖音热歌
    "学猫叫 小潘潘",
    "纸短情长 烟把儿乐队",
    "体面 于文文",
    "说散就散 袁娅维",
    "往后余生 马良",
    "可能否 木小雅",
    "我们不一样 大壮",
    "往后余生 马良",
    "起风了 买辣椒也用券",
    "芒种 音阙诗听",
    "出山 花粥",
    "绿色 陈雪凝",
    "世间美好与你环环相扣 柏松",
    "下山 要不要买菜",
    "大鱼 周深",
    "知否知否 郁可唯",
    "芒种 音阙诗听",
    "左手指月 萨顶顶",
    "海底 一支榴莲",
    "关山酒 等什么君",
    "离人愁 李袁杰",
    "红昭愿 音阙诗听",
    "琵琶行 奇然",
    "生僻字 陈柯宇",
    "浪子闲话 花僮",
    "醉梦前尘 林距离",
    "桥边姑娘 海伦",
    "大田后生仔 林启得",
    "一路向北 李荣浩",
    "消愁 毛不易",
    "像我这样的人 毛不易",
    "平凡之路 朴树",
    "成都 赵雷",
    "南山南 马頔",
    "董小姐 宋冬野",
    "斑马斑马 宋冬野",
    "理想三旬 陈鸿宇",
    "安和桥 宋冬野",
    "画 赵雷",
    "三十岁的女人 赵雷",
    "无法长大 赵雷",
    "九月 朴树",
    "那些花儿 朴树",
    "白桦林 朴树",
    "生如许巍",
    "蓝莲花 许巍",
    "曾经的你 许巍",
    "故乡 许巍",
    "礼物 许巍",
    "时光 许巍",
    "旅行 许巍",
    "执着 许巍",
    "温暖 许巍",
    "两天 许巍",
    "我思念的城市 许巍",
    "树 许巍",
    "青鸟 许巍",
    "悠远的天空 许巍",
    "那一年 许巍",
    "简单爱 周杰伦",
    "晴天 周杰伦",
    "七里香 周杰伦",
    "稻香 周杰伦",
    "告白气球 周杰伦",
    "等你下课 周杰伦",
    "说好不哭 周杰伦",
    "Mojito 周杰伦",
    "本草纲目 周杰伦",
    "双截棍 周杰伦",
    "夜曲 周杰伦",
    "以父之名 周杰伦",
    "东风破 周杰伦",
    "发如雪 周杰伦",
    "千里之外 周杰伦",
    "菊花台 周杰伦",
    "青花瓷 周杰伦",
    "烟花易冷 周杰伦",
    "红尘客栈 周杰伦",
    "告白气球 周杰伦",
    "不爱我就拉倒 周杰伦",
    "学猫叫 小潘潘 小峰峰",
    "往后余生 马良",
    "可能否 木小雅",
    "纸短情长 烟把儿乐队",
    "我们不一样 大壮",
    "起风了 买辣椒也用券",
    "芒种 音阙诗听",
    "出山 花粥",
    "绿色 陈雪凝",
    "世间美好与你环环相扣 柏松",
    "下山 要不要买菜",
    "大鱼 周深",
    "知否知否 郁可唯",
    "左手指月 萨顶顶",
    "海底 一支榴莲",
    "关山酒 等什么君",
    "离人愁 李袁杰",
    "红昭愿 音阙诗听",
    "琵琶行 奇然",
    "生僻字 陈柯宇",
    "浪子闲话 花僮",
    "醉梦前尘 林距离",
    "桥边姑娘 海伦",
    "大田后生仔 林启得",
    "一路向北 李荣浩",
    "消愁 毛不易",
    "像我这样的人 毛不易",
    "平凡之路 朴树",
    "成都 赵雷",
    "南山南 马頔",
    "董小姐 宋冬野",
    "斑马斑马 宋冬野",
    "理想三旬 陈鸿宇",
    "安和桥 宋冬野",
    "画 赵雷",
    "三十岁的女人 赵雷",
    "无法长大 赵雷",
    "九月 朴树",
    "那些花儿 朴树",
    "白桦林 朴树",
    "生如许巍",
    "蓝莲花 许巍",
    "曾经的你 许巍",
    "故乡 许巍",
    "礼物 许巍",
    "时光 许巍",
    "旅行 许巍",
    "执着 许巍",
    "温暖 许巍",
    "两天 许巍",
    "我思念的城市 许巍",
    "树 许巍",
    "青鸟 许巍",
    "悠远的天空 许巍",
    "那一年 许巍",
]

# 情绪推断（从歌名/歌手推断）
EMOTION_KEYWORDS = {
    "平静": ["舒缓", "轻音乐", "钢琴", "安静", "放松", "冥想", "画", "桥边", "斑马", "董小姐", "安和桥", "理想三旬", "九月", "那些花儿", "白桦林", "故乡", "时光", "旅行", "温暖", "悠远", "简单", "晴天"],
    "愉快": ["欢快", "开心", "阳光", "快乐", "活泼", "猫", "七里香", "稻香", "告白", "Mojito", "本草纲目"],
    "兴奋": ["嗨", "DJ", "蹦迪", "电音", "燃", "热血", "动感", "双截棍", "红昭愿", "芒种", "下山"],
    "悲伤": ["伤感", "忧伤", "emo", "哭", "失恋", "离别", "海底", "离人愁", "体面", "说散就散", "知否"],
    "紧张": ["悬疑", "紧张", "惊悚", "恐怖", "左手指月"],
    "激昂": ["励志", "震撼", "史诗", "运动", "战斗", "孤勇者", "星辰大海", "一路生花", "少年", "答案"],
    "温馨": ["温暖", "治愈", "温柔", "甜蜜", "浪漫", "往后余生", "成都", "南山南", "消愁", "平凡之路"],
    "搞笑": ["搞笑", "沙雕", "鬼畜", "魔性", "学猫叫", "生僻字"],
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


def infer_emotion(song_query):
    for emo, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in song_query:
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


def download_from_youtube(query, output_dir):
    """用yt-dlp从YouTube搜索下载MP3"""
    filename = f"bgm_{uuid.uuid4().hex[:8]}"
    output_path = os.path.join(output_dir, f"{filename}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "192K",
        "-o", output_path,
        "--no-playlist",
        "--match-filter", "duration<600 & duration>30",
        "--print", "title",
        "--print", "duration",
        f"ytsearch1:{query}",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        title = lines[0] if lines else query
        duration_str = lines[1] if len(lines) > 1 else "0"

        # 找到下载的文件
        mp3_path = os.path.join(output_dir, f"{filename}.mp3")
        if not os.path.exists(mp3_path):
            for f in os.listdir(output_dir):
                if f.startswith(filename) and f.endswith(".mp3"):
                    mp3_path = os.path.join(output_dir, f)
                    break

        if not os.path.exists(mp3_path):
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
        return None
    except Exception as e:
        return None


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
    parser = argparse.ArgumentParser(description="下载抖音热歌到本地BGM库")
    parser.add_argument("--num", type=int, default=100, help="下载数量 (默认100)")
    args = parser.parse_args()

    os.makedirs(AUDIO_DIR, exist_ok=True)
    library = load_library()
    existing_titles = {item.get("title", "") for item in library}

    # 去重
    songs = list(dict.fromkeys(DOUYIN_HOT_SONGS))
    songs = songs[:args.num]

    success = 0
    fail = 0
    skip = 0

    print(f"=" * 50)
    print(f"抖音热歌下载工具 (via YouTube)")
    print(f"目标: {len(songs)} 首")
    print(f"存储: {AUDIO_DIR}")
    print(f"=" * 50)

    for i, query in enumerate(songs):
        if success >= args.num:
            break

        # 检查是否已存在
        title_part = query.split()[0] if query else ""
        if any(title_part in t for t in existing_titles if t):
            skip += 1
            continue

        print(f"[{success+1}/{args.num}] {query}...", end=" ", flush=True)

        result = download_from_youtube(query, AUDIO_DIR)
        if not result:
            fail += 1
            print("失败")
            continue

        emotion = infer_emotion(query)
        bpm = random.randint(80, 130)
        duration = result["duration"]

        entry = {
            "id": result["filename"],
            "title": result["title"],
            "artist": query.split()[-1] if len(query.split()) > 1 else "抖音热歌",
            "emotion": emotion,
            "tempo": bpm,
            "beat_positions": estimate_beats(bpm, duration),
            "structure": build_structure(duration),
            "style_tags": ["抖音", "热歌", "华语"],
            "energy_curve": ENERGY_CURVES.get(emotion, [0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3]),
            "duration": duration,
            "preview_url": f"/audio/{result['filename']}.mp3",
            "source": "douyin",
        }

        library.append(entry)
        existing_titles.add(result["title"])
        success += 1
        print(f"OK ({duration}s, {emotion})")

    save_library(library)
    print(f"\n{'=' * 50}")
    print(f"完成! 成功: {success} | 跳过: {skip} | 失败: {fail}")
    print(f"库总数: {len(library)} 首")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
