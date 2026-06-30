"""
方案 A 验收测试：Agent 多轮对话 + 流式 SSE
"""
import httpx, json, asyncio, sys, re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


async def collect_sse(client, url, json_data, timeout=300.0):
    """发送请求并收集所有 SSE 事件"""
    events = []
    async with client.stream("POST", url, json=json_data, timeout=httpx.Timeout(timeout)) as resp:
        print(f"  Status: {resp.status_code}", flush=True)
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)
                        etype = event.get("type", "?")
                        if etype == "tool_call":
                            print(f"  ⚙ Tool: {event['tool']}", flush=True)
                        elif etype == "tool_result":
                            r = event.get("result", {})
                            err = r.get("error", "")
                            if err:
                                print(f"  ⚠ Result: {event['tool']} error: {err}", flush=True)
                            else:
                                n = len(r.get("candidates", r.get("recommendations", [])))
                                print(f"  ✓ Result: {event['tool']} ({n} items)", flush=True)
                        elif etype == "final":
                            print(f"  ✓ Final ({len(event.get('recommendations', []))} recs)", flush=True)
                        elif etype == "error":
                            print(f"  ✗ Error: {event.get('message', '')}", flush=True)
                    except json.JSONDecodeError:
                        pass
    return events


async def test_1_full_flow():
    """测试1: 上传 → Agent 全流程分析"""
    print("\n" + "=" * 50)
    print("测试1: 上传 → Agent 全流程分析")
    print("=" * 50)

    base = "http://localhost:8000"
    async with httpx.AsyncClient() as client:
        # Upload
        video_path = "D:/projects/web-demo/feed-video.mp4"
        with open(video_path, "rb") as f:
            resp = await client.post(base + "/api/upload", files={"video": ("test.mp4", f, "video/mp4")})
        assert resp.status_code == 200, f"Upload failed: {resp.status_code}"
        upload = resp.json()
        print(f"  Upload OK: video_id={upload['video_id']}")

        # Agent analyze
        events = await collect_sse(
            client, base + "/api/agent/analyze",
            {"video_id": upload["video_id"], "file_path": upload["file_path"]},
        )

    # 验证
    finals = [e for e in events if e["type"] == "final"]
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    errors = [e for e in events if e["type"] == "error"]

    assert not errors, f"有错误事件: {errors}"
    assert len(finals) == 1, f"应有1个final事件, 实际 {len(finals)}"
    assert len(finals[0].get("recommendations", [])) > 0, "应有推荐结果"
    # 应至少调用 analyze_video + search_bgm + score_and_rank
    called_tools = {t["tool"] for t in tool_calls}
    assert "analyze_video" in called_tools, "缺少 analyze_video"
    assert "search_bgm" in called_tools, "缺少 search_bgm"
    assert "score_and_rank" in called_tools, "缺少 score_and_rank"
    # 不应自动调用 adjust_volume 或 detect_conflict
    assert "adjust_volume" not in called_tools, "不应自动调用 adjust_volume"
    assert "detect_conflict" not in called_tools, "不应自动调用 detect_conflict"

    print(f"\n  ✓ 测试1通过: {len(tool_calls)} 个工具调用, "
          f"final包含 {len(finals[0]['recommendations'])} 个推荐")
    return events


