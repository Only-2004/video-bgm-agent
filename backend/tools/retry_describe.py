"""重试失败的 BGM 描述生成"""

import json
import sys
import time
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LIBRARY_PATH = "D:/video-bgm-data/bgm_library.json"
MIMO_API_KEY = "sk-CpfQyqJEPcd5JPbDHEjG3MIlmbKoJwka"
MIMO_API_URL = "https://ai.iapp.dpdns.org"

PROMPT_TEMPLATE = """你是专业音乐描述专家，请为以下歌曲写一段自然语言描述。

## 歌曲信息
- 歌名：《{title}》
- 艺术家：{artist}
- 风格标签：{style_tags}
- BPM：{bpm}
- 能量值：{energy}
- 人声占比：{vocal_ratio}

## 要求
请写一段 60-100 字的自然语言描述，必须包含：

1. **整体氛围感**（不要只说风格标签，要说"听起来像什么感觉"）
2. **节奏感受**（缓慢/中等/快速，是否有明显 beat）
3. **配器特点**（吉他/钢琴/电子/管弦... 带来的画面感）
4. **最适合的 2-3 种视频场景**（具体，如"城市夜景延时""旅行 Vlog 温情片段"）
5. **是否适合旁白**（人声是否突出，是否会干扰对话）

## 注意
- 不要用"这是一首...风格的歌曲"这种废话开头
- 描述要给「剪辑师」看，不是给音乐评论家看
- 侧重「适合什么画面」，不是「音乐本身好不好听」

## 输出格式
直接输出描述文字，不要分段，不要加歌名，不要加"描述："前缀。"""


def call_mimo(prompt, retries=3):
    payload = {
        "model": "mimo-v2.5",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    headers = {
        "x-api-key": MIMO_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "Connection": "close",
    }
    for attempt in range(retries + 1):
        try:
            with requests.Session() as session:
                resp = session.post(MIMO_API_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            for item in result.get("content", []):
                if item.get("type") == "text":
                    return item["text"].strip()
            return ""
        except Exception as e:
            if attempt < retries:
                wait = 3 * (attempt + 1)
                print(f"  重试 {attempt+1}/{retries}: {e}")
                time.sleep(wait)
            else:
                print(f"  失败: {e}")
                return ""


with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

retry_ids = ["bgm_f33a4d4e", "bgm_b3dd3d1f"]
for track in data["bgm_list"]:
    if track["id"] not in retry_ids:
        continue
    title = track.get("title", "未知")
    artist = track.get("artist", "未知")
    st = track.get("style_tag", {})
    style_tags = ", ".join([st.get("primary", "")] + st.get("sub", []))
    rt = track.get("rhythm_tag", {})

    prompt = PROMPT_TEMPLATE.format(
        title=title, artist=artist, style_tags=style_tags,
        bpm=rt.get("bpm", 0), energy=rt.get("energy", 0.5), vocal_ratio=rt.get("vocal_ratio", 0),
    )
    print(f"重试 {title} ({track['id']})...")
    desc = call_mimo(prompt)
    if desc:
        track["description"] = desc
        print(f"  OK: {desc[:80]}...")
    else:
        print(f"  仍然失败")
    time.sleep(2)

with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("已保存")
