"""把 eftarkov 互动地图上的「任务地点 / 剧情地点」抓成本地任务点 / 剧情点数据。

坐标来自 eftarkov 的 #map-config；任务名称、目标与攻略信息统一取自开源的 tarkov.dev
（本地 data/tasks/tasks.*.json，构建期由 tools/fetch_tasks.py 拉取）。
按要求不再下载任何现场截图。

坐标对齐：用同名地标（撤离点 / 转移点 / 钥匙门 / Boss / 固定武器）做 RANSAC 仿射拟合
（该站地图是重绘的 800×1100，个别近似标注会被剔除）。

产物：data/task-points.json

用法：
    python tools/fetch_eftarkov_tasks.py --limit-maps ground-zero
    python tools/fetch_eftarkov_tasks.py
"""

import argparse
import itertools
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_eftarkov_docs as fx  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "build-cache", "eftarkov")
BASE = fx.BASE
TASK_CAT = "任务地点"
STORY_CAT = "剧情地点"
# 本地楼层中文名：地面层、一层、二层…（各图由 floors.selectable 提供）
FLOOR_LABELS = ["地面层", "一层", "二层", "三层", "四层", "五层", "六层"]


def site_floor_name(cfg, key):
    for f in cfg.get("floors") or []:
        if str(f.get("key")) == str(key):
            return f.get("name") or (str(key) + "层")
    return str(key) + "层"


def local_floor(local_map, floor_name):
    """站点楼层名 → (本地 svgLayer, 本地楼层名)；对不上时返回 (None, 站点名)"""
    selectable = (local_map.get("floors") or {}).get("selectable") or []
    labels = {f.get("label"): f.get("svgLayer") for f in selectable}
    m = re.match(r"地下(\d+)层", floor_name or "")
    if m:
        label = "地下层" if int(m.group(1)) == 1 else "地下" + m.group(1) + "层"
        if label in labels:
            return labels[label], label
        return (selectable[0].get("svgLayer") if selectable else None), label
    m = re.match(r"(\d+)层", floor_name or "")
    if m:
        idx = int(m.group(1)) - 1
        label = FLOOR_LABELS[idx] if 0 <= idx < len(FLOOR_LABELS) else None
        if label and label in labels:
            return labels[label], label
        return None, (label or floor_name)
    return None, floor_name


