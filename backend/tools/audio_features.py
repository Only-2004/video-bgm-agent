"""
用 librosa 提取 MP3 客观音频特征（BPM、能量曲线、高潮段、结构等）

情绪标签由 MiMo LLM 生成，librosa 只负责客观特征提取。

用法：
  python tools/audio_features.py              # 处理全部
  python tools/audio_features.py --limit 10   # 只处理前10首（测试用）
  python tools/audio_features.py --force       # 覆盖已有特征
"""

import argparse
import json
import os
import sys
import time

import librosa
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"


def extract_features(filepath):
    """提取单首 MP3 的全部音频特征"""
    try:
        y, sr = librosa.load(filepath, sr=22050, duration=120)
    except Exception as e:
        print(f"    加载失败: {e}")
        return None

    duration = librosa.get_duration(y=y, sr=sr)

    # --- 基础特征 ---
    tempo_bt, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo_bt, np.ndarray):
        tempo_bt = float(tempo_bt[0]) if len(tempo_bt) > 0 else 100.0
    else:
        tempo_bt = float(tempo_bt) if tempo_bt else 100.0

    # 交叉验证：onset envelope 估算 BPM，取较大值避免半拍误检
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_oe = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    if isinstance(tempo_oe, np.ndarray):
        tempo_oe = float(tempo_oe[0]) if len(tempo_oe) > 0 else tempo_bt
    else:
        tempo_oe = float(tempo_oe) if tempo_oe else tempo_bt

    tempo = max(tempo_bt, tempo_oe)

    # --- 频谱特征 ---
    spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
    spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
    spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
    zero_crossing = np.mean(librosa.feature.zero_crossing_rate(y))

    # --- MFCC ---
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_means = np.mean(mfcc, axis=1).tolist()
    mfcc_stds = np.std(mfcc, axis=1).tolist()

    # --- 色度特征（调性/和声） ---
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_means = np.mean(chroma, axis=1).tolist()

    # 判断大调/小调（简化：比较 I 度和 iii 度的能量）
    major_score = chroma_means[0] + chroma_means[4] + chroma_means[7]  # C, E, G
    minor_score = chroma_means[0] + chroma_means[3] + chroma_means[7]  # C, Eb, G
    is_major = major_score > minor_score

    # --- 能量特征 ---
    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    energy_cv = energy_std / (energy_mean + 1e-6)  # 变异系数：能量波动程度

    # 前后能量比：判断是"渐强型"还是"前重后轻"
    third = len(rms) // 3
    energy_front = float(np.mean(rms[:third]))
    energy_back = float(np.mean(rms[2*third:]))
    energy_ratio = energy_back / (energy_front + 1e-6)  # >1 渐强，<1 渐弱

    # --- 节奏密度（onset strength） ---
    onset_density = float(np.mean(onset_env))

    # --- 段落分析（分7段，对应 intro/build/climax/outro 等） ---
    n_segments = 7
    segment_len = len(y) // n_segments
    energy_curve = []
    tempo_segments = []

    for i in range(n_segments):
        start = i * segment_len
        end = min(start + segment_len, len(y))
        seg = y[start:end]
        if len(seg) == 0:
            energy_curve.append(0.3)
            tempo_segments.append(80)
            continue
        seg_rms = float(np.mean(librosa.feature.rms(y=seg)))
        energy_curve.append(min(1.0, seg_rms * 3))  # 归一化到 0-1
        try:
            seg_tempo, _ = librosa.beat.beat_track(y=seg, sr=sr)
            if isinstance(seg_tempo, np.ndarray):
                seg_tempo = float(seg_tempo[0]) if len(seg_tempo) > 0 else 80.0
            tempo_segments.append(int(seg_tempo))
        except Exception:
            tempo_segments.append(80)

    # 平滑能量曲线
    energy_curve = smooth_curve(energy_curve)

    # --- beat positions ---
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    beat_times = [round(t, 2) for t in beat_times]

    # --- 强拍/弱拍分类 ---
    beat_details = classify_beats(onset_env, beat_frames, sr)

    # --- 高潮段检测 ---
    climax_segments = detect_climax_segments(rms, sr)

    # --- 音乐结构分段（agglomerative） ---
    music_segments = detect_music_segments(y, sr, n_segments=6)

    # --- 推荐起始位置 ---
    start_position = compute_start_position(music_segments, climax_segments, duration)

    # --- 结构分析（基于能量变化，作为 fallback） ---
    structure = build_structure_from_energy(energy_curve, duration)

    return {
        "duration": round(duration, 1),
        "tempo": int(round(tempo)),
        "energy_curve": [round(e, 3) for e in energy_curve],
        "beat_positions": beat_times,
        "beat_details": beat_details,
        "climax_segments": climax_segments,
        "music_segments": music_segments,
        "start_position_sec": round(start_position, 2),
        "structure": structure,
        "features": {
            "spectral_centroid": round(spectral_centroid, 1),
            "spectral_bandwidth": round(spectral_bandwidth, 1),
            "spectral_rolloff": round(spectral_rolloff, 1),
            "zero_crossing_rate": round(zero_crossing, 4),
            "energy_mean": round(energy_mean, 4),
            "energy_std": round(energy_std, 4),
            "energy_cv": round(energy_cv, 4),  # 变异系数
            "energy_ratio": round(energy_ratio, 4),  # 前后能量比
            "onset_density": round(onset_density, 2),
            "is_major": is_major,
            "mfcc_means": [round(m, 2) for m in mfcc_means],
            "tempo_segments": tempo_segments,
        },
    }


