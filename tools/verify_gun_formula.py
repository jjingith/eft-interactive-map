# -*- coding: utf-8 -*-
"""R19：用 373 个真实枪械预设反证整枪属性公式。

`data/gun-presets.json` 的每个预设都记录了：完整装配清单 `i`（path -> itemId）
以及**游戏内的真值** `e`（人机工效）/ `rv` / `rh`（后坐力）/ `moa`（精度 MOA）。

于是可以逐条验证候选公式：
    ergo      = base.e + Σ(mod.e)                    ?
    recoil(V) = base.rv * (1 + Σ recoilModifier)     ?
    moa       = base.coi + Σ accuracyModifier        ?
统计残差，判断公式是否成立、是否需要额外的重量惩罚项。

用法：python tools/verify_gun_formula.py [--dump docs/.../formula-residuals.json]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
STATS = os.path.join(ROOT, "data", "gun-stats.json")
PRESETS = os.path.join(ROOT, "data", "gun-presets.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="")
    a = ap.parse_args()

    items = json.load(open(ITEMS, encoding="utf-8"))["items"]
    stats = json.load(open(STATS, encoding="utf-8"))
    presets = json.load(open(PRESETS, encoding="utf-8"))["presets"]
    guns, mods = stats["guns"], stats["mods"]

    rows = []
    for pid, pr in presets.items():
        gid = pr.get("g")
        gs = guns.get(gid)
        if not gs:
            continue
        base_e = gs.get("e")
        base_rv = gs.get("rv")
        base_rh = gs.get("rh")
        base_coi = gs.get("coi")
        ergo_sum = 0.0
        rm_sum = 0.0
        am_sum = 0.0
        w_sum = 0.0
        n = 0
        missing = 0
        for path, iid in (pr.get("i") or {}).items():
            rec = items.get(iid)
            ms = mods.get(iid) or {}
            if rec is None:
                missing += 1
                continue
            n += 1
            w_sum += rec.get("w") or 0
            e = ms.get("e")
            if e is None:
                e = (rec.get("mod") or {}).get("e")
            if isinstance(e, (int, float)):
                ergo_sum += e
            rm = ms.get("rm")
            if rm is None:
                rm = (rec.get("mod") or {}).get("r")
            if isinstance(rm, (int, float)):
                rm_sum += rm
            am = ms.get("am")
            if isinstance(am, (int, float)):
                am_sum += am
        if missing:
            continue
        gun = items.get(gid) or {}
        w_total = (gun.get("w") or 0) + w_sum
        calc = {
            "e": None if base_e is None else base_e + ergo_sum,
            "rv": None if base_rv is None else base_rv * (1 + rm_sum),
            "rh": None if base_rh is None else base_rh * (1 + rm_sum),
            "moa": None if base_coi is None else base_coi + am_sum,
        }
        rows.append({
            "preset": pr.get("n"), "gun": gid, "parts": n, "w": round(w_total, 3),
            "base": {"e": base_e, "rv": base_rv, "rh": base_rh, "coi": base_coi},
            "sum": {"e": round(ergo_sum, 3), "rm": round(rm_sum, 4), "am": round(am_sum, 4)},
            "calc": {k: (None if v is None else round(v, 3)) for k, v in calc.items()},
            "truth": {"e": pr.get("e"), "rv": pr.get("rv"), "rh": pr.get("rh"), "moa": pr.get("moa")},
        })

    print("可验证预设：%d 条" % len(rows))
    for key in ("e", "rv", "rh", "moa"):
        diffs = []
        for r in rows:
            c, t = r["calc"][key], r["truth"][key]
            if c is None or t is None:
                continue
            diffs.append(c - t)
        if not diffs:
            print("  %-4s 无可用样本" % key)
            continue
        absd = sorted(abs(d) for d in diffs)
        print("  %-4s n=%-4d 平均残差 %+8.3f  中位绝对误差 %.3f  p95 %.3f  最大 %.3f"
              % (key, len(diffs), statistics.mean(diffs),
                 absd[len(absd) // 2], absd[int(len(absd) * 0.95)], absd[-1]))

    # 人机工效残差 vs 总重量：若存在系统性重量惩罚，这里会呈现相关性
    print("\n人机工效残差（calc - truth）按总重量分桶：")
    buckets = {}
    for r in rows:
        c, t = r["calc"]["e"], r["truth"]["e"]
        if c is None or t is None:
            continue
        b = int(r["w"] * 2) / 2.0
        buckets.setdefault(b, []).append(c - t)
    for b in sorted(buckets):
        v = buckets[b]
        print("  重量 %.1f~%.1f kg  n=%-3d 平均残差 %+7.3f"
              % (b, b + 0.5, len(v), statistics.mean(v)))

    if a.dump:
        os.makedirs(os.path.dirname(a.dump), exist_ok=True)
        json.dump(rows, open(a.dump, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n明细 -> %s" % a.dump)


if __name__ == "__main__":
    main()
