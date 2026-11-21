"""【已停用】把 eftarkov 互动地图上的「赛季通行证文件」点位（含现场图）对齐到本地刷点。

注意：R20.13 起按要求不再随包分发任何第三方截图，本脚本不再参与构建流程，
仅保留其中的地标仿射拟合函数供 ``fetch_eftarkov_tasks.py`` 复用；运行它仍会下载图片。

数据来源：https://www.eftarkov.com/map/<mapId> 页面内嵌的 #map-config。
每个文件点带 x/y（该站 1600×1600 地图舞台像素）、楼层、文字说明和 image_urls。
本脚本用「同名撤离点」最小二乘拟合仿射变换（该站舞台坐标 → 本地 SVG 坐标），
再把文件点换算成世界坐标，就近匹配本地 data/season-documents.json 的刷点。

产物：
  assets/season-docs/<地图 key>/<序号>.webp
  data/season-doc-media.json   （按本地刷点坐标 "x|z" 索引）

用法：
    python tools/fetch_eftarkov_docs.py --limit-maps factory
    python tools/fetch_eftarkov_docs.py
"""

import argparse
import concurrent.futures as futures
import io
import json
import math
import os
import re
import time
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "season-docs")
MEDIA = os.path.join(DATA, "season-doc-media.json")
BASE = "https://www.eftarkov.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eft-interactive-map/1.0"}
MAX_WIDTH = 1280
QUALITY = 80
MATCH_LIMIT = 9.0   # 本地单位（约 1 米/单位）


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=dict(UA, Referer=BASE + "/"))
    last = None
    for attempt in range(3):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as exc:
            last = exc
            time.sleep(0.6 * (attempt + 1))
    raise last


def solve3(rows):
    """最小二乘解 X*a + Y*b + 1*c = V"""
    A = [[0.0] * 3 for _ in range(3)]
    r = [0.0] * 3
    for x, y, v in rows:
        p = (x, y, 1.0)
        for i in range(3):
            r[i] += p[i] * v
            for j in range(3):
                A[i][j] += p[i] * p[j]
    for i in range(3):
        piv = max(range(i, 3), key=lambda k: abs(A[k][i]))
        A[i], A[piv] = A[piv], A[i]
        r[i], r[piv] = r[piv], r[i]
        d = A[i][i]
        for j in range(i, 3):
            A[i][j] /= d
        r[i] /= d
        for k in range(3):
            if k == i:
                continue
            f = A[k][i]
            for j in range(i, 3):
                A[k][j] -= f * A[i][j]
            r[k] -= f * r[i]
    return r


