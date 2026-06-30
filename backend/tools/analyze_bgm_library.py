"""
分析音乐库中所有音频文件，用 librosa 提取真实特征并推断情绪

用法：
  python tools/analyze_bgm_library.py              # 分析所有
  python tools/analyze_bgm_library.py --single FILE  # 分析单首
  python tools/analyze_bgm_library.py --force         # 强制重新分析
"""

import argparse
import json
import os
import sys
import numpy as np
import librosa

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"

# 8维情绪维度
EMOTION_DIMS = ["平静", "愉快", "兴奋", "悲伤", "紧张", "激昂", "温馨", "搞笑"]

# 情绪原型特征（归一化后的典型值）
EMOTION_PROTOTYPES = {
    "平静": {"energy": 0.2, "tempo": 0.25, "brightness": 0.3, "onset": 0.15, "onset_var": 0.15, "zcr": 0.25},
    "愉快": {"energy": 0.5, "tempo": 0.55, "brightness": 0.5, "onset": 0.4, "onset_var": 0.3, "zcr": 0.45},
    "兴奋": {"energy": 0.75, "tempo": 0.75, "brightness": 0.55, "onset": 0.65, "onset_var": 0.4, "zcr": 0.5},
    "悲伤": {"energy": 0.12, "tempo": 0.15, "brightness": 0.15, "onset": 0.08, "onset_var": 0.08, "zcr": 0.1},
    "紧张": {"energy": 0.5, "tempo": 0.5, "brightness": 0.5, "onset": 0.5, "onset_var": 0.7, "zcr": 0.4},
    "激昂": {"energy": 0.7, "tempo": 0.65, "brightness": 0.5, "onset": 0.6, "onset_var": 0.35, "zcr": 0.4},
    "温馨": {"energy": 0.3, "tempo": 0.35, "brightness": 0.45, "onset": 0.2, "onset_var": 0.15, "zcr": 0.35},
    "搞笑": {"energy": 0.45, "tempo": 0.5, "brightness": 0.55, "onset": 0.45, "onset_var": 0.6, "zcr": 0.45},
}


def extract_features(audio_path: str) -> dict:
    """从音频文件提取特征"""
    y, sr = librosa.load(audio_path, sr=22050, duration=90)
    duration = librosa.get_duration(y=y, sr=sr)

    # BPM
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0]) if len(tempo) > 0 else 100.0

    # RMS 能量
    rms = librosa.feature.rms(y=y)[0]
    avg_rms = float(np.mean(rms))

    # 频谱质心（亮度）
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    avg_centroid = float(np.mean(centroid))

    # 零交叉率
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    avg_zcr = float(np.mean(zcr))

    # onset 强度（节奏感）
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_mean = float(np.mean(onset_env))
    onset_std = float(np.std(onset_env))

    # 能量曲线（7段）
    seg_len = len(y) // 7
    energy_curve = []
    for i in range(7):
        seg = y[i * seg_len:(i + 1) * seg_len]
        if len(seg) > 0:
            energy_curve.append(round(float(np.mean(librosa.feature.rms(y=seg))), 4))
        else:
            energy_curve.append(0.0)

    # 鼓点时间
    beat_frames = librosa.beat.beat_track(y=y, sr=sr)[1]
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    return {
        "duration": round(duration, 1),
        "tempo": round(tempo, 1),
        "avg_rms": avg_rms,
        "avg_centroid": avg_centroid,
        "avg_zcr": avg_zcr,
        "onset_mean": onset_mean,
        "onset_std": onset_std,
        "energy_curve": energy_curve,
        "beat_times": [round(b, 2) for b in beat_times],
    }


def normalize_feature(value, min_val, max_val):
    """归一化到 0-1"""
    if max_val <= min_val:
        return 0.5
    return max(0, min(1, (value - min_val) / (max_val - min_val)))


