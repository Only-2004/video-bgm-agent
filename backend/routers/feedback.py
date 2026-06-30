"""
反馈路由 — 记录用户偏好，支持个性化推荐
"""
import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.taste_profile import record_interaction, get_taste_profile

router = APIRouter()


class FeedbackRequest(BaseModel):
    user_id: str = "default"
    bgm_id: str
    action: str  # select / like / skip / dislike / change / preview
    genre: str = ""
    mood: str = ""
    energy: float = 0.5
    vocal_ratio: float = 0.0


@router.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """记录用户对 BGM 的反馈"""
    if request.action not in ("select", "like", "skip", "dislike", "change", "preview"):
        raise HTTPException(status_code=400, detail=f"无效的 action: {request.action}")

    record_interaction(
        user_id=request.user_id,
        bgm_id=request.bgm_id,
        action=request.action,
        genre=request.genre,
        mood=request.mood,
        energy=request.energy,
        vocal_ratio=request.vocal_ratio,
    )

    return {"status": "ok", "action": request.action}


@router.get("/api/taste/{user_id}")
async def get_taste(user_id: str):
    """查看用户 taste profile（调试用）"""
    profile = get_taste_profile(user_id)
    return profile
