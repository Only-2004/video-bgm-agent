import httpx, json, asyncio, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test_agent():
    base = "http://localhost:8000"

    # 1. Upload
    files = {"video": ("test.mp4", open("D:/projects/web-demo/feed-video.mp4", "rb"), "video/mp4")}
    resp = await httpx.AsyncClient().post(base + "/api/upload", files=files)
    print("Upload:", resp.status_code, flush=True)
    upload = resp.json()
    video_id = upload["video_id"]
    file_path = upload["file_path"]
    print("  video_id:", video_id, flush=True)
    print("  file_path:", file_path, flush=True)

    # 2. Agent analyze
    print("\nAgent analyzing...", flush=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        async with client.stream("POST", base + "/api/agent/analyze",
            json={"video_id": video_id, "file_path": file_path}) as resp:
            print("Agent Status:", resp.status_code, flush=True)
            buffer = ""
            final = None
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            if event["type"] == "tool_call":
                                print("  Tool:", event["tool"], flush=True)
                            elif event["type"] == "final":
                                final = event
                        except Exception as e:
                            pass

            print("\nFinal:", len(final.get("recommendations", [])), "recommendations", flush=True)
            if final:
                recs = final.get("recommendations", [])
                for r in recs[:3]:
                    print("  #%d: %s (score: %s)" % (r["rank"], r["title"], str(r["score"])), flush=True)
                if final.get("content"):
                    content = final["content"]
                    safe = content.encode('utf-8', errors='replace').decode('utf-8')
                    print("\nAgent response:", safe[:500] + "...", flush=True)

asyncio.run(test_agent())