def fit_affine(map_cfg, local_map, doc_type_names):
    """用同名地标（撤离点/转移点/钥匙门/Boss）拟合 舞台坐标 → 本地 SVG 坐标"""
    theirs = {}
    for m in map_cfg.get("markers", []):
        title = m.get("title")
        if not title or m.get("category") in doc_type_names or m.get("marker_type") == "label":
            continue
        theirs.setdefault(title, []).append((float(m["x"]), float(m["y"])))

    c = local_map["worldToSvg"]

    def push(name, layers):
        if not name:
            return
        for key in layers:
            for e in local_map["layers"].get(key, []):
                nm = e.get("keyName") if key == "locks" else e.get("name")
                if nm != name:
                    continue
                sx = c["a"] * e["x"] + c["b"] * e["z"] + c["c"]
                sy = c["d"] * e["x"] + c["e"] * e["z"] + c["f"]
                ours.setdefault(name, []).append((sx, sy))

    ours = {}
    for name in theirs.keys():
        push(name, ("extracts", "transits", "locks", "bosses"))

    pairs = []
    for name, pts in ours.items():
        cand = theirs.get(name)
        if len(pts) == 1 and cand and len(cand) == 1:
            pairs.append((cand[0][0], cand[0][1], pts[0][0], pts[0][1]))
    if len(pairs) < 4:
        return None, len(pairs)

    def fit(ps):
        ax = solve3([(x, y, ox) for x, y, ox, oy in ps])
        ay = solve3([(x, y, oy) for x, y, ox, oy in ps])
        errs = [math.hypot(ax[0] * tx + ax[1] * ty + ax[2] - ox,
                           ay[0] * tx + ay[1] * ty + ay[2] - oy) for tx, ty, ox, oy in ps]
        return (ax, ay), errs

    (ax, ay), errs = fit(pairs)
    # 一轮离群剔除：残差超过中位数 3 倍的点不参与最终拟合
    if len(pairs) >= 6:
        med = sorted(errs)[len(errs) // 2]
        keep = [p for p, e in zip(pairs, errs) if e <= max(med * 3, 6.0)]
        if len(keep) >= 4 and len(keep) != len(pairs):
            pairs = keep
            (ax, ay), errs = fit(pairs)

    errs.sort()
    return (ax, ay, {"pairs": len(pairs), "median": round(errs[len(errs) // 2], 2),
                     "max": round(errs[-1], 2)}), len(pairs)


def stage_to_world(ax, ay, x, y, world):
    sx = ax[0] * x + ax[1] * y + ax[2]
    sy = ay[0] * x + ay[1] * y + ay[2]
    a, b, c = world["a"], world["b"], world["c"]
    d, e, f = world["d"], world["e"], world["f"]
    det = a * e - b * d
    if abs(det) < 1e-9:
        return None
    wx = (e * (sx - c) - b * (sy - f)) / det
    wz = (-d * (sx - c) + a * (sy - f)) / det
    return wx, wz


def fetch_media(url, key, index):
    try:
        raw = fetch(url)
    except Exception:
        return None, 0
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.width > MAX_WIDTH:
        h = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, h), Image.LANCZOS)
    folder = os.path.join(OUT, key)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%02d.webp" % index)
    img.save(path, "WEBP", quality=QUALITY, method=4)
    return os.path.relpath(path, ROOT).replace("\\", "/"), os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-maps")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    maps = json.load(open(os.path.join(DATA, "maps.json"), encoding="utf-8"))["maps"]
    docs = json.load(open(os.path.join(DATA, "season-documents.json"), encoding="utf-8"))
    type_by_item = {t["itemId"]: t["key"] for t in docs["types"]}
    type_names = {t["nameZh"] for t in docs["types"]}

    want = None
    if args.limit_maps:
        want = [s.strip() for s in args.limit_maps.split(",") if s.strip()]

    media = {"schema": 1, "source": BASE + "/map/<mapId>（#map-config）",
             "attribution": "点位现场图来自 eftarkov.com，版权归原作者，仅作离线参考",
             "maps": {}}
    total_imgs = 0
    total_bytes = 0
    started = time.time()

    for lm in maps:
        key = lm["key"]
        if want and key not in want:
            continue
        pack = docs["maps"].get(key)
        if not pack:
            continue
        try:
            html = fetch("%s/map/%s" % (BASE, lm["id"])).decode("utf-8", "replace")
        except Exception as exc:
            print(key, "页面失败:", exc)
            continue
        m = re.search(r'id="map-config"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            print(key, "没有 map-config")
            continue
        cfg = json.loads(m.group(1))

        fit, pairs = fit_affine(cfg, lm, type_names)
        if not fit:
            print("%-16s 仿射拟合失败（同名撤离点仅 %d 个）" % (key, pairs))
            continue
        ax, ay, quality = fit

        our_points = []
        for p in pack["points"]:
            our_points.append(p)

        matched = 0
        jobs = []
        for mk in cfg.get("markers", []):
            if mk.get("category") not in type_names:
                continue
            world = stage_to_world(ax, ay, float(mk["x"]), float(mk["y"]), lm["worldToSvg"])
            if not world:
                continue
            tkey = type_by_item.get(mk.get("item_id"))
            best = None
            for p in our_points:
                if tkey and tkey not in p.get("types", []):
                    continue
                d = math.hypot(p["x"] - world[0], p["z"] - world[1])
                if best is None or d < best[0]:
                    best = (d, p)
            if not best or best[0] > MATCH_LIMIT:
                continue
            p = best[1]
            slot = media["maps"].setdefault(key, {"nameZh": lm["name"], "points": {}})
            pkey = "%.3f|%.3f" % (p["x"], p["z"])
            entry = slot["points"].setdefault(pkey, {
                "desc": [], "floor": mk.get("floor_key"), "images": [],
            })
            desc = (mk.get("description") or "").strip()
            if desc and desc not in entry["desc"]:
                entry["desc"].append(desc)
            urls = mk.get("image_urls") or []
            for u in urls:
                jobs.append((key, u, entry))
            matched += 1

        if not jobs:
            print("%-16s 无可用点位（拟合 %s）" % (key, quality))
            continue

        # 去重后下载；每个点位内部按 01、02、… 编号
        uniq = []
        seen = set()
        counter = {}
        for kk, u, entry in jobs:
            if (kk, u) in seen:
                continue
            seen.add((kk, u))
            counter[id(entry)] = counter.get(id(entry), 0) + 1
            uniq.append((kk, u, entry, counter[id(entry)]))
        with futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            results = list(ex.map(lambda j: fetch_media(BASE + j[1], j[0], j[3]), uniq))
        for j in uniq:
            j[2]["images"] = []
        for (kk, u, entry, idx), (rel, size) in zip(uniq, results):
            if not rel:
                continue
            entry["images"].append(rel)
            total_imgs += 1
            total_bytes += size

        print("%-16s 拟合 %s  命中 %d 个点位 / %d 张图" % (key, quality, matched, len(uniq)))

    with open(MEDIA, "w", encoding="utf-8") as fh:
        json.dump(media, fh, ensure_ascii=False, separators=(",", ":"))
    print("\n完成：%d 张图 / %.1f MB / %.1fs -> %s" % (
        total_imgs, total_bytes / 1024 / 1024, time.time() - started, MEDIA))


if __name__ == "__main__":
    main()
