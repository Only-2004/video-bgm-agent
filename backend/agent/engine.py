"""
Agent 核心引擎 — LLM Function Calling 主循环

流程:
  user_input → LLM(思考) → tool_call → execute → LLM(再思考) → ... → final response

输出:
  async generator, 每次 yield {"type": "tool_call" | "final", ...} 供 SSE 流式推送
"""
import asyncio
import json
import os
import uuid
import httpx
from typing import Any, AsyncGenerator, Optional
from agent.prompts import SYSTEM_PROMPT, TOOL_DEFINITIONS
from agent.tools import execute_tool

# ──────────────────────────────────────────
# 配置
# ──────────────────────────────────────────
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "sk-CpfQyqJEPcd5JPbDHEjG3MIlmbKoJwka")
MIMO_API_URL = os.getenv("MIMO_API_URL", "https://ai.iapp.dpdns.org/v1/chat/completions")
MODEL = "mimo-v2.5"

MAX_TOOL_ROUNDS = 10  # 短路保护


class AgentEngine:
    """FC Agent 引擎，每个 session 一个实例"""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.context: dict = {}  # 共享上下文（video_path, analysis_id 等）

    def to_dict(self) -> dict:
        """序列化引擎状态，用于 DB 持久化"""
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentEngine":
        """从已保存的状态重建引擎"""
        engine = cls(session_id=data.get("session_id"))
        engine.messages = data.get("messages", [])
        engine.context = data.get("context", {})
        return engine

    # ──────────────────────────────────────
    # 公开 API
    # ──────────────────────────────────────

    async def run(self, user_input: str, context: Optional[dict] = None) -> AsyncGenerator[dict, None]:
        """
        主入口：接收用户输入，运行 FC 循环，流式产出事件。

        yield 事件格式：
          {"type": "tool_call",  "tool": name, "args": args, "result": result}
          {"type": "final",      "content": str, "recommendations": [...]}
          {"type": "error",      "message": str}
        """
        if context:
            self.context.update(context)

        # 将上下文信息注入用户消息
        enriched_input = user_input
        if self.context.get("file_path"):
            enriched_input = f"{user_input}\n\n视频文件路径: {self.context['file_path']}"
        if self.context.get("session_id"):
            enriched_input += f"\n会话ID: {self.context['session_id']}"

        self.messages.append({"role": "user", "content": enriched_input})

        for _round in range(MAX_TOOL_ROUNDS):
            try:
                response = await self._call_llm()
            except Exception as e:
                yield {"type": "error", "message": f"LLM 调用失败: {str(e)}"}
                return

            # 检查是否有 tool_call
            tool_calls = response.get("tool_calls") or []

            if not tool_calls:
                # LLM 返回纯文本 → 最终回复
                content = response.get("content", "")
                yield {
                    "type": "final",
                    "content": content,
                    "recommendations": self.context.get("recommendations", []),
                }
                return

            # 执行工具调用（可能有多个并行）
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # yield tool_call 事件（前端展示进度）
                yield {"type": "tool_call", "tool": name, "args": args}

                # 执行
                result = await execute_tool(name, args)

                # 将结果存入上下文和共享状态
                if name == "analyze_video":
                    self.context["video_analysis"] = result
                    analysis_id = self.context.get("analysis_id") or f"agent_{self.session_id}"
                    self.context["video_analysis_id"] = analysis_id
                    from agent.tools import analysis_tasks
                    analysis_tasks[analysis_id] = result
                elif name == "search_bgm":
                    candidates = result.get("candidates", [])
                    self.context["last_search_results"] = candidates
                    # 自动传入 score_and_rank
                    if candidates and self.context.get("video_analysis_id"):
                        self.context["candidate_ids"] = [c["bgm_id"] for c in candidates]
                elif name == "score_and_rank":
                    recs = result.get("recommendations", [])
                    self.context["recommendations"] = recs
                    if recs:
                        self.context["last_recommendations"] = recs
                elif name == "adjust_volume" and result.get("volume_adjustments"):
                    self.context.setdefault("volume_adjustments", {})
                    self.context["volume_adjustments"][result.get("bgm_id", "")] = result["volume_adjustments"]
                elif name == "detect_conflict" and result.get("has_conflict"):
                    self.context.setdefault("conflicts", [])
                    self.context["conflicts"].append(result)

                # yield result 事件
                yield {"type": "tool_result", "tool": name, "result": result}

                # 把 tool_call + result 追加到 messages
                self.messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", f"call_{_round}"),
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }],
                })
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{_round}"),
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # 超过最大轮数
        yield {
            "type": "final",
            "content": "我已经完成了分析，以上是为您推荐的配乐方案。如需调整，请告诉我。",
            "recommendations": self.context.get("recommendations", []),
        }

    async def chat(self, user_input: str) -> AsyncGenerator[dict, None]:
        """多轮对话入口"""
        async for event in self.run(user_input):
            yield event

    # ──────────────────────────────────────
    # LLM 调用
    # ──────────────────────────────────────

    async def _call_llm(self) -> dict:
        """调用 mimo-v2.5 LLM，失败时重试 1 次（仅 5xx 和超时）"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MIMO_API_KEY}",
        }

        payload = {
            "model": MODEL,
            "messages": self.messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "max_tokens": 4000,
        }

        max_attempts = 2
        last_exception = None

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    resp = await client.post(MIMO_API_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                choice = data["choices"][0]
                message = choice["message"]

                return {
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                }

            except httpx.TimeoutException as e:
                last_exception = e
                print(f"[AgentEngine] LLM 超时 (attempt {attempt+1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                    continue
                raise

            except httpx.HTTPStatusError as e:
                last_exception = e
                print(f"[AgentEngine] LLM HTTP {e.response.status_code} (attempt {attempt+1}/{max_attempts})")
                if attempt < max_attempts - 1 and e.response.status_code >= 500:
                    await asyncio.sleep(2)
                    continue
                raise

            except Exception as e:
                last_exception = e
                print(f"[AgentEngine] LLM 错误 (attempt {attempt+1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                    continue
                raise