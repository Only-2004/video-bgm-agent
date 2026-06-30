"""
一次性脚本：用所有新字段重写 BGM 库的 feature_text。

feature_text 是 embedding search 的核心索引文本，需要包含：
风格/配器/BPM/能量/人声占比/高潮段/律动感/结尾类型/音色质感
"""

import json

LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"


def build_feature_text(track: dict) -> str:
    """从所有字段拼接客观描述文本"""
    parts = []

    # 风格与配器
    st = track.get("style_tag", {})
    primary = st.get("primary", "")
    sub = st.get("sub", [])
    instruments = st.get("instruments", [])
    if primary:
        style_str = primary
        if sub:
            style_str += f"({', '.join(sub)})"
        parts.append(style_str)
    if instruments:
        parts.append(f"配器: {', '.join(instruments)}")

    # BPM 与能量
    rt = track.get("rhythm_tag", {})
    bpm = rt.get("bpm", 0)
    energy = rt.get("energy", 0.5)
    vocal_ratio = rt.get("vocal_ratio", 0)
    density = rt.get("density", 3)
    if bpm:
        parts.append(f"BPM{bpm}")
    parts.append(f"能量{energy:.1f}")
    if vocal_ratio > 0:
        parts.append(f"人声{vocal_ratio}%")
    parts.append(f"配器密度{density}/5")

    # 情绪标签
    et = track.get("emotion_tag", {})
    tags = et.get("tags", [])
    arc_type = et.get("arc_type", "")
    if tags:
        parts.append(f"情绪: {', '.join(tags)}")
    if arc_type:
        parts.append(f"情绪弧线: {arc_type}")

    # 高潮段
    climax_segs = track.get("climax_segments", [])
    if climax_segs:
        climax_strs = [f"{c['start']}-{c['end']}s" for c in climax_segs]
        parts.append(f"高潮段: {', '.join(climax_strs)}")

    # 律动感
    beat_reg = track.get("rhythm_tag", {}).get("beat_regularity")
    swing = track.get("rhythm_tag", {}).get("swing_ratio")
    if beat_reg is not None:
        if beat_reg > 0.85:
            parts.append("节拍极规律(适合卡点)")
        elif beat_reg > 0.65:
            parts.append("节拍较规律")
        else:
            parts.append("节拍自由")
    if swing is not None and swing > 0.3:
        parts.append("有swing感")

    # 结尾类型
    ending = track.get("ending_type", "")
    if ending:
        ending_map = {"fade_out": "渐弱结尾", "hard_stop": "突然停止", "sustain": "持续到结束"}
        parts.append(ending_map.get(ending, ending))

    # 音色质感
    tp = track.get("timbre_profile", {})
    if tp:
        label = tp.get("timbre_label", "")
        centroid = tp.get("centroid_mean", 0.5)
        reverb = tp.get("reverb_estimate", 0.5)
        if label:
            parts.append(f"音色: {label}")
        else:
            # 从数值推导简短描述
            brightness = "明亮" if centroid > 0.5 else "温暖" if centroid < 0.3 else "中性"
            spatial = "大厅混响" if reverb > 0.6 else "近场干声" if reverb < 0.3 else ""
            if spatial:
                parts.append(f"音色: {brightness}{spatial}")
            else:
                parts.append(f"音色: {brightness}")

    # 结构段落摘要
    sections = track.get("structural_sections", [])
    if sections:
        section_types = [s.get("section", "") for s in sections]
        # 去重保序
        seen = set()
        unique = []
        for s in section_types:
            if s and s not in seen:
                seen.add(s)
                unique.append(s)
        if unique:
            parts.append(f"结构: {'→'.join(unique)}")

    # 适用场景
    scene_tag = track.get("scene_tag", {})
    fit = scene_tag.get("fit", [])
    if fit:
        parts.append(f"适合: {', '.join(fit[:3])}")

    # 时长
    duration = track.get("duration", 0)
    if duration:
        parts.append(f"时长{duration}秒")

    return "，".join(parts)


def main():
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    bgm_list = data.get("bgm_list", [])
    print(f"共 {len(bgm_list)} 首 BGM，重写 feature_text...")

    for i, track in enumerate(bgm_list):
        title = track.get("title", "?")
        old_text = track.get("feature_text", "")
        new_text = build_feature_text(track)
        track["feature_text"] = new_text
        print(f"[{i+1}] {title}")
        print(f"  旧: {old_text[:80]}...")
        print(f"  新: {new_text[:80]}...")

    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n完成！已更新 {LIBRARY_PATH}")


if __name__ == "__main__":
    main()
