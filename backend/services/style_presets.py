"""
视频场景风格预设 — 映射视频类型 → BGM 偏好

用于硬过滤加分和推荐起始位置建议
"""

STYLE_PRESETS = {
    # ──── 运动 / 极限 ────
    "极限运动": {
        "energy_range": (0.6, 1.0),
        "bpm_range": (120, 180),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Rock", "Metal"],
        "prefer_climax": True,
        "description": "高能量电子/摇滚，强劲节拍匹配运动节奏",
    },
    "滑雪": {
        "energy_range": (0.5, 0.9),
        "bpm_range": (110, 160),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Rock", "Pop"],
        "prefer_climax": True,
        "description": "推进感强的电子乐或摇滚，配合速度感",
    },
    "健身": {
        "energy_range": (0.5, 0.9),
        "bpm_range": (110, 150),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Hip-Hop", "Rock"],
        "prefer_climax": True,
        "description": "节奏感强的电子/Hip-Hop，适合运动节拍",
    },
    "跑步": {
        "energy_range": (0.4, 0.8),
        "bpm_range": (100, 140),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Pop", "Rock"],
        "prefer_climax": False,
        "description": "稳定节奏的电子乐或流行乐，配速感",
    },

    # ──── 生活 / 日常 ────
    "日常Vlog": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (70, 120),
        "prefer_vocal": False,
        "prefer_styles": ["Lofi", "Pop", "Acoustic", "Indie"],
        "prefer_climax": False,
        "description": "轻松温暖的 Lofi/原声，不抢画面注意力",
    },
    "美食": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (80, 120),
        "prefer_vocal": False,
        "prefer_styles": ["Lofi", "Jazz", "Acoustic", "Pop"],
        "prefer_climax": False,
        "description": "轻松愉悦的 Lofi 或爵士，营造温馨氛围",
    },
    "旅行": {
        "energy_range": (0.3, 0.6),
        "bpm_range": (80, 130),
        "prefer_vocal": False,
        "prefer_styles": ["Pop", "Indie", "Acoustic", "World"],
        "prefer_climax": False,
        "description": "温暖开阔的流行/独立音乐，适合旅途风景",
    },
    "宠物": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (80, 130),
        "prefer_vocal": False,
        "prefer_styles": ["Pop", "Lofi", "Acoustic"],
        "prefer_climax": False,
        "description": "可爱轻快的流行/Lofi，配合萌宠画面",
    },

    # ──── 风景 / 自然 ────
    "自然风光": {
        "energy_range": (0.1, 0.4),
        "bpm_range": (60, 100),
        "prefer_vocal": False,
        "prefer_styles": ["Ambient", "Classical", "New Age", "Acoustic"],
        "prefer_climax": False,
        "description": "舒缓氛围乐或古典，衬托自然壮美",
    },
    "延时摄影": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (70, 120),
        "prefer_vocal": False,
        "prefer_styles": ["Ambient", "Electronic", "Post-Rock"],
        "prefer_climax": False,
        "description": "氛围电子或后摇滚，配合时间流逝感",
    },
    "城市夜景": {
        "energy_range": (0.3, 0.6),
        "bpm_range": (80, 120),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Lo-fi", "Synthwave"],
        "prefer_climax": False,
        "description": "电子/Synthwave，营造都市夜晚氛围",
    },

    # ──── 情感 / 叙事 ────
    "温情": {
        "energy_range": (0.1, 0.4),
        "bpm_range": (60, 100),
        "prefer_vocal": True,
        "prefer_styles": ["Acoustic", "Pop", "Classical", "Indie"],
        "prefer_climax": False,
        "description": "温暖原声/钢琴，适合情感叙事",
    },
    "婚礼": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (60, 100),
        "prefer_vocal": True,
        "prefer_styles": ["Classical", "Pop", "Acoustic"],
        "prefer_climax": False,
        "description": "浪漫古典或流行，适合婚礼仪式",
    },
    "纪录片": {
        "energy_range": (0.2, 0.5),
        "bpm_range": (60, 110),
        "prefer_vocal": True,
        "prefer_styles": ["Classical", "Ambient", "World", "Acoustic"],
        "prefer_climax": False,
        "description": "沉稳古典或世界音乐，配合叙事深度",
    },

    # ──── 商业 / 产品 ────
    "产品展示": {
        "energy_range": (0.3, 0.6),
        "bpm_range": (80, 120),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Pop", "Corporate"],
        "prefer_climax": False,
        "description": "简洁现代的电子/流行，突出产品质感",
    },
    "广告": {
        "energy_range": (0.4, 0.7),
        "bpm_range": (90, 130),
        "prefer_vocal": False,
        "prefer_styles": ["Pop", "Electronic", "Rock"],
        "prefer_climax": True,
        "description": "抓耳的流行/电子，快速吸引注意力",
    },

    # ──── 其他 ────
    "搞笑": {
        "energy_range": (0.3, 0.7),
        "bpm_range": (80, 140),
        "prefer_vocal": False,
        "prefer_styles": ["Pop", "Comedy", "Electronic"],
        "prefer_climax": False,
        "description": "轻快搞怪的音乐，配合幽默画面",
    },
    "恐怖": {
        "energy_range": (0.1, 0.4),
        "bpm_range": (40, 80),
        "prefer_vocal": False,
        "prefer_styles": ["Ambient", "Dark", "Soundtrack"],
        "prefer_climax": False,
        "description": "低沉暗黑氛围乐，营造紧张恐怖感",
    },
    "游戏": {
        "energy_range": (0.4, 0.8),
        "bpm_range": (100, 150),
        "prefer_vocal": False,
        "prefer_styles": ["Electronic", "Chiptune", "Rock"],
        "prefer_climax": True,
        "description": "动感电子/芯片音乐，配合游戏节奏",
    },
}

