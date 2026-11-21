#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r208_gunsmith_attrs.py — 探针5：原始缓存里 buildWeapon 的完整约束（buildAttributes + containsCategory + containsAll）"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda *p: json.load(open(os.path.join(BASE, *p), "r", encoding="utf-8"))

raw = J("data", "tasks", "raw", "tasks.regular.json")["data"]["tasks"]
zh = J("data", "tasks", "raw", "tasks_zh.regular.json")
tasks_zh = zh.get("data", zh).get("tasks", {}) if isinstance(zh, dict) else {}

items_doc = J("data", "items.json")["items"]

# 中文名映射：先取构建后的（含 nameZh）
built = J("data", "tasks", "tasks.regular.json")["tasks"]
bname = {}
for tid, t in built.items():
    bname[tid] = t.get("nameZh")

# 原始 task 名（英文）
def tname(t):
    return bname.get(t.get("id")) or t.get("name") or t.get("id")

ATTR_KEYS = ["accuracy", "durability", "effectiveDistance", "ergonomics", "height",
             "magazineCapacity", "muzzleVelocity", "recoil", "weight", "width"]

rows = []
for t in raw.values():
    for ob in (t.get("objectives") or []):
        if ob.get("type") != "buildWeapon":
            continue
        ba = ob.get("buildAttributes") or {}
        cons = []
        for k in ATTR_KEYS:
            v = ba.get(k)
            if not v:
                continue
            val = v.get("value")
            cm = v.get("compareMethod")
            # value 为 0 且 >= 视为「无约束」（上游用 0 占位）
            if val in (None, 0) and cm == ">=":
                continue
            cons.append("%s %s %s" % (k, ("<=" if cm == "<=" else ">="), val))
        rows.append({
            "task": tname(t), "tid": t.get("id"),
            "lvl": t.get("minPlayerLevel"),
            "gun": (items_doc.get(str(ob.get("item")), {}) or {}).get("n") or ob.get("item"),
            "gunId": str(ob.get("item")),
            "cats": [c.get("name") if isinstance(c, dict) else c for c in (ob.get("containsCategory") or [])],
            "catIds": [c.get("id") if isinstance(c, dict) else c for c in (ob.get("containsCategory") or [])],
            "all": [items_doc.get(str(i), {}).get("n", i) for i in (ob.get("containsAll") or [])],
            "allIds": [str(i) for i in (ob.get("containsAll") or [])],
            "cons": cons,
        })

rows.sort(key=lambda r: ((r["lvl"] if isinstance(r["lvl"], int) else 0), r["task"]))
print("buildWeapon 目标数 =", len(rows))
print("=" * 100)
for r in rows:
    print("LV%-3s %-26s | %s" % (r["lvl"], r["task"][:26], r["gun"][:34]))
    if r["cons"]:
        print("        属性约束: %s" % " ; ".join(r["cons"]))
    if r["cats"]:
        print("        必含类别: %s" % ", ".join(str(c) for c in r["cats"]))
    if r["all"]:
        print("        必装配件: %s" % ", ".join(str(a)[:30] for a in r["all"]))
