#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r208_gunsmith_probe4.py — 探针4：BFS 递归展开子槽，算枪匠必装配件的真实可达率

展开规则与塔科夫一致：从枪根出发 → 顶层 slots 的 allow 为「可装」→
装上某配件后该配件自身的 slots 继续展开为可达子槽（链式装配）。
"""
import json, os
from collections import deque

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda *p: json.load(open(os.path.join(BASE, *p), "r", encoding="utf-8"))

items = J("data", "items.json")["items"]
guns = J("data", "gunslots.json")["guns"]


def reach(gid, max_depth=8):
    """返回 {可装 itemId: 深度} —— 从枪根 BFS 展开所有可达槽位允许的配件"""
    root = guns.get(gid)
    if not root:
        return {}
    seen_items = set()
    out = {}
    # 队列元素: (slots列表, 深度)
    q = deque([(root.get("slots") or [], 0)])
    while q:
        slots, d = q.popleft()
        if d > max_depth:
            continue
        for s in slots:
            for aid in s.get("allow") or []:
                aid = str(aid)
                if aid in out and out[aid] <= d:
                    continue
                out[aid] = d
                if aid in seen_items:
                    continue
                seen_items.add(aid)
                sub = (items.get(aid) or {}).get("slots") or []
                if sub:
                    q.append((sub, d + 1))
    return out


tasks = J("data", "tasks", "tasks.regular.json")["tasks"]
tot = tot_ok = 0
rows = []
for t in tasks.values():
    for ob in (t.get("objectives") or []):
        if ob.get("type") != "buildWeapon":
            continue
        wid = str((ob.get("item") or {}).get("id") or "")
        R = reach(wid)
        ids = [str(x) for x in ((ob.get("raw") or {}).get("containsAll") or [])]
        ok = [i for i in ids if i in R]
        bad = [(items.get(i, {}).get("n", i)) for i in ids if i not in R]
        tot += len(ids)
        tot_ok += len(ok)
        rows.append((t.get("nameZh"), (ob["item"] or {}).get("name"), len(R), len(ids), len(ok), bad))

print("=" * 80)
print("BFS 递归展开后：必装配件 = %d  可安装 = %d  (%.1f%%)" %
      (tot, tot_ok, 100.0 * tot_ok / max(tot, 1)))
print()
print("  %-16s %-40s %-7s %-6s %s" % ("任务", "目标枪", "可达件", "配件", "不可达"))
for r in rows:
    print("  %-16s %-40s %-7d %d/%-4d %s" % (
        r[0][:16], (r[1] or "")[:40], r[2], r[4], r[3],
        ("✗ " + " / ".join(x[:26] for x in r[5])) if r[5] else "✓"))