def smooth_curve(curve, window=3):
    """简单移动平均平滑"""
    result = []
    for i in range(len(curve)):
        start = max(0, i - window // 2)
        end = min(len(curve), i + window // 2 + 1)
        result.append(round(np.mean(curve[start:end]), 3))
    return result


def detect_climax_segments(rms, sr, hop_length=512, top_percent=15, min_duration=0.3):
    """
    基于 RMS energy 检测高潮段：能量 top 15% 且连续超过 0.3s 的区域

    返回：[{"start": 35.2, "end": 52.1, "energy": 0.85}, ...]
    """
    if len(rms) == 0:
        return []

    # 计算阈值：top 15% 的 RMS
    threshold = np.percentile(rms, 100 - top_percent)

    # 找到超过阈值的帧
    above = rms > threshold
    min_frames = int(min_duration * sr / hop_length)

    segments = []
    in_segment = False
    seg_start = 0

    for i, val in enumerate(above):
        if val and not in_segment:
            in_segment = True
            seg_start = i
        elif not val and in_segment:
            if i - seg_start >= min_frames:
                start_sec = round(librosa.frames_to_time(seg_start, sr=sr, hop_length=hop_length), 2)
                end_sec = round(librosa.frames_to_time(i, sr=sr, hop_length=hop_length), 2)
                seg_energy = round(float(np.mean(rms[seg_start:i])), 3)
                segments.append({"start": start_sec, "end": end_sec, "energy": seg_energy})
            in_segment = False

    # 处理末尾
    if in_segment and len(above) - seg_start >= min_frames:
        start_sec = round(librosa.frames_to_time(seg_start, sr=sr, hop_length=hop_length), 2)
        end_sec = round(librosa.frames_to_time(len(above), sr=sr, hop_length=hop_length), 2)
        seg_energy = round(float(np.mean(rms[seg_start:])), 3)
        segments.append({"start": start_sec, "end": end_sec, "energy": seg_energy})

    # 合并间距 < 0.5s 的相邻段
    if len(segments) <= 1:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        if seg["start"] - merged[-1]["end"] < 0.5:
            merged[-1]["end"] = seg["end"]
            merged[-1]["energy"] = round(max(merged[-1]["energy"], seg["energy"]), 3)
        else:
            merged.append(seg)
    return merged


def classify_beats(onset_env, beat_frames, sr, hop_length=512):
    """
    基于 onset_strength 分类强拍/弱拍

    强拍：onset_strength > mean + std
    弱拍：onset_strength < mean - std
    中等：介于两者之间

    返回：[{"time": 1.2, "strength": 0.8, "type": "strong"}, ...]
    """
    if len(onset_env) == 0 or len(beat_frames) == 0:
        return []

    mean_val = np.mean(onset_env)
    std_val = np.std(onset_env)

    beat_details = []
    for frame in beat_frames:
        if frame >= len(onset_env):
            continue
        strength = float(onset_env[frame])
        if strength > mean_val + std_val:
            beat_type = "strong"
        elif strength < mean_val - std_val:
            beat_type = "weak"
        else:
            beat_type = "medium"
        time_sec = round(librosa.frames_to_time(frame, sr=sr, hop_length=hop_length), 2)
        beat_details.append({"time": time_sec, "strength": round(strength, 3), "type": beat_type})

    return beat_details


def detect_music_segments(y, sr, n_segments=6):
    """
    用 librosa.segment.agglomerative 基于色度特征做结构分段

    返回：[{"start": 0, "end": 15.2, "type": "intro", "energy": 0.3}, ...]
    """
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        bound_frames = librosa.segment.agglomerative(chroma, n_segments)
        bound_times = librosa.frames_to_time(bound_frames, sr=sr).tolist()
        duration = librosa.get_duration(y=y, sr=sr)
        bound_times.append(duration)
        bound_times = sorted(set(round(t, 2) for t in bound_times))

        # 标注每段类型
        segments = []
        for i in range(len(bound_times) - 1):
            seg_start = bound_times[i]
            seg_end = bound_times[i + 1]
            seg_start_frame = librosa.time_to_frames(seg_start, sr=sr)
            seg_end_frame = librosa.time_to_frames(seg_end, sr=sr)
            seg_rms = float(np.mean(librosa.feature.rms(y=y)[0][seg_start_frame:seg_end_frame]))

            # 根据位置和能量判断段落类型
            position_ratio = seg_start / duration
            if position_ratio < 0.12:
                seg_type = "intro"
            elif position_ratio > 0.82:
                seg_type = "outro"
            elif seg_rms > 0.15:
                seg_type = "climax"
            elif position_ratio < 0.4:
                seg_type = "build_up"
            else:
                seg_type = "verse"

            segments.append({
                "start": round(seg_start, 2),
                "end": round(seg_end, 2),
                "type": seg_type,
                "energy": round(min(1.0, seg_rms * 3), 3),
            })

        return segments
    except Exception:
        return []


def compute_start_position(segments, climax_segments, duration):
    """
    根据结构分段和高潮检测计算推荐起始位置

    优先级：climax 起点 > intro 结束点 > verse 起点
    """
    # 优先从 climax 段开始
    if climax_segments:
        return climax_segments[0]["start"]

    # 找到 intro 结束点
    for seg in segments:
        if seg["type"] == "intro":
            return seg["end"]

    # 找到第一个非 intro 段的起点
    for seg in segments:
        if seg["type"] not in ("intro",):
            return seg["start"]

    return 0


def build_structure_from_energy(energy_curve, duration):
    """从能量曲线推断结构（保留作为 fallback）"""
    if len(energy_curve) < 7:
        return {
            "intro": [0, round(duration * 0.15, 1)],
            "build_up": [round(duration * 0.15, 1), round(duration * 0.35, 1)],
            "climax": [round(duration * 0.35, 1), round(duration * 0.80, 1)],
            "outro": [round(duration * 0.80, 1), float(duration)],
        }

    peak_idx = np.argmax(energy_curve[2:5]) + 2
    climax_start = round(duration * (peak_idx - 1) / 7, 1)
    climax_end = round(duration * (peak_idx + 1) / 7, 1)

    return {
        "intro": [0, round(duration * 0.15, 1)],
        "build_up": [round(duration * 0.15, 1), climax_start],
        "climax": [climax_start, climax_end],
        "outro": [round(duration * 0.80, 1), float(duration)],
    }


def load_library():
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_library(data):
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="用 librosa 提取 MP3 音频特征并更新 BGM 库")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 首 (0=全部)")
    parser.add_argument("--force", action="store_true", help="覆盖已有音频特征")
    parser.add_argument("--dry-run", action="store_true", help="只分析不写入")
    args = parser.parse_args()

    library_data = load_library()
    tracks = library_data.get("bgm_list", [])

    if args.limit > 0:
        tracks = tracks[:args.limit]

    print("=" * 55)
    print("librosa 音频特征提取工具")
    print(f"待处理: {len(tracks)} 首 | 音频目录: {AUDIO_DIR}")
    print("=" * 55)

    success = 0
    fail = 0
    skip = 0
    start_time = time.time()

    for i, track in enumerate(tracks):
        track_id = track.get("id", "")
        audio_file = track.get("audio_file", "")
        if audio_file:
            filepath = os.path.join(AUDIO_DIR, audio_file)
        else:
            filepath = os.path.join(AUDIO_DIR, f"{track_id}.mp3")

        if not os.path.exists(filepath):
            fail += 1
            continue

        # 跳过已有特征
        if not args.force and "features" in track and track.get("rhythm_tag", {}).get("bpm", 0) > 0:
            skip += 1
            continue

        title = track.get("title", "?")[:30]
        print(f"[{i+1}/{len(tracks)}] {title}...", end=" ", flush=True)

        features = extract_features(filepath)
        if not features:
            fail += 1
            print("失败")
            continue

        # 更新 track 数据（只更新客观特征，情绪标签由 MiMo 生成）
        track["tempo"] = features["tempo"]
        track["energy_curve"] = features["energy_curve"]
        track["beat_positions"] = features["beat_positions"]
        track["beat_details"] = features["beat_details"]
        track["climax_segments"] = features["climax_segments"]
        track["music_segments"] = features["music_segments"]
        track["structure"] = features["structure"]
        track["duration"] = int(features["duration"])
        track["audio_features"] = features["features"]

        # 自动填充 start_position_sec 到 scene_tag
        if "scene_tag" not in track:
            track["scene_tag"] = {}
        track["scene_tag"]["start_position_sec"] = features["start_position_sec"]

        success += 1
        climax_info = ""
        if features["climax_segments"]:
            c = features["climax_segments"][0]
            climax_info = f", 高潮{c['start']}-{c['end']}s"
        print(f"OK ({features['tempo']}BPM{climax_info}, 起始{features['start_position_sec']}s)")

    elapsed = time.time() - start_time

    if not args.dry_run and success > 0:
        save_library(library_data)
        print(f"\n已保存到 {LIBRARY_PATH}")

    print(f"\n{'=' * 55}")
    print(f"完成! 成功: {success} | 跳过: {skip} | 失败: {fail}")
    print(f"耗时: {elapsed:.1f}s ({elapsed/max(success,1):.1f}s/首)")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
