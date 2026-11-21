"""构建搜索索引：物品刷新点 + 任务点（data/search-index.json）。

- 物品刷新点：上游 json.tarkov.dev/regular/maps 的 lootLoose 刷点池 → 物品中文名；
- 任务点：本地 data/tasks/tasks.{regular,pve,pvps}.json 的目标 zone 坐标。

结构（紧凑，给前端一次加载）：
{
  "schema": 1,
  "items": {
    "names": ["物品中文名", ...],
    "maps": { "customs": [[x, z, y, [名字下标...]], ...], ... }
  },
  "tasks": [
    {"id": "...", "name": "新手上路", "mode": "regular", "map": "ground-zero",
     "zonesByMap": {"ground-zero": [[x, z, y], ...]}}
  ]
}

用法：python tools/build_search_index.py [--maps 本地 maps JSON]
"""

import argparse
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "search-index.json")
URL = "https://json.tarkov.dev/regular/maps"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) eft-interactive-map/1.0"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def fetch_maps(path):
    if path:
        return load(path)
    req = urllib.request.Request(URL, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps")
    args = ap.parse_args()

    maps = load(os.path.join(DATA, "maps.json"))["maps"]
    items = load(os.path.join(DATA, "items.json"))["items"]
    name_by_id = {iid: rec.get("n") for iid, rec in items.items()}

    id_to_key = {m["id"]: m["key"] for m in maps}
    upstream = fetch_maps(args.maps)["data"]["maps"]

    names = []
    name_index = {}
    item_maps = {}

    def idx_of(name):
        if name not in name_index:
            name_index[name] = len(names)
            names.append(name)
        return name_index[name]

    for mid, mp in upstream.items():
        key = id_to_key.get(mid)
        if not key:
            continue
        rows = []
        for pool in mp.get("lootLoose") or []:
            pos = pool.get("position") or {}
            if "x" not in pos or "z" not in pos:
                continue
            ids = [name_by_id.get(i) for i in pool.get("items") or []]
            ids = sorted({i for i in ids if i})
            if not ids:
                continue
            rows.append([round(pos["x"], 3), round(pos["z"], 3),
                         round(pos["y"], 3) if pos.get("y") is not None else None,
                         [idx_of(n) for n in ids]])
        if rows:
            item_maps[key] = rows

    # 任务点：三个模式并集，按任务 id 去重，zone 按地图 key 归并
    tasks = {}
    for mode in ("regular", "pve", "pvps"):
        p = os.path.join(DATA, "tasks", "tasks.%s.json" % mode)
        if not os.path.exists(p):
            continue
        doc = load(p)
        for t in (doc.get("tasks") or {}).values():
            tid = t.get("id")
            if not tid:
                continue
            entry = tasks.setdefault(tid, {"id": tid, "name": t.get("nameZh") or t.get("nameEn"),
                                          "mode": mode, "zonesByMap": {}, "zones": [],
                                          "seen": set()})
            for o in t.get("objectives") or []:
                for z in o.get("zones") or []:
                    pos = z.get("position") or {}
                    key = id_to_key.get(z.get("mapId"))
                    if not key or "x" not in pos or "z" not in pos:
                        continue
                    pt = [round(pos["x"], 3), round(pos["z"], 3),
                          round(pos["y"], 3) if pos.get("y") is not None else None]
                    # 同一任务在 regular / pve / pvps 三个文件里会带同一份 zone，
                    # 多个 objective 也可能落在同一个点：按「地图 + 坐标」去重，避免计数翻倍
                    sk = (key, pt[0], pt[1], pt[2])
                    if sk in entry["seen"]:
                        continue
                    entry["seen"].add(sk)
                    entry["zones"].append(pt)
                    entry["zonesByMap"].setdefault(key, []).append(pt)

    task_rows = []
    for e in tasks.values():
        if not e["zones"]:
            continue
        main_map = max(e["zonesByMap"].items(), key=lambda kv: len(kv[1]))[0]
        task_rows.append({"id": e["id"], "name": e["name"], "mode": e["mode"],
                          "map": main_map, "zonesByMap": e["zonesByMap"]})

    doc = {
        "schema": 1,
        "source": "tarkov.dev maps lootLoose + data/tasks/*",
        "counts": {"itemNames": len(names), "itemMaps": len(item_maps),
                   "itemPoints": sum(len(v) for v in item_maps.values()),
                   "tasks": len(task_rows),
                   "taskPoints": sum(len(v) for t in task_rows for v in t["zonesByMap"].values())},
        "items": {"names": names, "maps": item_maps},
        "tasks": task_rows,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    print("物品名 %d / 刷点 %d（%d 张图）；任务 %d / 任务点 %d → %.1f KB" % (
        doc["counts"]["itemNames"], doc["counts"]["itemPoints"], len(item_maps),
        len(task_rows), doc["counts"]["taskPoints"], os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
