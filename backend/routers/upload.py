from fastapi import APIRouter, UploadFile, File, HTTPException
from config import UPLOAD_DIR
import uuid
import os

router = APIRouter()

os.makedirs(UPLOAD_DIR, exist_ok=True)

# 内存中保存上传文件信息（生产环境应使用数据库）
uploaded_files = {}


@router.post("/api/upload")
async def upload_video(video: UploadFile = File(...)):
    """
    上传视频文件
    返回：video_id, status, filename, size
    """
    # 验证文件类型
    allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"]
    if video.content_type and video.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式: {video.content_type}")

    video_id = str(uuid.uuid4())
    file_ext = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
    file_path = os.path.join(UPLOAD_DIR, f"{video_id}{file_ext}")

    # 保存文件
    content = await video.read()
    # I3: 文件大小限制100MB
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小超过100MB限制")
    with open(file_path, "wb") as f:
        f.write(content)

    # 记录文件信息
    uploaded_files[video_id] = {
        "video_id": video_id,
        "file_path": file_path,
        "filename": video.filename,
        "size": len(content),
        "content_type": video.content_type,
    }

    return {
        "video_id": video_id,
        "status": "uploaded",
        "file_path": file_path,
        "filename": video.filename,
        "size": len(content),
    }
