"""学习示范视频剪辑逻辑 API"""

import json
import sqlite3
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import DB_PATH, UPLOAD_DIR

router = APIRouter(prefix="/api/learn", tags=["learn"])


class LearnRequest(BaseModel):
    video_id: str
    file_path: str
    name: Optional[str] = ""


class ApplyRequest(BaseModel):
    pattern_id: str
    video_duration: float       # 新视频时长（秒）
    bgm_duration: float         # BGM 时长（秒）
    bgm_beat_times: list = []   # BGM 鼓点时间列表（可选）


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS editing_patterns (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT,
        audio_entry TEXT,
        climax_alignment TEXT,
        volume_segments TEXT,
        beat_sync TEXT,
        demo_duration_sec REAL,
        demo_video_id TEXT,
        detection_confidence REAL DEFAULT 0.5
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pattern_applications (
        id TEXT PRIMARY KEY,
        pattern_id TEXT,
        video_id TEXT,
        bgm_id TEXT,
        applied_at TEXT,
        result_summary TEXT
    )''')
    conn.commit()
    conn.close()


init_db()


@router.post("/analyze")
async def learn_from_demo(req: LearnRequest):
    """分析示范视频，存储剪辑 Pattern"""
    import os
    file_path = req.file_path
    if not os.path.isfile(file_path):
        raise HTTPException(404, f"视频文件不存在: {file_path}")

    # 提取音频
    from services.audio_extractor import AudioExtractor
    extractor = AudioExtractor()
    upload_dir = os.path.dirname(file_path)
    audio_path = extractor.extract(file_path, upload_dir)

    # 分析 Pattern
    from services.pattern_analyzer import PatternAnalyzer
    analyzer = PatternAnalyzer()
    pattern = analyzer.analyze_demo(
        video_path=file_path,
        audio_path=audio_path,
        name=req.name,
        video_id=req.video_id,
    )

    # 生成 ID 并存储
    pattern.id = str(uuid.uuid4())
    pattern.created_at = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO editing_patterns
               (id, name, description, created_at, audio_entry, climax_alignment,
                volume_segments, beat_sync, demo_duration_sec, demo_video_id, detection_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern.id, pattern.name, pattern.description, pattern.created_at,
                json.dumps(pattern.audio_entry.model_dump(), ensure_ascii=False),
                json.dumps(pattern.climax_alignment.model_dump(), ensure_ascii=False),
                json.dumps([v.model_dump() for v in pattern.volume_segments], ensure_ascii=False),
                json.dumps(pattern.beat_sync.model_dump(), ensure_ascii=False),
                pattern.demo_duration_sec,
                pattern.demo_video_id,
                pattern.detection_confidence,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # 清理临时音频
    try:
        os.remove(audio_path)
    except Exception:
        pass

    return {
        "pattern_id": pattern.id,
        "pattern": pattern.model_dump(),
    }


@router.get("/patterns")
async def list_patterns():
    """列出所有已学 Pattern"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM editing_patterns ORDER BY created_at DESC"
        ).fetchall()
        patterns = []
        for r in rows:
            patterns.append({
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "created_at": r["created_at"],
                "demo_duration_sec": r["demo_duration_sec"],
                "detection_confidence": r["detection_confidence"],
                "audio_entry": json.loads(r["audio_entry"]) if r["audio_entry"] else {},
                "beat_sync": json.loads(r["beat_sync"]) if r["beat_sync"] else {},
            })
        return {"patterns": patterns}
    finally:
        conn.close()


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(pattern_id: str):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM editing_patterns WHERE id=?", (pattern_id,))
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


@router.post("/apply")
async def apply_pattern(req: ApplyRequest):
    """将 Pattern 应用到新视频，生成剪辑计划"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM editing_patterns WHERE id=?", (req.pattern_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Pattern 不存在: {req.pattern_id}")

        # 重建 EditingPattern
        from models.patterns import (
            EditingPattern, AudioEntryInfo, ClimaxAlignment,
            VolumeSegment, BeatSyncRule,
        )
        pattern = EditingPattern(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            audio_entry=AudioEntryInfo(**json.loads(row["audio_entry"])) if row["audio_entry"] else AudioEntryInfo(),
            climax_alignment=ClimaxAlignment(**json.loads(row["climax_alignment"])) if row["climax_alignment"] else ClimaxAlignment(),
            volume_segments=[VolumeSegment(**v) for v in json.loads(row["volume_segments"])] if row["volume_segments"] else [],
            beat_sync=BeatSyncRule(**json.loads(row["beat_sync"])) if row["beat_sync"] else BeatSyncRule(),
            demo_duration_sec=row["demo_duration_sec"] or 0,
            demo_video_id=row["demo_video_id"],
            detection_confidence=row["detection_confidence"] or 0.5,
        )
    finally:
        conn.close()

    # 生成计划
    from services.pattern_applier import PatternApplier
    applier = PatternApplier()
    plan = applier.generate_plan(
        pattern=pattern,
        video_duration=req.video_duration,
        bgm_duration=req.bgm_duration,
        bgm_beat_times=req.bgm_beat_times,
    )

    # 记录应用历史
    conn2 = sqlite3.connect(DB_PATH)
    try:
        conn2.execute(
            """INSERT INTO pattern_applications
               (id, pattern_id, video_id, bgm_id, applied_at, result_summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                req.pattern_id,
                "",
                "",
                datetime.now().isoformat(),
                json.dumps(plan, ensure_ascii=False),
            ),
        )
        conn2.commit()
    finally:
        conn2.close()

    return {
        "plan": plan,
        "summary": applier.format_plan_summary(plan),
        "pattern_name": pattern.name,
    }