def compute_emotion_vector(features: dict) -> list:
    """
    根据音频特征计算 8 维情绪向量

    核心逻辑：计算每个特征与每种情绪原型的相似度，加权合并
    """
    # 归一化特征（范围覆盖实际音频分布）
    norm_energy = normalize_feature(features["avg_rms"], 0.02, 0.25)
    norm_tempo = normalize_feature(features["tempo"], 60, 180)
    norm_brightness = normalize_feature(features["avg_centroid"], 500, 4000)
    norm_onset = normalize_feature(features["onset_mean"], 0.3, 4.0)
    norm_onset_var = normalize_feature(features["onset_std"], 0.3, 3.5)
    norm_zcr = normalize_feature(features["avg_zcr"], 0.01, 0.12)

    # 能量曲线特征：是否有 build-up
    curve = features["energy_curve"]
    if len(curve) >= 4:
        first_half = np.mean(curve[:3])
        second_half = np.mean(curve[3:6])
        build_up = normalize_feature(second_half - first_half, -0.1, 0.15)
    else:
        build_up = 0.5

    # 提取的特征向量
    feat_vec = {
        "energy": norm_energy,
        "tempo": norm_tempo,
        "brightness": norm_brightness,
        "onset": norm_onset,
        "onset_var": norm_onset_var,
        "zcr": norm_zcr,
    }

    # 计算与每种情绪原型的距离（越小越相似）
    scores = {}
    weights = {"energy": 0.25, "tempo": 0.2, "brightness": 0.15, "onset": 0.2, "onset_var": 0.1, "zcr": 0.1}

    for emotion, proto in EMOTION_PROTOTYPES.items():
        dist = 0
        for key, weight in weights.items():
            dist += weight * abs(feat_vec[key] - proto[key])
        scores[emotion] = dist

    # 距离转相似度（softmax-like，温度越低越尖锐）
    min_dist = min(scores.values())
    exp_scores = {e: np.exp(-(d - min_dist) * 15) for e, d in scores.items()}
    total = sum(exp_scores.values())
    emotion_vector = [round(exp_scores[dim] / total, 3) for dim in EMOTION_DIMS]

    # 主情绪
    primary_idx = np.argmax(emotion_vector)
    primary_emotion = EMOTION_DIMS[primary_idx]

    # === 规则修正：基于特征阈值覆盖原型匹配的误判 ===
    p_idx = EMOTION_DIMS.index

    # 极低能量 → 平静或悲伤
    if norm_energy < 0.12:
        emotion_vector[p_idx("平静")] += 0.2
        emotion_vector[p_idx("悲伤")] += 0.1
    elif norm_energy < 0.2 and norm_tempo < 0.3:
        emotion_vector[p_idx("平静")] += 0.15

    # 高能量 + 快节奏 → 兴奋
    if norm_energy > 0.6 and norm_tempo > 0.65:
        emotion_vector[p_idx("兴奋")] += 0.2

    # 高能量 + 中节奏 + 有 build-up → 激昂
    if norm_energy > 0.5 and 0.3 < norm_tempo < 0.7 and build_up > 0.55:
        emotion_vector[p_idx("激昂")] += 0.2

    # 高 onset_var → 紧张
    if norm_onset_var > 0.6 and norm_energy > 0.4:
        emotion_vector[p_idx("紧张")] += 0.15

    # 低 onset + 低能量 + 低 tempo → 悲伤
    if norm_onset < 0.15 and norm_energy < 0.2 and norm_tempo < 0.25:
        emotion_vector[p_idx("悲伤")] += 0.15

    # 中能量 + 中高亮度 + 低 onset_var → 温馨
    if 0.2 < norm_energy < 0.5 and norm_brightness > 0.4 and norm_onset_var < 0.25:
        emotion_vector[p_idx("温馨")] += 0.1

    # 中能量 + 高 onset_var → 搞笑
    if 0.3 < norm_energy < 0.6 and norm_onset_var > 0.5:
        emotion_vector[p_idx("搞笑")] += 0.1

    # 归一化
    total = sum(emotion_vector)
    if total > 0:
        emotion_vector = [round(v / total, 3) for v in emotion_vector]

    primary_idx = np.argmax(emotion_vector)
    primary_emotion = EMOTION_DIMS[primary_idx]

    return emotion_vector, primary_emotion