# 场景关键词 → 预设名称 的模糊映射
SCENE_KEYWORDS = {
    "滑雪": ["滑雪", "雪", "滑雪场", "snow", "ski"],
    "极限运动": ["极限", "跑酷", "攀岩", "跳伞", "滑板", "冲浪", "BMX"],
    "健身": ["健身", "gym", "运动", "锻炼", "肌肉"],
    "跑步": ["跑步", "晨跑", "夜跑", "马拉松", "running"],
    "日常Vlog": ["日常", "vlog", "生活", "一天", "日常记录"],
    "美食": ["美食", "做饭", "烹饪", "餐厅", "吃", "food", "cooking"],
    "旅行": ["旅行", "旅游", "旅途", "风景", "攻略", "travel"],
    "宠物": ["猫", "狗", "宠物", "萌宠", "cat", "dog"],
    "自然风光": ["自然", "山", "海", "湖", "日落", "日出", "森林", "landscape"],
    "延时摄影": ["延时", "timelapse", "time-lapse"],
    "城市夜景": ["城市", "夜景", "都市", "city", "night"],
    "温情": ["温情", "感动", "亲情", "友情", "温暖"],
    "婚礼": ["婚礼", "结婚", "婚纱", "wedding"],
    "纪录片": ["纪录片", "纪录", "documentary"],
    "产品展示": ["产品", "展示", "开箱", "评测", "product"],
    "广告": ["广告", "宣传", "推广", "品牌"],
    "搞笑": ["搞笑", "幽默", "沙雕", "funny", "comedy"],
    "恐怖": ["恐怖", "惊悚", "悬疑", "horror"],
    "游戏": ["游戏", "电竞", "game", "esport"],
}


def match_scene(scene_type: str, theme: str = "", purpose: str = "") -> dict | None:
    """
    根据场景类型/主题/用途匹配最接近的风格预设

    返回预设 dict 或 None
    """
    text = f"{scene_type} {theme} {purpose}".lower()

    # 精确匹配
    for preset_name in STYLE_PRESETS:
        if preset_name in text:
            return STYLE_PRESETS[preset_name]

    # 关键词匹配
    for preset_name, keywords in SCENE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return STYLE_PRESETS[preset_name]

    return None


def get_preset(name: str) -> dict | None:
    """按名称获取预设"""
    return STYLE_PRESETS.get(name)
