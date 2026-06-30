"""全流程匹配追踪：一首歌如何匹配上一个视频"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")

with open("D:/video-bgm-data/bgm_library.json", "r", encoding="utf-8") as f:
    library = json.load(f)
tracks = library["bgm_list"]

from services.audio_filter import AudioFilter
af = AudioFilter()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  输入：视频分析结果（滑雪跳跃视频，15秒）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

video_analysis = {
    "bpm_range": [100, 140],
    "vocal_ok": True,
    "overall_atmosphere": {"primary_mood": "热血激昂", "energy_level": 0.75},
    "video_genre": "极限运动",
    "video_structure": {
        "duration": 15,
        "transition_points": [
            {"timestamp": 3.0, "type": "cut", "tension_level": 0.6},
            {"timestamp": 8.0, "type": "whip", "tension_level": 0.8},
            {"timestamp": 12.0, "type": "fade", "tension_level": 0.5},
        ],
        "tension_curve": [
            {"tension": 0.4}, {"tension": 0.6}, {"tension": 0.8},
            {"tension": 0.9}, {"tension": 0.7}, {"tension": 0.5},
        ],
    },
    "key_matching_points": [
        {"video_timestamp": 8.0, "importance": "高", "reason": "跳跃高潮"},
    ],
    "music_imagination": {
        "recommended_styles": ["电子", "摇滚"],
        "recommended_characteristics": {"energy_range": [0.5, 0.9], "has_climax": True},
    },
    "color_mood": {"warm_ratio": 0.3, "dark_ratio": 0.5, "mood_tendency": "冷色调"},
    "alignment_strategy": "full_beat_sync",
    "video_imagination": "适合快节奏电子/摇滚，配合滑雪跳跃和速度感",
    "scene_analysis": {"scene_type": "极限运动", "mood": "热血"},
    "rhythm_pattern": {"pattern": "加速型"},
    "narrative_arc": {"arc_type": "渐强型", "closing_mood": "热血"},
    "camera_motion_type": "跟拍",
}

print("=" * 70)
print("  全流程匹配追踪")
print("  视频：滑雪跳跃短视频 (15秒)")
print("=" * 70)

# ─── Step 0: 视频分析输入 ───
print()
print("=" * 70)
print("  Step 0: 视频分析输入（来自 /api/analyze）")
print("=" * 70)
print()
print("  MiMo 看视频后输出:")
print(f"    video_genre     = 极限运动")
print(f"    primary_mood    = 热血激昂")
print(f"    energy_level    = 0.75 (CV张力曲线覆盖后)")
print(f"    alignment       = full_beat_sync (转场多+张力高)")
print(f"    camera_motion   = 跟拍 (运镜boost +0.20)")
print(f"    bpm_range       = [100, 140]")
print(f"    recommended     = 电子/摇滚, 有高潮")
print(f"    转场点(3个)     = 3s(cut,张力0.6) / 8s(whip,张力0.8) / 12s(fade,张力0.5)")
print(f"    张力曲线        = [0.4, 0.6, 0.8, 0.9, 0.7, 0.5]")
print(f"    color_mood      = 冷色调(warm=0.3, dark=0.5)")
print(f"    rhythm_pattern  = 加速型")
print(f"    narrative_arc   = 渐强型")
print(f"    key_point       = 8s(高重要性: 跳跃高潮)")
print()
print("  CV覆盖逻辑:")
print(f"    avg_tension = (0.4+0.6+0.8+0.9+0.7+0.5)/6 = 0.65")
print(f"    alignment=full_beat_sync → cv_energy = max(0.6, 0.65) = 0.65")
print(f"    camera=跟拍 → +0.20 → 0.85")
print(f"    video_genre=极限运动 → 基线0.6, 已超过, 不变")
print(f"    final energy_level = 0.85")

# 修正 energy_level 为计算值
video_analysis["overall_atmosphere"]["energy_level"] = 0.85

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stage 0: 硬过滤
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 70)
print("  Stage 0: 硬过滤（逐首检查，无 LLM）")
print("=" * 70)
print()
print("  规则:")
print("    1. BPM: 视频建议 [100,140], 硬过滤放宽到 [80,160]")
print("    2. 能量: rhythm_tag.energy <= 1.0")
print("    3. 人声: rhythm_tag.vocal_ratio <= 100%")
print("    4. 场景冲突: scene_tag.unfit 不能包含视频场景/类型关键词")
print()

passed = []
excluded = []
for t in tracks:
    rt = t.get("rhythm_tag", {})
    bpm = rt.get("bpm", 0)
    energy = rt.get("energy", 0.5)
    vocal = rt.get("vocal_ratio", 0)
    unfit = [s.lower() for s in t.get("scene_tag", {}).get("unfit", [])]

    reasons = []
    if bpm > 0 and not (80 <= bpm <= 160):
        reasons.append(f"BPM {bpm} 超范围 [80,160]")
    if energy > 1.0:
        reasons.append(f"能量 {energy} > 1.0")
    if vocal > 100:
        reasons.append(f"人声 {vocal}% > 100%")
    # 场景冲突检查：scene_type + video_genre
    video_keywords = {"极限运动"}
    for u in unfit:
        for kw in video_keywords:
            if kw in u or u in kw:
                reasons.append(f"场景冲突: unfit含'{u}', 视频含'{kw}'")
                break

    if reasons:
        excluded.append((t["title"], reasons, t))
    else:
        passed.append(t)

for title, reasons, t in excluded:
    print(f"  x {title}")
    for r in reasons:
        print(f"      {r}")
    print(f"      (bpm={t['rhythm_tag'].get('bpm')}, energy={t['rhythm_tag'].get('energy')}, "
          f"vocal={t['rhythm_tag'].get('vocal_ratio')}%, unfit={t.get('scene_tag',{}).get('unfit',[])})")
print()
print(f"  结果: {len(tracks)} 首 -> {len(passed)} 首通过")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stage 2: AudioFilter 14维打分
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 70)
print("  Stage 2: AudioFilter 14维代码筛选（无 LLM，纯代码逻辑）")
print("=" * 70)

reqs = af._extract_requirements(video_analysis)
print()
print("  从视频分析中提取的结构化需求:")
print(f"    bpm_min/max       = {reqs['bpm_min']} / {reqs['bpm_max']}")
print(f"    energy_min/max    = {reqs['energy_min']:.2f} / {reqs['energy_max']:.2f}")
print(f"    energy_level      = {reqs['energy_level']:.2f}")
print(f"    vocal_ok          = {reqs['vocal_ok']}")
print(f"    max_vocal_ratio   = {reqs['max_vocal_ratio']}")
print(f"    n_transitions     = {reqs['n_transitions']}")
print(f"    needs_climax      = {reqs['needs_climax']}")
print(f"    primary_mood      = {reqs['primary_mood']}")
print(f"    recommended_styles= {reqs['recommended_styles']}")
print(f"    alignment_strategy= {reqs['alignment_strategy']}")
print(f"    video_genre       = {reqs['video_genre']}")
print(f"    rhythm_pattern    = {reqs['rhythm_pattern']}")
print(f"    color_mood        = {reqs['color_mood']}")
print(f"    tension_values    = {reqs['tension_values']}")
print(f"    key_timestamps    = {reqs['key_timestamps']}")

candidates = [{"track": t, "score": 1.0} for t in passed]
filtered = af.filter(video_analysis, candidates)

# 展示 Top 5
dim_methods = [
    ("BPM", "_score_bpm"), ("能量", "_score_energy"), ("风格", "_score_style"),
    ("情绪", "_score_emotion"), ("高潮", "_score_climax"), ("人声", "_score_vocal"),
    ("动态", "_score_dynamics"), ("转场", "_score_transition_alignment"),
    ("色调", "_score_color_mood"), ("前向", "_score_forward_match"),
    ("节奏", "_score_rhythm_pattern"), ("音色", "_score_timbre"),
    ("文化", "_score_cultural_context"), ("约束", "_score_constraints"),
]
dim_keys = {
    "BPM": "bpm", "能量": "energy", "风格": "style", "情绪": "emotion",
    "高潮": "climax", "人声": "vocal", "动态": "dynamics", "转场": "transition",
    "色调": "color", "前向": "forward_match", "节奏": "rhythm", "音色": "timbre",
    "文化": "cultural", "约束": "constraints",
}
weights = {
    "bpm": 0.11, "energy": 0.08, "style": 0.11, "emotion": 0.08,
    "climax": 0.06, "vocal": 0.05, "dynamics": 0.05, "transition": 0.08,
    "color": 0.07, "forward_match": 0.10, "rhythm": 0.06, "timbre": 0.05,
    "cultural": 0.04, "constraints": 0.08,
}

print()
print("  Top 5 候选排名:")
print()

for rank, c in enumerate(filtered[:5]):
    t = c["track"]
    print(f"  {'━' * 60}")
    print(f"  [{rank+1}] {t['title']}  总分={c['score']:.3f}")
    print(f"  {'━' * 60}")

    total = 0
    for name, method in dim_methods:
        score, reason = getattr(af, method)(t, reqs)
        key = dim_keys[name]
        w = weights[key]
        contrib = score * w
        total += contrib
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        r_str = f"  ({reason})" if reason else ""
        print(f"    {name:4s} {bar} {score:.2f} x {w:.2f} = {contrib:.3f}{r_str}")
    print(f"    {'─' * 45}")
    print(f"    加权总分 = {total:.3f}  (代码算的 = {c['score']:.3f})")
    print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stage 3: MiMo 精听（模拟）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 70)
print("  Stage 3: MiMo 精听匹配（Top 3 送入 MiMo API）")
print("=" * 70)
print()
print("  MiMo 拿到:")
print("    1. Top 3 候选的 MP3 音频（转 WAV）")
print("    2. 视频分析结果文本（转场点/张力曲线/情绪/音乐想象）")
print()
print("  MiMo 听歌后输出:")
print("    - audio_analysis: 每首歌的 energy_shape/climax_count/energy_baseline")
print("    - matching_analysis: video_type/recommended_start_sec/video_imagination")
print("    - recommendation: best_match/final_score/recommended_cut_points")
print()
print("  (实际运行需要调用 MiMo API，此处展示 Stage 2 结果)")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stage 2 后处理：形状匹配 + 结尾匹配
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 70)
print("  Stage 2 后处理：能量形状 + 结尾类型匹配")
print("=" * 70)
print()

winner = filtered[0]["track"]
es = winner.get("energy_shape", {})
shape = es.get("shape", "") if isinstance(es, dict) else ""
arc = "渐强型"  # 视频 narrative_arc

print(f"  能量形状匹配:")
print(f"    BGM energy_shape = {shape}")
print(f"    视频 narrative_arc = {arc}")

SHAPE_COMPAT = {
    ("渐强型", "渐强型"): 0.95, ("渐强型", "爆发型"): 0.6, ("渐强型", "平稳型"): 0.3,
    ("渐强型", "先抑后扬型"): 0.7, ("渐强型", "波动型"): 0.5,
    ("爆发型", "渐强型"): 0.6, ("爆发型", "爆发型"): 0.95, ("爆发型", "平稳型"): 0.4,
    ("爆发型", "先抑后扬型"): 0.5, ("爆发型", "波动型"): 0.6,
    ("脉冲型", "渐强型"): 0.5, ("脉冲型", "爆发型"): 0.6, ("脉冲型", "平稳型"): 0.5,
    ("脉冲型", "先抑后扬型"): 0.5, ("脉冲型", "波动型"): 0.9,
    ("平稳型", "渐强型"): 0.3, ("平稳型", "爆发型"): 0.3, ("平稳型", "平稳型"): 0.95,
    ("平稳型", "先抑后扬型"): 0.4, ("平稳型", "波动型"): 0.4,
    ("衰落型", "渐强型"): 0.4, ("衰落型", "爆发型"): 0.4, ("衰落型", "平稳型"): 0.6,
    ("衰落型", "先抑后扬型"): 0.9, ("衰落型", "波动型"): 0.5,
}
compat = SHAPE_COMPAT.get((shape, arc), 0.5)
print(f"    兼容矩阵 ({shape}, {arc}) = {compat}")
shape_bonus = (compat - 0.5) * 0.3
print(f"    shape_bonus = ({compat} - 0.5) * 0.3 = {shape_bonus:+.3f}")

# 结尾匹配
ending = winner.get("ending_type", "")
print()
print(f"  结尾类型匹配:")
print(f"    BGM ending_type = {ending or '(无数据)'}")
print(f"    视频 closing_mood = 热血")
if ending == "fade_out":
    print(f"    fade_out + 热血结尾 → -0.03 (能量对不上)")
elif ending == "hard_stop":
    print(f"    hard_stop + 热血结尾 → +0.05 (有力收束)")
elif ending == "sustain":
    print(f"    sustain + 热血 → +0.03 (能量保持)")
else:
    print(f"    无 ending_type 数据 → 0.00")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stage 3 后处理：双向验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 70)
print("  Stage 3 后处理：双向验证（正向+反向）")
print("=" * 70)
print()
print("  正向匹配（已完成）:")
print("    视频需求 → BGM 标签 = Stage 2 的 14维打分")
print()
print("  反向验证（需要 Stage 3 的 bgm_video_imagination）:")
print("    BGM 的 video_imagination → 视频实际特征")
print("    例如: MiMo 听完歌后说'这首歌适合热血运动视频'")
print("          与视频实际 genre=极限运动 对比 → 一致性分数")
print()
print("    检查维度:")
print("      1. 视频类型是否在 BGM 想象中 (genre_keywords 匹配)")
print("      2. 情绪是否匹配 (mood_keywords 匹配)")
print("      3. 场景是否匹配 (scene_type 匹配)")
print("      4. 矛盾检测 (平静视频 vs 热血BGM = 扣分)")
print()
print("    bidirectional_factor:")
print("      >= 0.8 → 1.0 (不衰减)")
print("      0.5-0.8 → 0.7 (轻度衰减)")
print("      < 0.5 → max(0.3, score) (中度衰减)")
print("      < 0.3 + 有矛盾 → 0.15 (严重衰减)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  最终输出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 70)
print("  最终输出: BGMRecommendation")
print("=" * 70)
print()
print("  每个推荐包含:")
print("    bgm              = BGMTrack (id/title/artist/duration/...)")
print("    match_score      = Stage 2 加权分 + 形状bonus + 结尾bonus")
print("    reason           = 各维度匹配理由拼接")
print("    start_sec        = MiMo 推荐的切入点 (秒)")
print("    climax_hint      = 高潮段时间段")
print("    cut_points       = MiMo 推荐的剪辑点")
print("    bidirectional_factor = 反向验证分数")
print("    volume_adjustments   = 音量曲线 (避免BGM抢人声)")
print()

# 模拟最终结果
final_score = filtered[0]["score"] + shape_bonus
print(f"  模拟最终推荐:")
print(f"    歌曲: {winner['title']}")
print(f"    match_score = {filtered[0]['score']:.3f} + {shape_bonus:+.3f} = {final_score:.3f}")
print(f"    reason = {filtered[0]['reason'][:100]}")
print(f"    start_sec = (由 Stage 3 MiMo 决定)")
print(f"    bidirectional_factor = (由 Stage 3 MiMo 决定)")
print()
print("=" * 70)
print("  全流程结束")
print("=" * 70)