def classify_genre(features: dict, existing_genre: str) -> str:
    """根据特征推断类型（保留已有类型，但可修正）"""
    tempo = features["tempo"]
    energy = features["avg_rms"]
    brightness = features["avg_centroid"]

    # 如果已有明确类型且合理，保留
    if existing_genre and existing_genre != "unknown":
        return existing_genre

    # 否则根据特征推断
    if tempo > 140 and energy > 0.15:
        return "electronic"
    elif tempo < 80 and brightness < 2000:
        return "piano"
    elif energy > 0.2 and tempo > 120:
        return "rock"
    elif brightness > 3500:
        return "jazz"
    else:
        return "pop"


def analyze_single(audio_path: str, existing_track: dict = None) -> dict:
    """分析单首音频"""
    features = extract_features(audio_path)
    emotion_vector, primary_emotion = compute_emotion_vector(features)

    existing_genre = ""
    if existing_track:
        existing_genre = existing_track.get("genre", existing_track.get("type", ""))

    genre = classify_genre(features, existing_genre)

    # 构建结果
    result = {
        "tempo": features["tempo"],
        "emotion": primary_emotion,
        "emotion_vector": emotion_vector,
        "energy_curve": features["energy_curve"],
        "beat_positions": features["beat_times"],
        "structure": build_structure(features["duration"]),
        "duration": features["duration"],
        "genre": genre,
        # 保留原始特征用于调试
        "_features": {
            "avg_rms": round(features["avg_rms"], 4),
            "avg_centroid": round(features["avg_centroid"], 0),
            "avg_zcr": round(features["avg_zcr"], 4),
            "onset_mean": round(features["onset_mean"], 2),
            "onset_std": round(features["onset_std"], 2),
        },
    }

    return result


def build_structure(duration):
    return {
        "intro": [0, round(duration * 0.15, 1)],
        "build_up": [round(duration * 0.15, 1), round(duration * 0.35, 1)],
        "climax": [round(duration * 0.35, 1), round(duration * 0.80, 1)],
        "outro": [round(duration * 0.80, 1), float(duration)],
    }


def main():
    parser = argparse.ArgumentParser(description="分析音乐库音频特征")
    parser.add_argument("--single", help="只分析单个文件")
    parser.add_argument("--force", action="store_true", help="强制重新分析已有数据")
    args = parser.parse_args()

    # 加载库
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        library = json.load(f)

    bgm_list = library.get("bgm_list", [])

    if args.single:
        # 单文件分析
        result = analyze_single(args.single)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 批量分析
    analyzed = 0
    skipped = 0
    failed = 0

    for i, track in enumerate(bgm_list):
        track_id = track.get("id", "")
        audio_path = os.path.join(AUDIO_DIR, f"{track_id}.mp3")

        if not os.path.exists(audio_path):
            failed += 1
            continue

        # 跳过已分析的（除非 force）
        if not args.force and track.get("emotion_vector") and track.get("rhythm_tag", {}).get("bpm", 0) > 0:
            # 检查是否是旧的 hardcoded 数据（emotion_vector 全是相同模式）
            ev = track.get("emotion_vector", [])
            if len(ev) == 8 and not all(v == ev[0] for v in ev):
                skipped += 1
                continue

        try:
            result = analyze_single(audio_path, track)

            # 更新 track
            track["tempo"] = result["tempo"]
            track["emotion"] = result["emotion"]
            track["emotion_vector"] = result["emotion_vector"]
            track["energy_curve"] = result["energy_curve"]
            track["beat_positions"] = result["beat_positions"]
            track["structure"] = result["structure"]
            track["genre"] = result["genre"]
            track["_audio_features"] = result["_features"]

            analyzed += 1

            if (i + 1) % 10 == 0:
                print(f"  进度: {i + 1}/{len(bgm_list)} (分析: {analyzed}, 跳过: {skipped})")

        except Exception as e:
            failed += 1
            print(f"  失败: {track_id} - {e}")

    # 保存
    library["bgm_list"] = bgm_list
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)

    print(f"\n完成! 分析: {analyzed} | 跳过: {skipped} | 失败: {failed} | 总计: {len(bgm_list)}")

    # 情绪分布统计
    emotion_counts = {}
    for t in bgm_list:
        e = t.get("emotion", "unknown")
        emotion_counts[e] = emotion_counts.get(e, 0) + 1
    print(f"\n情绪分布:")
    for e, c in sorted(emotion_counts.items(), key=lambda x: -x[1]):
        print(f"  {e}: {c}")


if __name__ == "__main__":
    main()