async def test_2_multi_turn_change():
    """测试2: 多轮对话 — 换一首"""
    print("\n" + "=" * 50)
    print("测试2: 多轮对话 — 换一首")
    print("=" * 50)

    base = "http://localhost:8000"
    async with httpx.AsyncClient() as client:
        # Upload
        with open("D:/projects/web-demo/feed-video.mp4", "rb") as f:
            resp = await client.post(base + "/api/upload", files={"video": ("test.mp4", f, "video/mp4")})
        upload = resp.json()

        # Agent analyze
        events = await collect_sse(
            client, base + "/api/agent/analyze",
            {"video_id": upload["video_id"], "file_path": upload["file_path"]},
        )

    finals = [e for e in events if e["type"] == "final"]
    assert len(finals) == 1
    session_id = finals[0].get("session_id", "")
    assert session_id, "缺少 session_id"
    first_recs = finals[0].get("recommendations", [])
    first_titles = {r["title"] for r in first_recs}
    print(f"  首批推荐: {first_titles}")

    # 多轮对话: "换一首"
    print("\n  → 发送: 换一首")
    async with httpx.AsyncClient() as client:
        events2 = await collect_sse(
            client, base + "/api/agent/chat",
            {"session_id": session_id, "message": "换一首"},
        )

    finals2 = [e for e in events2 if e["type"] == "final"]
    tool_calls2 = [e for e in events2 if e["type"] == "tool_call"]
    errors2 = [e for e in events2 if e["type"] == "error"]

    assert not errors2, f"有错误事件: {errors2}"
    assert len(finals2) == 1, f"应有1个final事件, 实际 {len(finals2)}"
    second_recs = finals2[0].get("recommendations", [])
    second_titles = {r["title"] for r in second_recs}
    called_tools2 = {t["tool"] for t in tool_calls2}

    # "换一首" 不应重新分析视频
    assert "analyze_video" not in called_tools2, \
        f'「换一首」不应重新analyze_video, 实际调用了: {called_tools2}'
    # 应该有推荐
    assert len(second_recs) > 0, '「换一首」应有推荐结果'

    print(f"  换一批推荐: {second_titles}")
    print(f"  调用的工具: {called_tools2}")
    print(f"  ✓ 测试2通过")


async def test_3_multi_turn_mood():
    """测试3: 多轮对话 — 指定情绪"""
    print("\n" + "=" * 50)
    print("测试3: 多轮对话 — 换一首更治愈的风格")
    print("=" * 50)

    base = "http://localhost:8000"
    async with httpx.AsyncClient() as client:
        # Upload
        with open("D:/projects/web-demo/feed-video.mp4", "rb") as f:
            resp = await client.post(base + "/api/upload", files={"video": ("test.mp4", f, "video/mp4")})
        upload = resp.json()

        # Agent analyze
        events = await collect_sse(
            client, base + "/api/agent/analyze",
            {"video_id": upload["video_id"], "file_path": upload["file_path"]},
        )

    finals = [e for e in events if e["type"] == "final"]
    session_id = finals[0].get("session_id", "")

    # 多轮对话: 指定情绪
    print("\n  → 发送: 换一首更治愈的")
    async with httpx.AsyncClient() as client:
        events3 = await collect_sse(
            client, base + "/api/agent/chat",
            {"session_id": session_id, "message": "换一首更治愈的，要纯音乐"},
        )

    finals3 = [e for e in events3 if e["type"] == "final"]
    tool_calls3 = [e for e in events3 if e["type"] == "tool_call"]
    errors3 = [e for e in events3 if e["type"] == "error"]

    assert not errors3, f"有错误事件: {errors3}"
    assert len(finals3) == 1, f"应有1个final事件"
    assert len(finals3[0].get("recommendations", [])) > 0, "应有推荐结果"

    third_recs = finals3[0]["recommendations"]
    third_titles = {r["title"] for r in third_recs}
    called_tools3 = {t["tool"] for t in tool_calls3}

    # 不应重新分析视频
    assert "analyze_video" not in called_tools3, \
        f"指定情绪不应重新analyze_video, 实际调用了: {called_tools3}"

    # 应有 search_bgm（带情绪参数）
    assert "search_bgm" in called_tools3, "指定情绪应调用 search_bgm"

    print(f"  推荐结果: {third_titles}")
    print(f"  调用的工具: {called_tools3}")
    print(f"  ✓ 测试3通过")


async def main():
    print("方案A 验收测试套件", flush=True)
    print(f"后端: http://localhost:8000", flush=True)

    tests = [
        ("全流程分析", test_1_full_flow),
        ("多轮对话换一首", test_2_multi_turn_change),
        ("多轮对话指定情绪", test_3_multi_turn_mood),
    ]

    passed = 0
    for name, fn in tests:
        try:
            await fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ 测试失败: {e}", flush=True)
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 50)
    print(f"结果: {passed}/{len(tests)} 通过")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
