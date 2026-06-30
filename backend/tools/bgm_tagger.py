"""
BGM 标签分析工具 — librosa 提取特征 + MiMo LLM 分析标签

用法：
  python tools/bgm_tagger.py --limit 10          # 分析前10首
  python tools/bgm_tagger.py --force             # 强制重新分析
  python tools/bgm_tagger.py --id bgm_xxx        # 分析指定歌曲
"""

import argparse
import json
import os
import sys
import time

import requests
import numpy as np
import librosa

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AUDIO_DIR = "D:/video-bgm-data/audio"
LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "../prompts/bgm_analysis.txt")

# MiMo API（Anthropic 格式，纯文本分析）
MIMO_API_KEY = "sk-CpfQyqJEPcd5JPbDHEjG3MIlmbKoJwka"
MIMO_API_URL = "https://ai.iapp.dpdns.org"


def _detect_climax(rms, sr, hop_length=512, top_percent=15, min_duration=0.3):
    """基于 RMS energy 检测高潮段"""
    if len(rms) == 0:
        return {"start": 0, "end": 0}
    threshold = np.percentile(rms, 100 - top_percent)
    above = rms > threshold
    min_frames = int(min_duration * sr / hop_length)

    in_segment = False
    seg_start = 0
    best_start, best_end, best_energy = 0, 0, 0

    for i, val in enumerate(above):
        if val and not in_segment:
            in_segment = True
            seg_start = i
        elif not val and in_segment:
            if i - seg_start >= min_frames:
                seg_energy = float(np.mean(rms[seg_start:i]))
                if seg_energy > best_energy:
                    best_start = seg_start
                    best_end = i
                    best_energy = seg_energy
            in_segment = False

    if in_segment and len(above) - seg_start >= min_frames:
        seg_energy = float(np.mean(rms[seg_start:]))
        if seg_energy > best_energy:
            best_start = seg_start
            best_end = len(above)
            best_energy = seg_energy

    start_sec = round(librosa.frames_to_time(best_start, sr=sr, hop_length=hop_length), 2)
    end_sec = round(librosa.frames_to_time(best_end, sr=sr, hop_length=hop_length), 2)
    return {"start": start_sec, "end": end_sec}


def _infer_structure_bounds(energy_curve, duration):
    """从能量曲线推断结构边界时间点"""
    if len(energy_curve) < 7:
        return [0, round(duration * 0.15, 1), round(duration * 0.35, 1), round(duration * 0.80, 1), duration]

    peak_idx = np.argmax(energy_curve[2:5]) + 2
    climax_start = round(duration * (peak_idx - 1) / 7, 1)
    climax_end = round(duration * (peak_idx + 1) / 7, 1)

    return [0, round(duration * 0.15, 1), climax_start, climax_end, duration]


def _guess_instruments(centroid, zcr, energy, bpm):
    """基于频谱特征推断可能的配器"""
    hints = []
    if centroid > 3000:
        hints.extend(["合成器", "电子节拍"])
    elif centroid > 2000:
        hints.extend(["钢琴", "木吉他"])
    else:
        hints.extend(["贝斯", "低频合成器"])

    if zcr > 0.1:
        hints.append("鼓组")
    if energy > 0.15:
        hints.append("鼓组")
    if bpm > 130:
        hints.append("电子节拍")
    if centroid < 1500 and energy > 0.1:
        hints.append("808鼓机")

    # 去重保持顺序
    seen = set()
    result = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            result.append(h)
    return result if result else ["合成器", "鼓组"]


