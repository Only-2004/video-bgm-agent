"""
一次性脚本：为 BGM 库预计算匹配约束 (constraints)。

从已有字段派生：
- min_video_energy: 从 energy_baseline 或 energy_curve 最低值
- requires_buildup: 从 energy_shape 判断
- has_lyrics: 从 rhythm_tag.vocal_ratio 判断
- best_entry_points: 优先用 beat_events（强拍/弱拍分类），降级用 energy_curve 谷底
- worst_entry_points: 从 climax_segments 中点 + energy_curve 峰值
"""

import json
import numpy as np

LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"


def compute_constraints(track: dict) -> dict:
    """从已有字段推导约束"""
    duration = track.get("duration", 60)

    # min_video_energy: BGM 能量基线
    energy_baseline = (track.get("energy_shape") or {}).get("energy_baseline")
    if energy_baseline is None:
        ec = track.get("energy_curve", [])
        if ec:
            energy_baseline = round(min(ec), 3)
        else:
            energy_baseline = 0.1

    # requires_buildup
    energy_shape = (track.get("energy_shape") or {}).get("shape", "")
    requires_buildup = energy_shape in ("渐强型", "爆发型")

    # has_lyrics
    vocal_ratio = track.get("rhythm_tag", {}).get("vocal_ratio", 0)
    has_lyrics = vocal_ratio > 30

    # best_entry_points: 优先用 beat_events（librosa 强拍分类）
    beat_events = track.get("beat_events", [])
    if beat_events:
        # 取 strong + climax 拍点
        strong_beats = [e["time"] for e in beat_events if e.get("type") in ("strong", "climax")]
        best_entries = []
        for t in strong_beats:
            if not best_entries or t - best_entries[-1] > 1.0:
                best_entries.append(round(t, 1))
            if len(best_entries) >= 5:
                break
        if not best_entries or best_entries[0] > 0.5:
            best_entries.insert(0, 0.0)
    else:
        # 降级：用 energy_curve 谷底
        best_entries = []
        ec = track.get("energy_curve", [])
        if ec and len(ec) >= 3:
            for i in range(1, len(ec) - 1):
                if ec[i] < ec[i-1] and ec[i] < ec[i+1]:
                    segment_len = duration / len(ec)
                    ts = round((i + 0.5) * segment_len, 1)
                    best_entries.append(ts)
            if not best_entries:
                min_idx = ec.index(min(ec))
                segment_len = duration / len(ec)
                best_entries.append(round((min_idx + 0.5) * segment_len, 1))
        # 添加结构段落开头（仅当 structural_sections 来自可靠数据时）
        sections = track.get("structural_sections", [])
        for s in sections:
            section_type = s.get("section", "")
            start = s.get("start", 0)
            if section_type in ("intro", "build-up", "bridge") and start not in best_entries:
                best_entries.append(round(start, 1))
        if 0 not in best_entries:
            best_entries.insert(0, 0)
        best_entries.sort()

    # worst_entry_points: 高潮中段 + 能量峰值
    worst_entries = []
    climax_segs = track.get("climax_segments", [])
    for c in climax_segs:
        mid = (c.get("start", 0) + c.get("end", 0)) / 2
        worst_entries.append(round(mid, 1))

    ec = track.get("energy_curve", [])
    if ec and len(ec) >= 3:
        for i in range(1, len(ec) - 1):
            if ec[i] > ec[i-1] and ec[i] > ec[i+1] and ec[i] > 0.7:
                segment_len = duration / len(ec)
                ts = round((i + 0.5) * segment_len, 1)
                if ts not in worst_entries:
                    worst_entries.append(ts)
    worst_entries.sort()

    return {
        "min_video_energy": energy_baseline,
        "requires_buildup": requires_buildup,
        "has_lyrics": has_lyrics,
        "best_entry_points": best_entries,
        "worst_entry_points": worst_entries,
    }


def main():
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    bgm_list = data.get("bgm_list", [])
    print(f"共 {len(bgm_list)} 首 BGM，计算约束...")

    for i, track in enumerate(bgm_list):
        title = track.get("title", "?")
        constraints = compute_constraints(track)
        track["constraints"] = constraints
        print(f"[{i+1}] {title}")
        print(f"  min_energy={constraints['min_video_energy']}, "
              f"buildup={constraints['requires_buildup']}, "
              f"lyrics={constraints['has_lyrics']}")
        print(f"  best_entries={constraints['best_entry_points']}")
        print(f"  worst_entries={constraints['worst_entry_points']}")

    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n完成！已更新 {LIBRARY_PATH}")


if __name__ == "__main__":
    main()
