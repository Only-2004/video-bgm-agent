import os

DATA_DIR = os.getenv("VIDEO_BGM_DATA_DIR", "D:/video-bgm-data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
LIBRARY_PATH = os.path.join(DATA_DIR, "bgm_library.json")
DB_PATH = os.path.join(DATA_DIR, "app.db")
AGENT_DB_PATH = os.path.join(DATA_DIR, "agent.db")
FEEDBACK_DB_PATH = os.path.join(DATA_DIR, "feedback.db")
MODEL_DIR = os.path.join(DATA_DIR, "models/bge-small-zh-v1.5")