def extract_audio_features(mp3_path: str) -> dict:
    """用 librosa 提取音频特征，作为 LLM 分析的参考信息"""
    try:
        y, sr = librosa.load(mp3_path, sr=22050, duration=90)
    except Exception as e:
        print(f"  librosa 加载失败: {e}")
        return {}

    duration = librosa.get_duration(y=y, sr=sr)

    # BPM（交叉验证，避免半拍误检）
    tempo_bt, _ = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo_bt, np.ndarray):
        tempo_bt = float(tempo_bt[0]) if len(tempo_bt) > 0 else 100.0

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_oe = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    if isinstance(tempo_oe, np.ndarray):
        tempo_oe = float(tempo_oe[0]) if len(tempo_oe) > 0 else tempo_bt

    # 交叉验证：两个方法差距大时，取较小值（避免半拍误检）
    if tempo_bt > 0 and tempo_oe > 0:
        ratio = max(tempo_bt, tempo_oe) / min(tempo_bt, tempo_oe)
        if ratio > 1.5:
            tempo = min(tempo_bt, tempo_oe)
        else:
            tempo = (tempo_bt + tempo_oe) / 2
    else:
        tempo = max(tempo_bt, tempo_oe)

    # RMS 能量
    rms = librosa.feature.rms(y=y)[0]
    avg_rms = float(np.mean(rms))
    energy_std = float(np.std(rms))
    energy_cv = energy_std / (avg_rms + 1e-6)  # 变异系数

    # 前后能量比
    third = len(rms) // 3
    energy_front = float(np.mean(rms[:third]))
    energy_back = float(np.mean(rms[2 * third:]))
    energy_ratio = energy_back / (energy_front + 1e-6)

    # 频谱质心
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    avg_centroid = float(np.mean(centroid))

    # 零交叉率
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    avg_zcr = float(np.mean(zcr))

    # onset 密度
    onset_density = float(np.mean(onset_env))

    # 7段能量曲线（用于结构推断）
    n_segments = 7
    seg_len = len(y) // n_segments
    energy_curve = []
    for i in range(n_segments):
        start = i * seg_len
        end = min(start + seg_len, len(y))
        seg = y[start:end]
        if len(seg) == 0:
            energy_curve.append(0.3)
        else:
            seg_rms = float(np.mean(librosa.feature.rms(y=seg)))
            energy_curve.append(min(1.0, seg_rms * 3))

    # 高潮段检测
    climax_segments = _detect_climax(rms, sr)

    # 结构边界（intro/build/climax/outro）
    structure_bounds = _infer_structure_bounds(energy_curve, duration)

    # 配器推断（基于频谱特征）
    instruments = _guess_instruments(avg_centroid, avg_zcr, avg_rms, tempo)

    return {
        "duration": round(duration, 1),
        "bpm": round(tempo, 0),
        "energy_mean": round(avg_rms, 4),
        "energy_cv": round(energy_cv, 4),
        "energy_ratio": round(energy_ratio, 4),
        "spectral_centroid": round(avg_centroid, 0),
        "zcr": round(avg_zcr, 4),
        "onset_density": round(onset_density, 2),
        "climax_segments": climax_segments,
        "structure_bounds": structure_bounds,
        "instruments": instruments,
    }


def load_prompt() -> str:
    """加载分析 prompt 模板"""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()



def call_mimo_llm(prompt: str, retries: int = 5) -> str:
    """调用 MiMo API（Anthropic 格式，纯文本，不传音频）"""
    content = [{"type": "text", "text": prompt}]

    payload = {
        "model": "mimo-v2.5",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": content}],
    }

    for attempt in range(retries + 1):
        try:
            session = requests.Session()
            response = session.post(
                MIMO_API_URL,
                headers={
                    "x-api-key": MIMO_API_KEY,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                    "Connection": "close",
                },
                json=payload,
                timeout=60,
            )
            session.close()
            response.raise_for_status()

            result = response.json()
            for item in result.get("content", []):
                if item.get("type") == "text":
                    return item["text"]
            return ""
        except Exception as e:
            if attempt < retries:
                time.sleep(5)
                continue
            raise


def parse_llm_response(raw: str) -> dict:
    """从 LLM 响应中提取 JSON（支持 markdown 代码块包裹）"""
    # 去除 markdown 代码块
    import re
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)

    # 找第一个 { 和最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return {}