def parse_config(html):
    m = re.search(r'<script id="map-config" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def fit_robust(cfg, local_map):
    """用全部可配对地标（撤离 / 转移 / 钥匙门 / Boss / 固定武器 / BTR）做 RANSAC 拟合。

    站点的地图是重绘的（800×1100），个别点位与本地同名地标并不在同一处
    （例如「Mira 大道（信号弹）」这类近似标注），直接最小二乘会被带偏；
    这里取「4 点拟合 → 统计内点 → 用内点重拟合」的做法，把离群点剔掉。
    """
    theirs = {}
    for m in cfg.get("markers") or []:
        title = m.get("title")
        if not title or m.get("marker_type") == "label":
            continue
        if (m.get("category") or "") in (TASK_CAT, STORY_CAT):
            continue
        theirs.setdefault(title, []).append((float(m["x"]), float(m["y"])))

    c = local_map["worldToSvg"]
    ours = {}
    for layer_key in ("extracts", "transits", "locks", "bosses", "stationary", "btr"):
        for e in local_map["layers"].get(layer_key, []):
            nm = e.get("keyName") if layer_key == "locks" else e.get("name")
            if not nm:
                continue
            sx = c["a"] * e["x"] + c["b"] * e["z"] + c["c"]
            sy = c["d"] * e["x"] + c["e"] * e["z"] + c["f"]
            ours.setdefault(nm, []).append((sx, sy))

    pairs = []
    for name, pts in ours.items():
        cand = theirs.get(name)
        if cand and len(cand) == 1 and len(pts) == 1:
            pairs.append((cand[0][0], cand[0][1], pts[0][0], pts[0][1]))
    if len(pairs) < 4:
        return None, {"pairs": len(pairs)}

    def model(ps):
        ax = fx.solve3([(x, y, ox) for x, y, ox, oy in ps])
        ay = fx.solve3([(x, y, oy) for x, y, ox, oy in ps])
        return ax, ay

    def errs(ax, ay, ps):
        return [math.hypot(ax[0] * x + ax[1] * y + ax[2] - ox,
                           ay[0] * x + ay[1] * y + ay[2] - oy) for x, y, ox, oy in ps]

    tol = 4.0
    n = len(pairs)
    if n <= 14:
        combos = list(itertools.combinations(range(n), 4))
    else:
        import random
        rnd = random.Random(2026)
        combos = set()
        while len(combos) < 500:
            combos.add(tuple(sorted(rnd.sample(range(n), 4))))
        combos = sorted(combos)
    best = None
    for combo in combos:
        ax, ay = model([pairs[i] for i in combo])
        e = errs(ax, ay, pairs)
        inl = [i for i, v in enumerate(e) if v <= tol]
        if len(inl) < 4:
            continue
        med = sorted(e[i] for i in inl)[len(inl) // 2]
        score = (len(inl), -round(med, 3))
        if best is None or score > best[0]:
            best = (score, inl)
    if not best:
        return None, {"pairs": n, "reason": "无共识集"}
    ax, ay = model([pairs[i] for i in best[1]])
    e_all = errs(ax, ay, pairs)
    inliers = [i for i, v in enumerate(e_all) if v <= tol]
    ax, ay = model([pairs[i] for i in inliers])
    e_in = sorted(errs(ax, ay, [pairs[i] for i in inliers]))
    return (ax, ay, {"pairs": n, "inliers": len(inliers),
                     "median": round(e_in[len(e_in) // 2], 2), "max": round(e_in[-1], 2)}), n


def page_html(map_id, force=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, map_id + ".html")
    if os.path.exists(path) and os.path.getsize(path) > 1024 and not force:
        return open(path, encoding="utf-8", errors="replace").read()
    html = fx.fetch("%s/map/%s" % (BASE, map_id), timeout=90).decode("utf-8", "replace")
    open(path, "w", encoding="utf-8").write(html)
    return html


def group_key(kind, marker):
    if kind == "tasks":
        return str(marker.get("task_id"))
    rel = (marker.get("story_relations") or [{}])[0]
    sid = rel.get("storyline_id") or "story"
    if rel.get("relation_type") == "unlock":
        return "story-" + sid + "-unlock"
    objs = marker.get("story_objective_ids") or []
    return "story-" + sid + "-" + (str(objs[0]) if objs else "obj")


def load_task_names():
    """任务 id → tarkov.dev 的任务名 / 商人 / 目标（攻略内容统一来自开源数据）"""
    meta = {}
    for mode in ("regular", "pve", "pvps"):
        path = os.path.join(DATA, "tasks", "tasks.%s.json" % mode)
        if not os.path.exists(path):
            continue
        for t in (json.load(open(path, encoding="utf-8")).get("tasks") or {}).values():
            tid = t.get("id")
            if not tid or tid in meta:
                continue
            goals = []
            for o in t.get("objectives") or []:
                text = (o.get("descZh") or "").strip()
                if text and text not in goals:
                    goals.append(text)
            meta[tid] = {
                "name": t.get("nameZh") or t.get("nameEn"),
                "trader": t.get("traderZh") or "",
                "objective": "；".join(goals[:4]),
            }
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-maps")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    maps = json.load(open(os.path.join(DATA, "maps.json"), encoding="utf-8"))["maps"]
    task_meta = load_task_names()
    want = [s.strip() for s in args.limit_maps.split(",")] if args.limit_maps else None

    doc = {"schema": 1,
           "source": "点位坐标：eftarkov.com /map/<mapId>（#map-config）；任务名称与目标：tarkov.dev（开源 MIT）",
           "attribution": "任务 / 剧情点位坐标参考 eftarkov；任务名称与目标文案来自 tarkov.dev（开源）；业务界面不外链，出处仅在本关于页；不含任何第三方截图",
           "counts": {"maps": 0, "tasks": 0, "stories": 0, "points": 0},
           "maps": {}}
    started = time.time()

    for lm in maps:
        key = lm["key"]
        if want and key not in want:
            continue
        try:
            html = page_html(lm["id"], args.force)
        except Exception as exc:  # noqa: BLE001
            print("%-18s 页面失败：%s" % (key, exc))
            continue
        cfg = parse_config(html)
        if not cfg:
            print("%-18s 没有 map-config，跳过" % key)
            continue

        fit, pairs = fit_robust(cfg, lm)
        if not fit:
            print("%-18s 仿射拟合失败（可配对地标 %d 个）" % (key, pairs if isinstance(pairs, int) else pairs.get("pairs", 0)))
            continue
        ax, ay, quality = fit

        packs = {"tasks": {}, "stories": {}}
        for mk in cfg.get("markers") or []:
            cat = mk.get("category")
            kind = "tasks" if cat == TASK_CAT else ("stories" if cat == STORY_CAT else None)
            if not kind:
                continue
            world = fx.stage_to_world(ax, ay, float(mk["x"]), float(mk["y"]), lm["worldToSvg"])
            if not world:
                continue
            gid = group_key(kind, mk)
            if not gid or gid == "None":
                continue
            pack = packs[kind].setdefault(gid, {"id": gid, "points": [], "name": "", "objective": "",
                                                "nameEn": "", "trader": ""})
            rel = (mk.get("story_relations") or [{}])[0]
            if kind == "tasks":
                meta = task_meta.get(gid, {})
                pack["name"] = meta.get("name") or cfg.get("taskTitles", {}).get(gid) or mk.get("title") or gid
                pack["trader"] = meta.get("trader") or ""
                # R79：不再生成 tarkov.dev 外链（业务界面不外跳）；出处统一收在「关于」页
                # 目标说明优先用 tarkov.dev 的 objective 文案；缺失时退回站点标注
                pack["objective"] = meta.get("objective") or (mk.get("description") or "").strip()
            else:
                pack["name"] = rel.get("storyline_title") or mk.get("title") or gid
                pack["nameEn"] = rel.get("storyline_title_en") or ""
                pack["objective"] = (rel.get("unlock_title") if rel.get("relation_type") == "unlock"
                                     else mk.get("title")) or ""
            floor_name = site_floor_name(cfg, mk.get("floor_key"))
            floor_id, floor_label = local_floor(lm, floor_name)
            point = {"id": mk.get("id"), "x": round(world[0], 3), "z": round(world[1], 3),
                     "floor": str(mk.get("floor_key")), "floorName": floor_name,
                     "floorId": floor_id, "floorLabel": floor_label}
            pack["points"].append(point)

        if not packs["tasks"] and not packs["stories"]:
            print("%-18s 没有任务 / 剧情点" % key)
            continue

        slot = doc["maps"].setdefault(key, {"nameZh": lm.get("name"), "fit": quality,
                                            "tasks": [], "stories": []})
        for kind in ("tasks", "stories"):
            for pack in packs[kind].values():
                if pack["points"]:
                    slot[kind].append(pack)
        slot["tasks"].sort(key=lambda p: p["name"])
        slot["stories"].sort(key=lambda p: p["name"])
        doc["counts"]["maps"] += 1
        doc["counts"]["tasks"] += len(slot["tasks"])
        doc["counts"]["stories"] += len(slot["stories"])
        doc["counts"]["points"] += sum(len(p["points"]) for p in slot["tasks"]) + \
            sum(len(p["points"]) for p in slot["stories"])
        print("%-18s 拟合 %s  任务 %d / 剧情 %d / 点 %d" % (
            key, quality, len(slot["tasks"]), len(slot["stories"]),
            sum(len(p["points"]) for p in slot["tasks"]) + sum(len(p["points"]) for p in slot["stories"])))

    out = os.path.join(DATA, "task-points.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    print("\n完成：%d 张图 / 任务 %d / 剧情 %d / 点 %d / %.1f MB / %.1fs → %s" % (
        doc["counts"]["maps"], doc["counts"]["tasks"], doc["counts"]["stories"],
        doc["counts"]["points"], os.path.getsize(out) / 1024 / 1024,
        time.time() - started, out))


if __name__ == "__main__":
    main()
