# 画境生音 — AI 视频配乐 Agent

上传视频，AI 自动分析画面情绪、节奏和内容，从 BGM 曲库中推荐最匹配的配乐。支持多轮对话调整推荐。

## 架构

```
用户上传视频 → LLM (Function Calling) → 自主调用工具 → 返回推荐
                    │
              ┌─────┴──────┐
              │   Tools     │
              ├─────────────┤
              │ analyze_video    │
              │ search_bgm       │
              │ score_and_rank   │
              │ adjust_volume    │
              │ detect_conflict  │
              └─────────────────┘
```

Agent 使用 LLM Function Calling 驱动，LLM 自主决定调用哪些工具和分析顺序，而非固定流水线。

## 快速开始

```bash
# 安装依赖
cd backend
pip install -r requirements.txt

# 启动服务
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 打开浏览器访问
http://localhost:8000
```

### 数据目录

BGM 曲库和音频文件存放在 `D:/video-bgm-data/`：

```
D:/video-bgm-data/
├── bgm_library.json    # BGM 曲库（标题、情绪标签、能量值等）
├── audio/              # BGM 音频文件（.mp3）
├── uploads/            # 上传的视频文件
└── agent.db            # Agent 会话持久化
```

## 项目结构

```
video-bgm-agent/
├── backend/                # Python FastAPI 后端
│   ├── agent/              # Agent 引擎
│   │   ├── engine.py       # FC 主循环（LLM + tool calling）
│   │   ├── tools.py        # 5 个工具执行器
│   │   ├── prompts.py      # system prompt + tool schema
│   │   └── db.py           # 会话 SQLite 持久化
│   ├── routers/
│   │   ├── upload.py       # 视频上传
│   │   ├── agent_route.py  # Agent SSE 流式端点
│   │   └── learn.py        # 编辑模式学习
│   ├── services/
│   │   ├── cv_analyzer.py       # 计算机视觉分析
│   │   ├── keyframe_extractor.py # 关键帧提取
│   │   ├── mimo_analyzer.py     # 多模态语义分析
│   │   ├── audio_filter.py      # 14 维 BGM 评分
│   │   ├── mimo_fine_ranker.py  # LLM 精排序
│   │   └── ...
│   ├── models/             # Pydantic 数据模型
│   ├── config.py           # 路径和 API 配置
│   └── main.py             # FastAPI 入口
│
├── web-demo/               # 移动端 Web UI
│   ├── index.html          # 5 页面 SPA
│   ├── app.js              # 前端逻辑（SSE + 轮播 + 多轮对话）
│   ├── style.css           # 样式
│   ├── bgm-covers/         # BGM 封面图
│   └── static/             # 静态资源
```

## API 端点

### Agent 流式分析（推荐使用）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传视频文件 |
| POST | `/api/agent/analyze` | SS**E **启动 Agent 分析，实时推送进度 |
| POST | `/api/agent/chat` | 多轮对话调整推荐 |

SSE 事件流：
```
data: {"type":"tool_call","tool":"analyze_video",...}
data: {"type":"tool_result","tool":"analyze_video",...}
data: {"type":"final","content":"...","recommendations":[...]}
```

### 传统 REST（已退役）

| 方法 | 路径 | 状态 |
|------|------|------|
| POST | `/api/analyze` | 已退役 |
| GET | `/api/status/{id}` | 已退役 |
| POST | `/api/match` | 已退役 |

## Agent 工具

| 工具 | 功能 | 底层服务 |
|------|------|----------|
| `analyze_video` | 分析画面内容、情绪、场景 | KeyFrameExtractor + CVAnalyzer + MiMoAnalyzer |
| `search_bgm` | 按情绪/风格/能量搜索曲库 | bgm_library.json 查询 |
| `score_and_rank` | 14 维评分 + LLM 精排序 | AudioFilter + MiMoFineRanker |
| `adjust_volume` | BGM 音量调整方案 | VolumeAdjuster |
| `detect_conflict` | 检测音画冲突 | ConflictDetector |

## 多轮对话示例

```
用户: "换一首更治愈的"
Agent: (调用 search_bgm mood="治愈") → 返回新推荐

用户: "换成纯音乐"
Agent: (调用 search_bgm genre="纯音乐") → 返回新推荐
```

## 技术栈

- **后端**: Python 3.13+, FastAPI, httpx
- **AI 模型**: MiMo-v2.5 (LLM Function Calling, 多模态分析)
- **前端**: 原生 HTML/CSS/JS, SSE 流式, GSAP 动画
- **持久化**: SQLite (会话存储)
- **视觉分析**: OpenCV (CV 分析, 关键帧提取)