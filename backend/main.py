from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import upload, learn, agent_route, feedback
from config import AUDIO_DIR
import os

app = FastAPI(title="视频智能配乐API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(learn.router)
app.include_router(agent_route.router)
app.include_router(feedback.router)

# Serve frontend static files
WEB_DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../web-demo")


@app.get("/")
async def root():
    index_path = os.path.join(WEB_DEMO_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "视频智能配乐API v2.0"}


if os.path.isdir(WEB_DEMO_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DEMO_DIR), name="static")

# BGM 封面图
BGM_COVERS_DIR = os.path.join(WEB_DEMO_DIR, "bgm-covers")
if os.path.isdir(BGM_COVERS_DIR):
    app.mount("/bgm-covers", StaticFiles(directory=BGM_COVERS_DIR), name="bgm-covers")

# Serve audio files from D: drive
if os.path.isdir(AUDIO_DIR):
    app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
