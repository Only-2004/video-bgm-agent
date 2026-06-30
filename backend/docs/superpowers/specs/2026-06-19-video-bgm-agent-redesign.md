# 视频配乐智能体全面重构计划

## 目标

将现有「结构化标签匹配」系统重构为「自然语言描述 + embedding 语义检索」系统，对标设计文档的四层架构。

## 现状

- 11 首已标注 BGM（8 维情绪打分 + 风格/场景/节奏标签）
- MiMo 视频五维分析（visual/audio/temporal/text/semantic）
- 向量检索（基于 8 维情绪向量余弦相似度）
- 冲突检测、音量调整、反馈闭环

## 重构范围

### Phase 1: BGM 库升级 — 自然语言描述 + Embedding

**目标**：每首 BGM 从「结构化标签」升级为「50-100 字自然语言描述 + embedding 向量」

**改动文件**：
- `tools/bgm_describer.py`（新建）— 批量生成自然语言描述
- `tools/bgm_embedder.py`（新建）— 本地 embedding 生成
- `models/schemas.py` — BGMTrack 新增 `description` 和 `embedding` 字段

**实现步骤**：
1. 用 MiMo 为 11 首歌各生成 50-100 字自然语言描述（输入：歌名+艺术家+现有标签）
2. 安装 sentence-transformers，用 `all-MiniLM-L6-v2` 模型本地生成 384 维 embedding
3. 更新 bgm_library.json，每首歌新增 `description` 和 `embedding` 字段
4. 保留现有标签作为辅助过滤字段

**Prompt 设计**（生成描述用）：
```
你是音乐描述专家。根据以下信息，为这首歌写一段 50-100 字的自然语言描述，
侧重描述它的情绪氛围和适合的视频场景。

歌名：{title}
艺术家：{artist}
风格：{primary_style}
情绪标签：{emotion_tags}
适合场景：{fit_scenes}

描述要包含：
1. 整体情绪氛围
2. 节奏感受
3. 配器带来的画面感
4. 最适合的 2-3 种视频场景

输出：纯描述文字，不要分段，不要标号。
```

---

### Phase 2: 视频理解层升级 — 音乐想象描述

**目标**：视频分析输出从结构化 JSON 升级为「音乐想象描述」+ 结构化需求

**改动文件**：
- `prompts/semantic.txt` — 重写 prompt，输出 music_imagination
- `models/schemas.py` — 新增 MusicImagination 模型
- `routers/analyze.py` — normalize_semantic 适配新输出

**MusicImagination 模型**：
```python
class MusicImagination(BaseModel):
    description: str  # 100 字以内自然语言描述
    target_emotion: dict  # 8 维情绪需求
    bpm_range: list  # [min, max]
    vocal_ok: bool  # 是否适合有人声
    culture_preference: str  # 文化风格倾向
    avoid: list  # 必须避免的风格
    reference_tracks: list  # 参照曲（如果有）
```

**Semantic.txt 新 prompt 核心**：
```
你是专业视频配乐分析师，也是一位经验丰富的剪辑师。
请分析这段视频，输出「这段视频需要的音乐想象」。

输出：
1. 音乐想象描述（100 字以内）：用自然语言描述这段视频"应该"配什么样的音乐
2. 结构化需求：目标情绪、BPM范围、人声、文化风格、避免项
3. 参照曲（如果有）
```

---

### Phase 3: Embedding 检索引擎

**目标**：用 embedding 向量库替代现有的情绪向量检索

**改动文件**：
- `services/embedding_search.py`（新建）— Chroma 向量检索服务
- `services/bgm_matcher.py` — 重写匹配逻辑

**实现步骤**：
1. `EmbeddingSearcher` 类：
   - 初始化 Chroma 持久化目录（`D:/video-bgm-data/chroma_db`）
   - 加载 sentence-transformers 模型
   - `add_track(track_id, description, metadata)` — 添加歌曲到 Chroma
   - `search(query_text, top_k=8, where_filter=None)` — 语义检索
   - `remove_track(track_id)` — 删除歌曲
