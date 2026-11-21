"""从 db4tarkov 下载任务封面图（公开 CDN），供「任务列表」页签使用。

来源：https://cdn.db4tarkov.com/task/<taskId>.webp（与 db4tarkov Quest 页左侧卡片一致）
处理：等比缩小到最大 360px 宽、WEBP 78，保存到 assets/task-images/<taskId>.webp
产物：data/task-images.json（taskId → 本地路径）

用法：python tools/fetch_db4_task_images.py
"""

import concurrent.futures as futures
import io
import json
import os
import time
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "task-images")
MANIFEST = os.path.join(DATA, "task-images.json")
URL = "https://cdn.db4tarkov.com/task/%s.webp"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eft-interactive-map/1.0",
      "Referer": "https://db4tarkov.com/"}
MAX_W = 360
QUALITY = 78
WORKERS = 8


def fetch(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as resp:
                ctype = resp.headers.get("Content-Type") or ""
                if "image" not in ctype:
                    raise RuntimeError("非图片：" + ctype)
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise last


def save_one(task_id):
    try:
        raw = fetch(URL % task_id)
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        if img.width > MAX_W:
            h = round(img.height * MAX_W / img.width)
            img = img.resize((MAX_W, h), Image.LANCZOS)
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, task_id + ".webp")
        img.save(path, "WEBP", quality=QUALITY, method=4)
        return task_id, os.path.relpath(path, ROOT).replace("\\", "/"), os.path.getsize(path)
    except Exception:  # noqa: BLE001
        return task_id, None, 0


def main():
    ids = []
    for mode in ("regular", "pve", "pvps"):
        path = os.path.join(DATA, "tasks", "tasks.%s.json" % mode)
        if not os.path.exists(path):
            continue
        for task in (json.load(open(path, encoding="utf-8")).get("tasks") or {}).values():
            tid = task.get("id")
            if tid and tid not in ids:
                ids.append(tid)
    print("tasks", len(ids))
    manifest = {"schema": 1,
                "source": "https://cdn.db4tarkov.com/task/<taskId>.webp（db4tarkov 公开 CDN）",
                "note": "任务封面图来自 db4tarkov，版权归原作者；构建期下载，运行期离线",
                "images": {}}
    started = time.time()
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(save_one, ids))
    ok = 0
    total = 0
    for tid, rel, size in results:
        if rel:
            manifest["images"][tid] = rel
            ok += 1
            total += size
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, separators=(",", ":"))
    print("完成：%d / %d 张，%.1f MB，%.1fs → %s" % (
        ok, len(ids), total / 1024 / 1024, time.time() - started, MANIFEST))


if __name__ == "__main__":
    main()