def analyze_single(mp3_path: str, track_info: dict, prompt_template: str) -> dict:
    """分析单首 BGM：librosa 提取客观特征 → MiMo 基于特征生成标签"""
    # 1. librosa 提取客观特征
    audio_features = extract_audio_features(mp3_path)
    if not audio_features:
        return {}

    # 2. 组装 prompt（所有字段来自 librosa，MiMo 不听音频）
    climax = audio_features.get("climax_segments", {"start": 0, "end": 0})
    bounds = audio_features.get("structure_bounds", [0, 10, 25, 50, 100])

    prompt = prompt_template.format(
        bpm=audio_features.get("bpm", 100),
        energy_mean=audio_features.get("energy_mean", 0.1),
        energy_cv=audio_features.get("energy_cv", 0.5),
        energy_ratio=audio_features.get("energy_ratio", 1.0),
        spectral_centroid=audio_features.get("spectral_centroid", 2000),
        zcr=audio_features.get("zcr", 0.05),
        onset_density=audio_features.get("onset_density", 1.0),
        climax_start=climax["start"],
        climax_end=climax["end"],
        structure_bounds=str(bounds),
        instruments=", ".join(audio_features.get("instruments", [])),
        duration=audio_features.get("duration", 120),
    )

    # 3. 调 MiMo（纯文本，不传音频）
    raw_response = call_mimo_llm(prompt)

    if not raw_response:
        print(f"  LLM 返回为空")
        return {}

    # 4. 解析 JSON
    tags = parse_llm_response(raw_response)
    if not tags:
        print(f"  JSON 解析失败，原始响应前200字: {raw_response[:200]}")
        return {}

    # 5. 合并 librosa 客观特征 + LLM 主观标签
    tags["_audio_features"] = audio_features
    tags["_raw_response"] = raw_response[:500]

    return tags


def load_library() -> list:
    if os.path.exists(LIBRARY_PATH):
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("bgm_list", [])
    return []