2. `BGMMatcher.match()` 重写：
   - 第一步：用 music_imagination.description 做 embedding 检索（粗排，Top-8）
   - 第二步：用结构化标签做辅助过滤（人声、文化、场景）
   - 第三步：Agent 精排（评估适配度 + 起始位置）
   - 第四步：冲突检测 + 音量调整

**检索流程**：
```
视频音乐想象描述 → sentence-transformers 编码 → 向量
    ↓ 余弦相似度
BGM 描述向量库 → Top-8 候选
    ↓ 标签过滤
剩余候选 → Agent 精排 → Top-3 推荐
```

---

### Phase 4: 精排 Agent — 适配度评估 + 起始位置

**目标**：推荐输出包含适配度评分、推荐理由、起始位置建议

**改动文件**：
- `prompts/rerank.txt`（新建）— 精排 prompt
- `services/rerank_agent.py`（新建）— 精排 agent
- `models/schemas.py` — BGMRecommendation 新增字段

**BGMRecommendation 新增字段**：
```python
class BGMRecommendation(BaseModel):
    # 现有字段保留
    bgm: BGMTrack
    match_score: float
    reason: str
    # 新增字段
    start_sec: int = 0  # 建议起始位置
    emotion_match: bool = True
    rhythm_match: bool = True
    vocal_conflict: bool = False
    score_detail: dict = {}  # 各维度评分
```

**精排 Prompt**：
```
你是一位经验丰富的剪辑师。以下视频需要配 BGM，
请逐首评估候选歌曲的适配度。

视频音乐想象：[description]
结构化需求：BPM [X-Y]，人声 [可接受/不可接受]，文化 [X]

候选歌曲：
1. [歌名] - [描述] | 人声：[有/无] | intro：[X]秒

请评估每首：
1. 情绪匹配？理由
2. 节奏协调？理由
3. 人声冲突？理由
4. 综合适配度（1-5，可带0.5）
5. 建议起始位置（秒）+ 理由
```

---

### Phase 5: 端到端测试 + 前端适配

**目标**：完整测试流程，适配前端展示

**改动文件**：
- `tests/test_e2e.py`（新建）— 端到端测试
- 前端适配（新增推荐理由、起始位置展示）

**测试流程**：
1. 上传测试视频
2. 视频分析 → 输出音乐想象描述
3. Embedding 检索 → Top-8 候选
4. 精排 → Top-3 推荐 + 起始位置
5. 对话调整 → "换一个安静点的" → 新推荐

---

## 实现顺序

| 阶段 | 任务 | 依赖 | 预估时间 |
|------|------|------|----------|
| Phase 1 | BGM 库升级（描述 + embedding + Chroma） | 无 | 2-3 小时 |
| Phase 2 | 视频理解层升级 | 无 | 1-2 小时 |
| Phase 3 | Embedding 检索引擎 | Phase 1 | 2-3 小时 |
| Phase 4 | 精排 Agent | Phase 2, 3 | 2-3 小时 |
| Phase 5 | 端到端测试 + 前端适配 | 全部 | 1-2 小时 |

**总预估**：8-13 小时

**延后**：对话式调整层（Phase 5 原计划）后续迭代

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Embedding 模型 | sentence-transformers `all-MiniLM-L6-v2` | 本地运行，384维，中文支持好 |
| 向量存储 | Chroma（本地持久化） | 一步到位，支持增量添加，后续扩充无需迁移 |
| 视频分析 | MiMo V2 Omni（现有） | 已验证可用 |
| 精排 Agent | MiMo V2 Omni（文本模式） | 需要理解能力 |
| 对话调整 | MiMo V2 Omni（文本模式） | 需要理解用户意图 |

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| MiMo API 不稳定 | 描述生成和精排失败 | 重试机制 + 批量处理 |
| 11 首歌库太小 | embedding 优势不明显 | 先跑通流程，后续扩充 |
| Chroma 依赖安装 | Windows 上可能有编译问题 | 使用 pip install chromadb，纯 Python 实现 |
| 前端适配工作量 | 推荐展示需要改 | 先 API 跑通，前端后做 |
