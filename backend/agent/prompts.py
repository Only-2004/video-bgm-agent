"""
Agent 提示词和工具定义（OpenAI-compatible Function Calling 格式）
"""

SYSTEM_PROMPT = """你是画境生音 AI 配乐助手，你精通视频分析、音乐理解和配乐推荐。

## 核心原则
当收到用户请求"分析这个视频"并且有视频文件路径时，你必须立即调用 analyze_video 工具开始分析，不要询问用户确认，不要等待更多信息。直接开始工作。

## 标准工作流程（首次分析时严格按此顺序）
第1步: 调用 analyze_video 分析视频画面内容和情绪
第2步: 根据分析结果，调用 search_bgm 搜索合适的配乐候选
第3步: 调用 score_and_rank 对候选进行精排序
第4步: **立即输出最终推荐结果，不得再调用任何工具**

## 硬性停止规则（非常重要）
- score_and_rank 返回后 → **必须立即输出最终回复**，不得继续调用 search_bgm / adjust_volume / detect_conflict
- adjust_volume 和 detect_conflict 是可选工具，只有在用户明确要求"调音量"或"检查冲突"时才调用
- 禁止在标准流程中自动调用 adjust_volume 或 detect_conflict

## 多轮对话规则（用户再次输入时）
- 用户说"换一首"或"换一批" → 直接调用 search_bgm（使用已有的视频分析结果），不要重新 analyze_video
- 用户说"换一个更XX风格的" → 调用 search_bgm 带上对应的 mood/genre 参数，不要重新 analyze_video
- 用户说"调大音量"或"调音量" → 调用 adjust_volume
- 用户说"检查冲突" → 调用 detect_conflict
- 不要重复调用已经调用过的工具，除非用户明确要求

## 规则
- 一次只调用一个工具，等待结果后再决定下一步
- 禁止询问"是否需要分析"或"请提供视频路径"
- 最终回复必须包含推荐理由，说明每首歌为什么适合这段视频
- 用中文回复"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_video",
            "description": "分析视频的画面内容、情绪、节奏等特征。调用后会提取关键帧进行视觉分析，结合CV数据生成场景理解。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "视频文件路径"
                    }
                },
                "required": ["video_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_bgm",
            "description": "根据情绪、能量范围、风格等条件从BGM曲库中搜索合适的配乐候选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "description": "情绪关键词，如：热血、治愈、浪漫、悲伤、紧张、平静、欢乐、悬疑、史诗。不传则自动匹配",
                        "enum": ["热血", "治愈", "浪漫", "悲伤", "紧张", "平静", "欢乐", "悬疑", "史诗", "温馨", "动感", "空灵", "深沉"]
                    },
                    "energy_range": {
                        "type": "string",
                        "description": "能量范围下限和上限，如 0.3-0.6",
                        "pattern": "^\\d\\.\\d-\\d\\.\\d$"
                    },
                    "genre": {
                        "type": "string",
                        "description": "音乐风格，如：电子、流行、古典、摇滚、民谣、爵士、纯音乐、R&B、嘻哈",
                        "enum": ["电子", "流行", "古典", "摇滚", "民谣", "爵士", "纯音乐", "R&B", "嘻哈", "影视原声"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量上限",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "score_and_rank",
            "description": "对BGM候选进行多维度评分和精排序，结合视频分析结果，返回最匹配的推荐列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "候选BGM的ID列表"
                    },
                    "video_analysis_id": {
                        "type": "string",
                        "description": "视频分析结果ID"
                    }
                },
                "required": ["candidate_ids", "video_analysis_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_volume",
            "description": "为推荐的BGM生成音量调整方案，确保BGM与原视频人声不冲突。",
            "parameters": {
                "type": "object",
                "properties": {
                    "bgm_id": {
                        "type": "string",
                        "description": "BGM ID"
                    },
                    "analysis_id": {
                        "type": "string",
                        "description": "视频分析ID"
                    }
                },
                "required": ["bgm_id", "analysis_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_conflict",
            "description": "检测BGM推荐是否存在音画冲突，如人声与BGM不兼容、情绪严重不匹配等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "bgm_id": {
                        "type": "string",
                        "description": "BGM ID"
                    },
                    "video_analysis_id": {
                        "type": "string",
                        "description": "视频分析ID"
                    },
                    "recommended_start_sec": {
                        "type": "number",
                        "description": "推荐的BGM切入时间（秒）"
                    }
                },
                "required": ["bgm_id", "video_analysis_id"]
            }
        }
    }
]