"""
BGM 自然语言描述生成工具 — MiMo 为每首歌生成 50-100 字描述

用法：
  python tools/bgm_describer.py --limit 5    # 生成前5首
  python tools/bgm_describer.py --force       # 强制重新生成
  python tools/bgm_describer.py --id bgm_xxx  # 生成指定歌曲
"""

import argparse
import json
import os
import sys
import time

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "../prompts/bgm_description.txt")

MIMO_API_KEY = "sk-CpfQyqJEPcd5JPbDHEjG3MIlmbKoJwka"
MIMO_API_URL = "https://ai.iapp.dpdns.org"


def load_prompt() -> str:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def call_mimo(prompt: str, retries: int = 5) -> str:
    payload = {
        "model": "mimo-v2.5",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    for attempt in range(retries + 1):
        try:
            session = requests.Session()
            response = session.post(
                MIMO_API_URL,
                headers={
                    "x-api-key": MIMO_API_KEY,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                    "Connection": "close",
                },
                json=payload,
                timeout=60,
            )
            session.close()
            response.raise_for_status()
            result = response.json()
            for item in result.get("content", []):
                if item.get("type") == "text":
                    return item["text"]
            return ""
        except Exception as e:
            if attempt < retries:
                time.sleep(5)
                continue
            raise


def generate_description(track: dict, prompt_template: str) -> str:
    et = track.get("emotion_tag", {})
    st = track.get("style_tag", {})
    rt = track.get("rhythm_tag", {})
    scene = track.get("scene_tag", {})

    emo_tags = et.get("tags", [])
    fit_scenes = scene.get("fit", [])

    prompt = prompt_template.format(
        title=track.get("title", "Unknown"),
        artist=track.get("artist", "Unknown"),
        primary_style=st.get("primary", "Unknown"),
        emotion_tags="、".join(emo_tags) if emo_tags else "未知",
        fit_scenes="、".join(fit_scenes[:5]) if fit_scenes else "未知",
        bpm=rt.get("bpm", 0),
        summary=scene.get("summary", ""),
    )

    raw = call_mimo(prompt)
    # 清理 markdown 代码块
    import re
    raw = re.sub(r'```[\s\S]*?```', '', raw).strip()
    raw = re.sub(r'^["\']|["\']$', '', raw).strip()
    return raw


def load_library() -> list:
    if os.path.exists(LIBRARY_PATH):
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("bgm_list", [])
    return []


def save_library(bgm_list: list):
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump({"bgm_list": bgm_list}, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="BGM 自然语言描述生成工具")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 首（0=全部）")
    parser.add_argument("--force", action="store_true", help="强制重新生成")
    parser.add_argument("--id", help="只处理指定 ID 的歌曲")
    args = parser.parse_args()

    prompt_template = load_prompt()
    print(f"Prompt 模板已加载: {PROMPT_PATH}")

    bgm_list = load_library()
    print(f"音乐库: {len(bgm_list)} 首")

    to_process = []
    for track in bgm_list:
        if args.id and track.get("id") != args.id:
            continue
        if not args.force and track.get("description"):
            continue
        to_process.append(track)

    if args.limit > 0:
        to_process = to_process[:args.limit]

    print(f"待生成描述: {len(to_process)} 首")
    print("=" * 50)

    success = 0
    failed = 0

    for i, track in enumerate(to_process):
        title = track.get("title", "?")[:30]
        print(f"  [{i+1}/{len(to_process)}] {title}...", end=" ", flush=True)

        try:
            desc = generate_description(track, prompt_template)
            if not desc or len(desc) < 10:
                failed += 1
                print("FAILED (too short)")
                continue

            track["description"] = desc
            success += 1
            print(f"OK ({len(desc)}字)")

            if (i + 1) % 5 == 0:
                save_library(bgm_list)
                print(f"  --- 已保存 ({i+1}/{len(to_process)}) ---")

            time.sleep(3)

        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")

    save_library(bgm_list)
    print(f"\n{'=' * 50}")
    print(f"完成! 成功: {success} | 失败: {failed} | 总计: {len(bgm_list)}")


if __name__ == "__main__":
    main()
