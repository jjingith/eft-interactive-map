#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r208_gunsmith_probe2.py — 探针2：containsAll 配件 id 能否在本地 items.json 解析；prerequisites 结构"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE, "data", "items.json"), "r", encoding="utf-8") as f:
    items_doc = json.load(f)

index = (items_doc.get("items") or {}) if isinstance(items_doc, dict) else {}
print("items.json 顶层键:", sorted(items_doc.keys()) if isinstance(items_doc, dict) else "list")
print("items 索引条数 =", len(index))

print("items.json 索引条数 =", len(index))

with open(os.path.join(BASE, "data", "tasks", "tasks.regular.json"), "r", encoding="utf-8") as f:
    doc = json.load(f)
tasks = doc["tasks"]

hit = miss = 0
missing_ids = []
sample_rows = []
for t in tasks.values():
    for ob in (t.get("objectives") or []):
        if ob.get("type") != "buildWeapon":
            continue
        ids = (ob.get("raw") or {}).get("containsAll") or []
        names = []
        for i in ids:
            it = index.get(str(i))
            if it:
                hit += 1
                names.append(it.get("n") or it.get("name") or i)
            else:
                miss += 1
                missing_ids.append((t.get("nameZh"), i))
        if names and len(sample_rows) < 3:
            sample_rows.append((t.get("nameZh"), ob["item"]["name"], names))

print("\ncontainsAll 解析: hit=%d miss=%d" % (hit, miss))
for r in sample_rows:
    print("\n*", r[0], "->", r[1])
    for n in r[2]:
        print("    -", n)
if missing_ids:
    print("\n未命中示例（前 15）:")
    for m in missing_ids[:15]:
        print("   ", m)

# prerequisites 结构
print("\n--- prerequisites 样例 ---")
n = 0
for t in tasks.values():
    if t.get("prerequisites") and n < 3:
        n += 1
        print(t.get("nameZh"), "->", json.dumps(t["prerequisites"], ensure_ascii=False)[:400])