def save_library(bgm_list: list):
    os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump({"bgm_list": bgm_list}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="BGM 标签分析工具（librosa + MiMo）")
    parser.add_argument("--limit", type=int, default=0, help="只分析前 N 首（0=全部）")
    parser.add_argument("--force", action="store_true", help="强制重新分析已有标签")
    parser.add_argument("--id", help="只分析指定 ID 的歌曲")
    args = parser.parse_args()

    # 加载 prompt
    prompt_template = load_prompt()
    print(f"Prompt 模板已加载: {PROMPT_PATH}")

    # 加载库
    bgm_list = load_library()
    print(f"音乐库: {len(bgm_list)} 首")

    # 筛选待分析的歌曲
    to_analyze = []
    for track in bgm_list:
        if args.id and track.get("id") != args.id:
            continue

        # 跳过已分析的（除非 force）
        if not args.force and track.get("emotion_tag"):
            continue

        to_analyze.append(track)

    if args.limit > 0:
        to_analyze = to_analyze[:args.limit]

    print(f"待分析: {len(to_analyze)} 首")
    print("=" * 50)

    analyzed = 0
    failed = 0

    for i, track in enumerate(to_analyze):
        track_id = track.get("id", "")
        audio_file = track.get("audio_file", "")
        if audio_file:
            audio_path = os.path.join(AUDIO_DIR, audio_file)
        else:
            audio_path = os.path.join(AUDIO_DIR, f"{track_id}.mp3")

        if not os.path.exists(audio_path):
            print(f"  [{i+1}] {track.get('title', '?')[:30]} — 文件不存在，跳过")
            failed += 1
            continue

        print(f"  [{i+1}/{len(to_analyze)}] {track.get('title', '?')[:30]}...", end=" ", flush=True)

        try:
            tags = analyze_single(audio_path, track, prompt_template)
            if not tags:
                failed += 1
                print("FAILED")
                continue

            # 写入新标签
            emo_raw = tags.get("emotion_scores", {})
            emo_keys = ["joy", "sadness", "tension", "calm", "epic", "romantic", "nostalgic", "mysterious"]

            def to_int_10(v):
                """将 0-1 小数或 0-10 整数统一为 0-10 整数"""
                v = float(v) if v else 0
                if 0 <= v <= 1.0:
                    return round(v * 10)
                return max(0, min(10, round(v)))

            # 归一化：确保约束
            raw_scores = {k: to_int_10(emo_raw.get(k, 0)) for k in emo_keys}
            total = sum(raw_scores.values())

            # 约束1：总和在 20-35 之间
            if total > 35:
                scale = 35.0 / total
                raw_scores = {k: max(0, round(v * scale)) for k, v in raw_scores.items()}
            elif total < 20:
                # 补齐到 20
                deficit = 20 - total
                for k in sorted(raw_scores, key=lambda x: raw_scores[x]):
                    add = min(deficit, 3)
                    raw_scores[k] += add
                    deficit -= add
                    if deficit <= 0:
                        break

            # 确保至少 2 个维度 >= 6，至少 2 个维度 <= 3
            # (新 prompt 已在 LLM 侧约束，这里做兜底)

            track["emotion_tag"] = {
                **raw_scores,
                "tags": tags.get("emotion_tags", []),
                "arc_type": tags.get("emotion_arc", ""),
            }
            track["style_tag"] = {
                "primary": tags.get("primary_style", ""),
                "sub": tags.get("sub_styles", []),
                "instruments": tags.get("instruments", []),
            }
            track["rhythm_tag"] = {
                "bpm": tags.get("bpm_estimate", 0),
                "time_signature": tags.get("time_signature", "4/4"),
                "energy": tags.get("energy", 0),
                "danceability": tags.get("danceability", 0),
                "density": tags.get("density", 3),
                "vocal_ratio": tags.get("vocal_ratio", 0),
                "tags": tags.get("rhythm_tags", []),
            }
            track["scene_tag"] = {
                "fit": tags.get("fit_scenes", []),
                "unfit": tags.get("unfit_scenes", []),
                "start_position_sec": tags.get("start_position_sec", 0),
                "summary": tags.get("summary", ""),
            }
            # 从 emotion_tag 推导主情绪字段
            emo = track["emotion_tag"]
            emo_scores = {"joy": emo["joy"], "sadness": emo["sadness"],
                         "tension": emo["tension"], "calm": emo["calm"],
                         "epic": emo["epic"], "romantic": emo["romantic"],
                         "nostalgic": emo["nostalgic"], "mysterious": emo["mysterious"]}
            track["emotion"] = max(emo_scores, key=emo_scores.get)

            # 更新 tempo（用 librosa 精确值）
            audio_features = tags.get("_audio_features", {})
            if audio_features.get("bpm"):
                track["tempo"] = int(audio_features["bpm"])

            analyzed += 1

            # 显示简要结果
            emo = track["emotion_tag"]
            style = track["style_tag"]
            top_emo = max(
                [("joy", emo["joy"]), ("sadness", emo["sadness"]),
                 ("tension", emo["tension"]), ("calm", emo["calm"]),
                 ("epic", emo["epic"]), ("romantic", emo["romantic"]),
                 ("nostalgic", emo["nostalgic"]), ("mysterious", emo["mysterious"])],
                key=lambda x: x[1],
            )
            print(f"OK [{style['primary']}] {top_emo[0]}={top_emo[1]}/10")

            # 每 5 首保存一次
            if (i + 1) % 5 == 0:
                save_library(bgm_list)
                print(f"  --- 已保存 ({i+1}/{len(to_analyze)}) ---")

            time.sleep(3)  # 间隔避免限流

        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")

    # 最终保存
    save_library(bgm_list)
    print(f"\n{'=' * 50}")
    print(f"完成! 分析: {analyzed} | 失败: {failed} | 总计: {len(bgm_list)}")

    # 情绪分布统计
    emotion_counts = {}
    for t in bgm_list:
        et = t.get("emotion_tag", {})
        if not et:
            continue
        scores = {
            "joy": et.get("joy", 0), "sadness": et.get("sadness", 0),
            "tension": et.get("tension", 0), "calm": et.get("calm", 0),
            "epic": et.get("epic", 0), "romantic": et.get("romantic", 0),
            "nostalgic": et.get("nostalgic", 0), "mysterious": et.get("mysterious", 0),
        }
        if scores:
            primary = max(scores, key=scores.get)
            emotion_counts[primary] = emotion_counts.get(primary, 0) + 1
    if emotion_counts:
        print(f"\n主情绪分布:")
        for e, c in sorted(emotion_counts.items(), key=lambda x: -x[1]):
            print(f"  {e}: {c}")


if __name__ == "__main__":
    main()
