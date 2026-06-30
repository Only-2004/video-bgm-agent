from fastapi import APIRouter, HTTPException
from models.schemas import MatchRequest
from services.bgm_matcher import BGMMatcher
from routers.analyze import analysis_tasks

router = APIRouter()


@router.post("/api/match")
async def match_bgm(request: MatchRequest):
    """
    根据分析结果匹配BGM
    请求体: {"analysis_id": "xxx"}
    返回：analysis_id, recommendations
    """
    task = analysis_tasks.get(request.analysis_id)
    if not task or task["status"] != "completed":
        raise HTTPException(status_code=400, detail="分析未完成或不存在")

    analysis = task["result"]

    matcher = BGMMatcher()
    recommendations = await matcher.match(analysis)

    return {
        "analysis_id": request.analysis_id,
        "recommendations": recommendations,
    }
