"""构建「赛季通行证文件刷点」数据（data/season-documents.json）。

数据来源：
- 上游地图：https://json.tarkov.dev/regular/maps 的 lootLoose 刷点池（与 data/maps.json 同源）；
- 文件类型 id：本地 data/items.json 里「赛季通行证文件」类目下的 8 种物品
  （类目 id 6a28212a0368f4438b0d0a45）。

用法：
    python tools/build_season_documents.py                 # 联网拉上游地图
    python tools/build_season_documents.py --maps x.json   # 用本地缓存的上游 maps
"""

import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UPSTREAM_MAPS = "https://json.tarkov.dev/regular/maps"

# 类型 key → 游戏内物品中文名（顺序即界面顺序）
DOC_TYPES = [
    ("blueprint", "蓝图与技术文档"),
    ("pmc", "PMC 个人档案"),
    ("medical", "医疗文件"),
    ("financial", "财务文件"),
    ("project", "项目文件"),
    ("employee", "员工文档"),
    ("test", "测试文档"),
    ("technical", "技术文档"),
]


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def doc_item_ids(items):
    """中文名 → item id；重名时保留第一个"""
    out = {}
    for iid, rec in items.items():
        name = rec.get("n", "")
        for key, zh in DOC_TYPES:
            if name == zh and key not in out:
                out[key] = iid
    missing = [zh for key, zh in DOC_TYPES if key not in out]
    if missing:
        raise SystemExit("data/items.json 缺少文件类型：" + "、".join(missing))
    return out


def fetch_maps(path):
    if path:
        return load_json(path)
    req = urllib.request.Request(UPSTREAM_MAPS, headers={"User-Agent": "eft-interactive-map/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", help="本地缓存的上游 maps JSON（默认联网拉取）")
    args = ap.parse_args()

    items = load_json(os.path.join(DATA, "items.json"))["items"]
    ids = doc_item_ids(items)
    id_to_type = {iid: key for key, iid in ids.items()}

    local_maps = load_json(os.path.join(DATA, "maps.json"))["maps"]
    id_to_key = {m["id"]: m["key"] for m in local_maps}
    key_to_name = {m["key"]: m["name"] for m in local_maps}

    upstream = fetch_maps(args.maps)
    up_maps = upstream["data"]["maps"]

    maps_out = {}
    total = 0
    for mid, mp in up_maps.items():
        key = id_to_key.get(mid)
        if not key:
            continue
        points = []
        for pool in mp.get("lootLoose", []):
            types = [id_to_type[i] for i in pool.get("items", []) if i in id_to_type]
            if not types:
                continue
            order = [t for t, _ in DOC_TYPES]
            types = sorted(set(types), key=order.index)
            pos = pool["position"]
            names = [dict(DOC_TYPES)[t] for t in types]
            points.append({
                "x": pos["x"],
                "y": pos.get("y"),
                "z": pos["z"],
                "name": " / ".join(names),
                "types": types,
            })
        if points:
            points.sort(key=lambda p: (p["z"], p["x"]))
            maps_out[key] = {"mapName": key_to_name.get(key, mp.get("name")), "points": points}
            total += len(points)

    season = None
    season_path = os.path.join(DATA, "tasks", "season.json")
    if os.path.exists(season_path):
        s = load_json(season_path)
        season = {"nameEn": s.get("nameEn"), "nameZh": s.get("nameZh"),
                  "startISO": s.get("startISO"), "endISO": s.get("endISO")}

    doc = {
        "schema": 1,
        "generatedAt": __import__("datetime").date.today().isoformat(),
        "source": "https://json.tarkov.dev/regular/maps（lootLoose 刷点池）",
        "season": season,
        "types": [{"key": k, "nameZh": zh, "itemId": ids[k]} for k, zh in DOC_TYPES],
        "counts": {"maps": len(maps_out), "points": total},
        "maps": maps_out,
    }
    out_path = os.path.join(DATA, "season-documents.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out_path)

    print("类型：", "、".join(zh for _, zh in DOC_TYPES))
    print("地图 %d 张，刷点 %d 个 → %s" % (len(maps_out), total, out_path))
    for key, pack in maps_out.items():
        by_type = {}
        for p in pack["points"]:
            for t in p["types"]:
                by_type[t] = by_type.get(t, 0) + 1
        print("  %-16s %3d 点  %s" % (key, len(pack["points"]),
              "  ".join("%s=%d" % (t, n) for t, n in by_type.items())))


if __name__ == "__main__":
    main()
