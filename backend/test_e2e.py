"""端到端测试：上传视频 → 分析 → 匹配BGM"""
import httpx
import time
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:8000"
VIDEO = "D:/projects/backend/uploads/19561aba-9ee2-40b3-9e47-f62e4952b797.mp4"


def main():
    with httpx.Client(timeout=300) as c:
        # 1. 上传
        print("=== 1. 上传视频 ===")
        with open(VIDEO, "rb") as f:
            resp = c.post(f"{BASE}/api/upload", files={"video": ("test.mp4", f, "video/mp4")})
        data = resp.json()
        video_id = data["video_id"]
        file_path = data["file_path"]
        print(f"video_id: {video_id}")

        # 2. 启动分析
        print("\n=== 2. 启动分析 ===")
        resp = c.post(f"{BASE}/api/analyze", json={"video_id": video_id, "file_path": file_path})
        analysis_data = resp.json()
        analysis_id = analysis_data.get("analysis_id") or video_id
        print(f"analysis_id: {analysis_id}")

        # 3. 查询分析结果（POST 是同步的，应该已完成）
        print("\n=== 3. 查询分析结果 ===")
        resp = c.get(f"{BASE}/api/status/{analysis_id}")
        status = resp.json()
        print(f"  status={status.get('status')}")
        if status.get("status") != "completed":
            print(f"  分析未完成: {status.get('error')}")
            return
        print(f"分析完成!")

        # 4. 匹配BGM
        print("\n=== 4. 匹配BGM ===")
        resp = c.post(f"{BASE}/api/match", json={"analysis_id": analysis_id})
        result = resp.json()

        if "detail" in result:
            print(f"错误: {result['detail']}")
            return

        recs = result.get("recommendations", [])
        print(f"推荐数量: {len(recs)}")
        for i, rec in enumerate(recs[:3]):
            bgm = rec.get("bgm", {})
            print(f"\n  [{i+1}] {bgm.get('title', '?')}")
            print(f"      分数: {rec.get('match_score', 0):.3f}")
            print(f"      原因: {rec.get('reason', '')[:100]}")
            print(f"      bidirectional: {rec.get('bidirectional_factor')}")


if __name__ == "__main__":
    main()
