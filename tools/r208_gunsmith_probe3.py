#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r208_gunsmith_probe3.py — 探针3：枪匠目标枪在 gunslots 中的覆盖率 + 必装配件可安装性"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda *p: json.load(open(os.path.join(BASE, *p), "r", encoding="utf-8"))

items = J("data", "items.json")["items"]
guns = J("data", "gunslots.json")["guns"]

# 槽位 allow 反查表：gunId -> { itemId: [(slotId, sid, label)] }
gun_allow = {}
for gid, g in guns.items():
    m = {}
    for s in g.get("slots") or []:
        for aid in s.get("allow") or []:
            m.setdefault(str(aid), []).append((s.get("id"), s.get("sid"), s.get("label")))
    gun_allow[gid] = m

for mode in ("regular", "pve", "pvps"):
    tasks = J("data", "tasks", "tasks.%s.json" % mode)["tasks"]
    total = gun_ok = 0
    part_total = part_ok = 0
    rows = []
    for t in tasks.values():
        for ob in (t.get("objectives") or []):
            if ob.get("type") != "buildWeapon":
                continue
            total += 1
            wid = str((ob.get("item") or {}).get("id") or "")
            ingun = wid in guns
            if ingun:
                gun_ok += 1
            ids = [str(x) for x in ((ob.get("raw") or {}).get("containsAll") or [])]
            ok = 0
            bad = []
            for i in ids:
                if ingun and i in gun_allow[wid]:
                    ok += 1
                else:
                    bad.append(items.get(i, {}).get("n", i))
            part_total += len(ids)
            part_ok += ok
            rows.append((t.get("nameZh"), (ob["item"] or {}).get("name"), ingun, len(ids), ok, bad))

    print("=" * 78)
    print("[%s] buildWeapon 目标=%d  目标枪在 gunslots 中=%d (%.0f%%)" %
          (mode, total, gun_ok, 100.0 * gun_ok / max(total, 1)))
    print("     必装配件=%d  可直接安装=%d (%.0f%%)" %
          (part_total, part_ok, 100.0 * part_ok / max(part_total, 1)))
    if mode == "regular":
        print("\n  明细（! 表示目标枪不在 gunslots；✗ 表示配件装不上）:")
        for r in rows:
            flag = "" if r[2] else "  !gun"
            if r[5]:
                flag += "  ✗%d:%s" % (len(r[5]), "/".join(r[5][:2]))
            print("   %-16s %-42s parts %d/%d%s" % (r[0], (r[1] or "")[:42], r[4], r[3], flag))
