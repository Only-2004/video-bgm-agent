"""
Agent 路由 — 提供 SSE 流式接入点
"""
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from agent.engine import AgentEngine
from agent.db import init_db, save_session, load_all_sessions, delete_session, cleanup_old_sessions

router = APIRouter()

# 初始化 DB 表
init_db()

# 从 DB 恢复已有会话
agent_sessions: dict = {}
MAX_SESSIONS = 50

for row in load_all_sessions(MAX_SESSIONS):
    try:
        engine = AgentEngine.from_dict(row)
        agent_sessions[row["session_id"]] = {
            "session_id": row["session_id"],
            "agent": engine,
            "context": row["context"],
            "status": row["status"],
            "created_at": datetime.fromisoformat(row["created_at"]),
        }
    except Exception as e:
        print(f"[agent_route] 恢复会话失败 {row['session_id']}: {e}")


class AgentAnalyzeRequest(BaseModel):
    video_id: str
    file_path: str


class AgentChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/api/agent/analyze")
async def agent_analyze(request: AgentAnalyzeRequest):
    """
    启动 Agent 分析流程（SSE 流式）
    事件流：
      data: {"type":"tool_call","tool":"analyze_video",...}
      data: {"type":"tool_result","tool":"analyze_video",...}
      data: {"type":"final","content":"...","recommendations":[...]}
    """
    session_id = uuid.uuid4().hex[:12]

    # 内存保护 + DB 清理
    if len(agent_sessions) > MAX_SESSIONS:
        oldest = min(agent_sessions, key=lambda k: agent_sessions[k]["created_at"])
        agent_sessions.pop(oldest)
        delete_session(oldest)

    agent = AgentEngine(session_id=session_id)

    context = {
        "video_id": request.video_id,
        "file_path": request.file_path,
        "analysis_id": f"agent_{session_id}",
        "session_id": session_id,
    }

    agent_sessions[session_id] = {
        "session_id": session_id,
        "agent": agent,
        "context": context,
        "status": "running",
        "created_at": datetime.now(),
    }

    # 持久化
    save_session(session_id, agent.messages, context, status="running")

    async def event_stream():
        try:
            async for event in agent.run("分析这个视频并推荐最合适的配乐", context=context):
                if event.get("type") == "final":
                    event["session_id"] = session_id
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "final":
                    agent_sessions[session_id]["status"] = "completed"
                    save_session(session_id, agent.messages, context, status="completed")
                elif event.get("type") == "error":
                    agent_sessions[session_id]["status"] = "failed"
                    save_session(session_id, agent.messages, context, status="failed")
        except Exception as e:
            agent_sessions[session_id]["status"] = "failed"
            yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'session_id': session_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/agent/chat")
async def agent_chat(request: AgentChatRequest):
    """
    多轮对话：用户说"换一首温柔点的" → Agent 重新搜索推荐
    """
    session_data = agent_sessions.get(request.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} 不存在或已过期")

    agent: AgentEngine = session_data["agent"]
    context = session_data["context"]

    async def event_stream():
        try:
            async for event in agent.chat(request.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "final":
                    session_data["status"] = "completed"
                    save_session(request.session_id, agent.messages, context, status="completed")
                elif event.get("type") == "error":
                    session_data["status"] = "failed"
                    save_session(request.session_id, agent.messages, context, status="failed")
        except Exception as e:
            session_data["status"] = "failed"
            save_session(request.session_id, agent.messages, context, status="failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
