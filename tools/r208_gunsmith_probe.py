#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r208_gunsmith_probe.py — 一次性探针：摸清 tasks.*.json 里枪匠(buildWeapon)目标的结构"""
import json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TDIR = os.path.join(BASE, "data", "tasks")

for mode in ("regular", "pve", "pvps"):
    p = os.path.join(TDIR, "tasks.%s.json" % mode)
    with open(p, "r", encoding="utf-8") as f:
        doc = json.load(f)
    tasks = doc.get("tasks")
    print("=" * 70)
    print(mode, "type=", type(tasks).__name__, "len=", len(tasks))
    items = tasks.values() if isinstance(tasks, dict) else tasks
    gs = []
    for t in items:
        for ob in (t.get("objectives") or []):
            if ob.get("type") == "buildWeapon":
                gs.append((t, ob))
    print("buildWeapon 目标数 =", len(gs))
    if mode == "regular":
        t, ob = gs[0]
        print("\n--- 样例任务顶层键 ---")
        print(sorted(t.keys()))
        print("\n--- 样例 objective 完整 JSON ---")
        print(json.dumps(ob, ensure_ascii=False, indent=2)[:3000])
        print("\n--- 全部 26 个 buildWeapon 目标摘要 ---")
        for t, ob in gs:
            print("  %-28s | trader=%-6s | lvl=%-3s | item=%s | containsAll=%d" % (
                t.get("nameZh"), t.get("traderZh"), t.get("minLevel"),
                (ob.get("item") or {}).get("name") if isinstance(ob.get("item"), dict) else ob.get("item"),
                len(ob.get("raw", {}).get("containsAll") or [])))
