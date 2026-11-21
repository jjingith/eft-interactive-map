# -*- coding: utf-8 -*-
"""构建期工具（R19.3）：生成「完整枪械」图像。

要解决的问题
------------
`assets/icons-items/{gunId}.webp` 是枪械**本体**（receiver）的展示图：EFT 里枪托、握把、
枪管等是可拆的独立 mod，本体图只渲染机匣 + 枪管 + 弹匣，所以在浏览卡片和装配摘要里
看起来"像一把没有枪托的机匣"。

真正的完整枪械渲染在**预设（Preset）**上：tarkov.dev 为每个官方预设渲染了整枪
（`{presetId}-base-image.webp`，透明底）。R18.2 已经用 AK-74 默认预设验证过这一点
（316×127 含木托，本体图 253×64 截断在机匣尾）。

做法
----
1. 每把枪取 `data/gun-stats.json` 记录的 `defaultPreset`；另外把
   `data/gun-presets.json` 里该枪的**全部**官方预设也出图（工作台做"装配 == 官方预设"
   精确匹配时可以直接换成那张真实渲染，而不是假装合成）；
2. 构建期按需下载到 `build-cache/gun-images-src/{presetId}.webp`（增量，已存在跳过）；
3. Alpha 裁包围盒 → 等比缩放到高 112px（长枪不超宽 400px）→ 输出透明底 PNG
   到 `assets/guns-full/{gunId}.png`（默认预设）与 `assets/presets-full/{presetId}.png`；
4. manifest 记录每个 gun→preset 的映射、源 URL、原始尺寸、alpha 覆盖率。

运行期零联网：前端只读本地 PNG，缺失时回退到原 64px 物品图标。

用法：
    python tools/build_gun_images.py            # 增量构建
    python tools/build_gun_images.py --verify    # 只校验，不联网
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS = os.path.join(ROOT, "data", "gun-stats.json")
PRESETS = os.path.join(ROOT, "data", "gun-presets.json")
GUNSLOTS = os.path.join(ROOT, "data", "gunslots.json")
OUT_GUN = os.path.join(ROOT, "assets", "guns-full")
OUT_PRESET = os.path.join(ROOT, "assets", "presets-full")
SRC = os.path.join(ROOT, "build-cache", "gun-images-src")
MANIFEST = os.path.join(ROOT, "assets", "guns-full", "manifest.json")

BASE_URL = "https://assets.tarkov.dev/{id}-base-image.webp"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:7896"

TARGET_H = 112
MAX_W = 400
ALPHA_CUT = 16


def fetch(preset_id):
    dst = os.path.join(SRC, "%s.webp" % preset_id)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst, "cached", None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    opener.addheaders = [("User-Agent", UA), ("Referer", "https://tarkov.dev/")]
    try:
        with opener.open(BASE_URL.format(id=preset_id), timeout=30) as r:
            data = r.read()
        if not data:
            return None, "empty", None
        os.makedirs(SRC, exist_ok=True)
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
        return dst, "downloaded", None
    except Exception as exc:                    # noqa: BLE001 - 单件失败不阻断
        return None, "failed", str(exc)[:160]


def convert(src_path):
    im = Image.open(src_path).convert("RGBA")
    orig = im.size
    alpha = im.split()[3].point(lambda a: 0 if a < ALPHA_CUT else a)
    bbox = alpha.getbbox()
    if not bbox:
        return None, {"reason": "Alpha 全透明"}
    subject = im.crop(bbox)
    sw, sh = subject.size
    scale = min(TARGET_H / float(sh), MAX_W / float(sw))
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    out = subject.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    canvas.paste(out, (0, 0), out)
    return canvas, {"origSize": [orig[0], orig[1]], "bbox": list(bbox),
                    "size": [nw, nh], "aspect": round(nw / float(nh), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    stats = json.load(open(STATS, encoding="utf-8"))["guns"]
    presets = json.load(open(PRESETS, encoding="utf-8"))["presets"]
    guns = json.load(open(GUNSLOTS, encoding="utf-8"))["guns"]

    # gun -> 默认预设；preset -> 归属枪
    gun_default = {}
    for gid in guns:
        pid = (stats.get(gid) or {}).get("preset")
        if pid and pid in presets:
            gun_default[gid] = pid
    gun_presets = {}
    for pid, pr in presets.items():
        g = pr.get("g")
        if g in guns:
            gun_presets.setdefault(g, []).append(pid)

    need = sorted(set(gun_default.values()) | {p for ps in gun_presets.values() for p in ps})
    print("枪械 %d 把，默认预设 %d 张，官方预设合计 %d 张，需下载/转换 %d 张"
          % (len(guns), len(gun_default), sum(len(v) for v in gun_presets.values()), len(need)))

    if not a.verify:
        os.makedirs(OUT_GUN, exist_ok=True)
        os.makedirs(OUT_PRESET, exist_ok=True)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            list(pool.map(fetch, need))

    rows, missing = [], []
    preset_rows = {}
    for pid in need:
        src = os.path.join(SRC, "%s.webp" % pid)
        if not os.path.exists(src):
            missing.append({"presetId": pid, "reason": "源图缺失（下载失败）"})
            continue
        img, meta = convert(src)
        if img is None:
            missing.append({"presetId": pid, "reason": meta.get("reason", "转换失败")})
            continue
        if not a.verify:
            img.save(os.path.join(OUT_PRESET, "%s.png" % pid))
        preset_rows[pid] = meta

    for gid, pid in gun_default.items():
        meta = preset_rows.get(pid)
        if not meta:
            continue
        if not a.verify:
            src = os.path.join(OUT_PRESET, "%s.png" % pid)
            img = Image.open(src)
            img.save(os.path.join(OUT_GUN, "%s.png" % gid))
        rows.append({
            "gunId": gid,
            "gunName": (guns[gid] or {}).get("n", ""),
            "presetId": pid,
            "presetName": (presets[pid] or {}).get("n", ""),
            "file": "assets/guns-full/%s.png" % gid,
            "source": BASE_URL.format(id=pid),
            "size": meta["size"],
            "aspect": meta["aspect"],
            "origSize": meta["origSize"],
            "otherPresets": len(gun_presets.get(gid, [])),
        })

    out = {
        "schema": 1,
        "round": "R19.3",
        "source": BASE_URL,
        "note": ("完整枪械图 = 官方预设渲染（含枪托/握把/弹匣等完整装配），"
                 "不是本体机匣图，也不是把配件图标叠出来的合成图。"),
        "counts": {"guns": len(guns), "withDefaultPreset": len(gun_default),
                   "presetsRendered": len(preset_rows), "missing": len(missing)},
        "items": rows,
        "missing": missing,
    }
    if not a.verify:
        json.dump(out, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("输出：%d 把枪的完整图 + %d 张预设图，缺失 %d 张"
          % (len(rows), len(preset_rows), len(missing)))
    for m in missing[:10]:
        print("  [缺失]", m["presetId"], m["reason"])


if __name__ == "__main__":
    sys.exit(main())
