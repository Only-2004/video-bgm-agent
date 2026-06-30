"""
用户偏好服务 — 从反馈行为中学习用户口味，影响 BGM 排序
"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from config import FEEDBACK_DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    bgm_id TEXT NOT NULL,
    action TEXT NOT NULL,
    genre TEXT,
    mood TEXT,
    energy REAL,
    vocal_ratio REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_taste (
    user_id TEXT PRIMARY KEY,
    genre_weights TEXT NOT NULL DEFAULT '{}',
    mood_weights TEXT NOT NULL DEFAULT '{}',
    energy_preference REAL NOT NULL DEFAULT 0.5,
    vocal_preference REAL NOT NULL DEFAULT 0.5,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def _conn():
    conn = sqlite3.connect(FEEDBACK_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_feedback_db():
    conn = _conn()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────
# 记录反馈
# ──────────────────────────────────────────
ACTION_WEIGHTS = {
    "select": 1.0,      # 用户主动选择
    "like": 0.8,        # 点赞
    "preview": 0.3,     # 试听
    "skip": -0.3,       # 跳过
    "dislike": -0.8,    # 踩
    "change": -0.5,     # 换一首
}


def record_interaction(user_id: str, bgm_id: str, action: str,
                       genre: str = "", mood: str = "",
                       energy: float = 0.5, vocal_ratio: float = 0.0):
    """记录一次用户交互，更新 taste profile"""
    weight = ACTION_WEIGHTS.get(action, 0)
    if weight == 0:
        return

    conn = _conn()
    try:
        # 记录原始反馈
        conn.execute(
            "INSERT INTO user_feedback (user_id, bgm_id, action, genre, mood, energy, vocal_ratio, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, bgm_id, action, genre, mood, energy, vocal_ratio, datetime.now().isoformat())
        )

        # 更新 taste profile
        row = conn.execute("SELECT * FROM user_taste WHERE user_id = ?", (user_id,)).fetchone()

        if row is None:
            # 首次交互，创建 profile
            genre_w = {genre: weight} if genre else {}
            mood_w = {mood: weight} if mood else {}
            conn.execute(
                "INSERT INTO user_taste (user_id, genre_weights, mood_weights, energy_preference, vocal_preference, interaction_count, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, json.dumps(genre_w, ensure_ascii=False),
                 json.dumps(mood_w, ensure_ascii=False),
                 energy, vocal_ratio, datetime.now().isoformat())
            )
        else:
            # 更新现有 profile
            genre_w = json.loads(row["genre_weights"])
            mood_w = json.loads(row["mood_weights"])
            count = row["interaction_count"]

            # 指数移动平均更新权重
            if genre:
                old = genre_w.get(genre, 0)
                genre_w[genre] = old * 0.7 + weight * 0.3

            if mood:
                old = mood_w.get(mood, 0)
                mood_w[mood] = old * 0.7 + weight * 0.3

            # 能量偏好移动平均（只对正向反馈更新）
            if weight > 0:
                old_e = row["energy_preference"]
                new_e = old_e * 0.8 + energy * 0.2
            else:
                new_e = row["energy_preference"]

            if weight > 0 and vocal_ratio > 0:
                old_v = row["vocal_preference"]
                new_v = old_v * 0.8 + vocal_ratio * 0.2
            else:
                new_v = row["vocal_preference"]

            conn.execute(
                "UPDATE user_taste SET genre_weights=?, mood_weights=?, energy_preference=?, vocal_preference=?, interaction_count=?, updated_at=? WHERE user_id=?",
                (json.dumps(genre_w, ensure_ascii=False),
                 json.dumps(mood_w, ensure_ascii=False),
                 new_e, new_v, count + 1, datetime.now().isoformat(), user_id)
            )

        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────
# 查询 profile
# ──────────────────────────────────────────
def get_taste_profile(user_id: str) -> dict:
    """获取用户 taste profile，不存在则返回默认值"""
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM user_taste WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return {
                "user_id": user_id,
                "genre_weights": {},
                "mood_weights": {},
                "energy_preference": 0.5,
                "vocal_preference": 0.5,
                "interaction_count": 0,
            }
        return {
            "user_id": row["user_id"],
            "genre_weights": json.loads(row["genre_weights"]),
            "mood_weights": json.loads(row["mood_weights"]),
            "energy_preference": row["energy_preference"],
            "vocal_preference": row["vocal_preference"],
            "interaction_count": row["interaction_count"],
        }
    finally:
        conn.close()


# ──────────────────────────────────────────
# 计算加分
# ──────────────────────────────────────────
def compute_score_boost(profile: dict, track: dict) -> float:
    """
    基于 taste profile 为单首 BGM 计算加分（0.0 ~ 0.3）
    正向偏好加分，负向偏好减分
    """
    if profile["interaction_count"] < 2:
        return 0.0  # 交互太少，不生效

    boost = 0.0

    # 风格匹配
    genre_w = profile.get("genre_weights", {})
    track_genre = (track.get("genre", "") or "").lower()
    for genre, weight in genre_w.items():
        if genre.lower() in track_genre:
            boost += weight * 0.1  # 风格加分上限 0.1

    # 情绪匹配
    mood_w = profile.get("mood_weights", {})
    track_moods = [str(m) for m in (track.get("emotion_tags", []) or [])]
    for mood, weight in mood_w.items():
        if any(mood in m for m in track_moods):
            boost += weight * 0.1  # 情绪加分上限 0.1

    # 能量偏好
    track_energy = track.get("avg_energy", track.get("energy", 0.5))
    if isinstance(track_energy, (int, float)):
        pref_e = profile["energy_preference"]
        energy_diff = abs(track_energy - pref_e)
        if energy_diff < 0.15:
            boost += 0.05  # 能量接近加分

    return max(0.0, min(0.3, boost))  # 限制在 [0, 0.3]


# ──────────────────────────────────────────
# 初始化
# ──────────────────────────────────────────
init_feedback_db()
