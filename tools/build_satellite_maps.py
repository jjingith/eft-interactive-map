#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 tarkov.dev 的卫星瓦片预拼成本地底图（离线可用）。

数据源：
  build-cache/tarkovdev-maps-config.json（tarkov.dev 的 src/data/maps.json）
  每个图条目里的 tilePath = https://assets.tarkov.dev/maps/.../{z}/{x}/{y}.png

做法（与枫织客户端的卫星模式一致）：
  - 固定取 zoom 3（客户端 Bbe 也是 3）；
  - 用 bounds + transform + coordinateRotation 计算四角在瓦片像素上的范围；
  - 下载该范围内的全部 256px 瓦片，拼成一张 canvas；
  - 再把 canvas 像素坐标 → 本项目 SVG 坐标的仿射矩阵算出来，运行时直接贴到 #map-svg 里。

输出：
  data/satellite.json
  assets/satellite/<地图 key>.webp

用法：
  python tools/build_satellite_maps.py
  python tools/build_satellite_maps.py --maps customs,interchange
  python tools/build_satellite_maps.py --force
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import math
import os
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "build-cache", "tarkovdev-maps-config.json")
MAPS = os.path.join(ROOT, "data", "maps.json")
OUT_JSON = os.path.join(ROOT, "data", "satellite.json")
OUT_DIR = os.path.join(ROOT, "assets", "satellite")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
ZOOM = 3
TILE = 256


def project(pt, rotation, tf, scale):
    """世界坐标 → 瓦片像素（和客户端 Hbe 同一公式）。"""
    x, y = pt
    a = math.radians(rotation or 0)
    rx = x * math.cos(a) - y * math.sin(a)
    ry = x * math.sin(a) + y * math.cos(a)
    return ((rx * tf[0] + tf[1]) * scale, (ry * -tf[2] + tf[3]) * scale)


def solve3(pts, vals):
    """三点解 [a,b,c]，使 a*u + b*v + c = val。"""
    (u1, v1), (u2, v2), (u3, v3) = pts
    d = (u1 - u3) * (v2 - v3) - (u2 - u3) * (v1 - v3)
    if abs(d) < 1e-8:
        raise ValueError("三点共线，无法拟合")
    a = ((vals[0] - vals[2]) * (v2 - v3) - (vals[1] - vals[2]) * (v1 - v3)) / d
    b = ((u1 - u3) * (vals[1] - vals[2]) - (u2 - u3) * (vals[0] - vals[2])) / d
    c = vals[2] - a * u3 - b * v3
    return a, b, c


def make_matrix(world_pts, canvas_pts, svg_pts):
    ax, bx, cx = solve3(canvas_pts, [p[0] for p in svg_pts])
    ay, by, cy = solve3(canvas_pts, [p[1] for p in svg_pts])
    # SVG matrix(a b c d e f): x' = a*u + c*v + e, y' = b*u + d*v + f
    return [round(ax, 6), round(ay, 6), round(bx, 6), round(by, 6), round(cx, 3), round(cy, 3)]


def fetch_tile(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read()


def build_one(key, cfg, map_rec):
    entry = next((v for v in cfg.get("maps", []) if v.get("tilePath")), None)
    if not entry:
        return None
    bounds = entry["bounds"]
    rot = entry.get("coordinateRotation") or 0
    tf = entry["transform"]
    z = min(entry.get("maxZoom", ZOOM), max(entry.get("minZoom", 0), ZOOM))
    scale = 2 ** z
    pts = [project(p, rot, tf, scale) for p in bounds]
    min_x = min(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    width = math.ceil(max(p[0] for p in pts) - min_x)
    height = math.ceil(max(p[1] for p in pts) - min_y)
    if width <= 0 or height <= 0:
        return None

    max_tile = 2 ** z - 1
    x0 = max(0, math.floor(min_x / TILE))
    x1 = min(max_tile, math.floor((min_x + width - 1) / TILE))
    y0 = max(0, math.floor(min_y / TILE))
    y1 = min(max_tile, math.floor((min_y + height - 1) / TILE))
    jobs = []
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            url = entry["tilePath"].replace("{z}", str(z)).replace("{x}", str(tx)).replace("{y}", str(ty))
            jobs.append((tx, ty, url))
    print("   ", key, "canvas", width, "x", height, "tiles", len(jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_tile, j[2]): j for j in jobs}
        images = {}
        for fut in concurrent.futures.as_completed(futs):
            tx, ty, url = futs[fut]
            try:
                images[(tx, ty)] = Image.open(io.BytesIO(fut.result())).convert("RGBA")
            except Exception:
                pass
    if not images:
        print("   ", key, "没有可用瓦片")
        return None
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for (tx, ty), im in images.items():
        canvas.paste(im, (round(tx * TILE - min_x), round(ty * TILE - min_y)))
    out = os.path.join(OUT_DIR, key + ".webp")
    canvas.convert("RGB").save(out, "WEBP", quality=88, method=6)
    print("   ", key, "->", out, round(os.path.getsize(out) / 1048576, 2), "MB")

    world_pts = [bounds[0], bounds[1], [bounds[0][0], bounds[1][1]]]
    canvas_pts = [(p[0] - min_x, p[1] - min_y) for p in
                  [project(q, rot, tf, scale) for q in world_pts]]
    w2s = map_rec["worldToSvg"]
    svg_pts = [(w2s["a"] * q[0] + w2s["b"] * q[1] + w2s["c"],
                w2s["d"] * q[0] + w2s["e"] * q[1] + w2s["f"]) for q in world_pts]
    matrix = make_matrix(world_pts, canvas_pts, svg_pts)
    return {
        "image": os.path.relpath(out, ROOT).replace("\\", "/"),
        "width": width, "height": height,
        "matrix": matrix, "zoom": z,
        "tilePath": entry["tilePath"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(CONFIG):
        raise SystemExit("缺少 %s；先跑 tools/fetch_data.py 生成缓存" % CONFIG)
    config = {m["normalizedName"]: m for m in json.load(open(CONFIG, encoding="utf-8"))}
    maps_doc = json.load(open(MAPS, encoding="utf-8"))["maps"]
    os.makedirs(OUT_DIR, exist_ok=True)
    keys = [k for k in a.maps.split(",") if k] if a.maps else [m["key"] for m in maps_doc]
    old = json.load(open(OUT_JSON, encoding="utf-8")) if os.path.exists(OUT_JSON) and not a.force else {}
    out = {"schema": 1,
           "source": "tarkov.dev maps tiles（https://assets.tarkov.dev/maps/，社区公开数据；非商业使用）",
           "zoom": ZOOM, "tileSize": TILE, "maps": old.get("maps", {})}
    for key in keys:
        if key in out["maps"] and not a.force:
            continue
        cfg = config.get(key)
        rec = next((m for m in maps_doc if m["key"] == key), None)
        if not cfg or not rec:
            print("跳过", key)
            continue
        print("构建", key)
        item = build_one(key, cfg, rec)
        if item:
            out["maps"][key] = item
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("写出", OUT_JSON, round(os.path.getsize(OUT_JSON) / 1024, 1), "KB，",
          len(out["maps"]), "张卫星底图")


if __name__ == "__main__":
    main()
