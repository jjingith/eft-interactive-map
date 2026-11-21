#!/usr/bin/env python3
"""R79 数据修正：用 game-truth 的 `armorColliders` 补齐 `data/items.json` 里缺失的防护区域。

背景
----
上游 tarkov.dev 对眼镜（`glasses`）以及部分面具 / 头盔不返回 `properties.zones`，
`data/items.json` 的 `z` 因此为空 —— 配装界面的「防护区域」列就看不到「眼部」。
但游戏文件提取的 `data/game-truth/armor_items.json` 里 `armorColliders` 是权威值
（例如 6B34 护目镜 = `["Eyes"]`）。

规则
----
只补 `z` 为空的物品，已有值一律不动；来源只认 game-truth，不编造。
落盘保持原来的紧凑单行 JSON，只给这 16 条记录插入 `z`，其余字节不变。

用法
----
    python tools/r79_apply_zone_fallback.py          # 写盘 + 写差异清单
    python tools/r79_apply_zone_fallback.py --check  # 只报告，不写盘

差异清单落在 `docs/r79-eyewear-eyes/zones-before-after.json`，作为验收证据。
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
TRUTH = os.path.join(ROOT, "data", "game-truth", "armor_items.json")
DIFF = os.path.join(ROOT, "docs", "r79-eyewear-eyes", "zones-before-after.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def insert_zone(rec, zones):
    """在记录里插入 `z`，位置与构建期一致（`cats` 之前）。"""
    out = {}
    placed = False
    for key, value in rec.items():
        if key == "cats" and not placed:
            out["z"] = zones
            placed = True
        out[key] = value
    if not placed:
        out["z"] = zones
    return out


def main():
    check = "--check" in sys.argv
    payload = load(ITEMS)
    truth = load(TRUTH).get("items") or {}
    items = payload.get("items") or {}

    changed = []
    for iid, rec in items.items():
        if rec.get("z"):
            continue
        props = (truth.get(iid) or {}).get("props") or {}
        coll = [c for c in (props.get("armorColliders") or []) if isinstance(c, str) and c]
        if not coll:
            continue
        zones = list(dict.fromkeys(coll))
        changed.append({
            "id": iid,
            "name": rec.get("n"),
            "cat": rec.get("cat"),
            "before": None,
            "after": zones,
        })
        if not check:
            items[iid] = insert_zone(rec, zones)

    if not changed:
        print("没有需要补齐的物品。")
        return

    print("补齐 %d 件：" % len(changed))
    for row in changed:
        print("  %-10s %-36s %s" % (row["cat"], row["name"], "、".join(row["after"])))

    if check:
        print("（--check：未写盘）")
        return

    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(ITEMS, "wb") as f:
        f.write(data)

    os.makedirs(os.path.dirname(DIFF), exist_ok=True)
    with open(DIFF, "w", encoding="utf-8") as f:
        json.dump({
            "round": "R79",
            "source": "data/game-truth/armor_items.json → props.armorColliders",
            "rule": "仅补 data/items.json 里 z 为空的物品，已有值不动",
            "count": len(changed),
            "items": changed,
        }, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已写入 %s（%d 字节）" % (ITEMS, len(data)))
    print("差异清单：%s" % DIFF)


if __name__ == "__main__":
    main()
