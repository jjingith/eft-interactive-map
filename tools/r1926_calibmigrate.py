# -*- coding: utf-8 -*-
"""R19.18 校准数据迁移：给「真实槽位已修正、不再存在」的旧记录标记回退原因。

原则（任务书 2.2）：
  · 不删除任何人工校准记录；
  · 不把旧记录改挂到别的槽位；
  · 只在记录里补一句 note，说明它为什么不再生效（保留原始坐标不动）。

用法：python tools/r1926_calibmigrate.py [--dry-run]
产物：docs/r19.18-slot-fix-audit/calibration-migration.json
备份：data/gun-layout-calibration.json.r1918.bak.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
BACKUP = os.path.join(ROOT, "data", "gun-layout-calibration.json.r1918.bak.json")
OUT_DIR = os.path.join(ROOT, "docs", "r19.18-slot-fix-audit")

# 真实槽位修正说明（与 tools/slotfix.py 对应）：按**被移除子槽的父件物品 id** 判定，
# 不能只看路径 —— AKM 照门（59d650cf…）的 AKMP 子槽仍然有效，不该被标记。
STALE_OWNERS = {
    "5649b0544bdc2d1b2b8b458a": "R19.18：AK-74 叶式照门游戏内没有 AKMP 侧轨接口，"
                                 "该条件子槽已按真实数据移除；本条记录保留原坐标，但不再生效。",
    "5ac72e475acfc400180ae6fe": "R19.18：AK-74M 叶式照门游戏内没有 AKMP 侧轨接口，"
                                 "该条件子槽已按真实数据移除；本条记录保留原坐标，但不再生效。",
    "5ac733a45acfc400192630e2": "R19.18：AK-105 叶式照门游戏内没有 AKMP 侧轨接口，"
                                 "该条件子槽已按真实数据移除；本条记录保留原坐标，但不再生效。",
    "64527a3a7da7133e5a09ca99": "R19.18：9A-91 消音器没有 VSS/VAL B-3 环形基座接口，"
                                 "该条件子槽已按真实数据移除；本条记录保留原坐标，但不再生效。",
    "687128c4505fed5f370b1625": "R19.18：AS VAL MOD.4 套件护木的 3.5 英寸导轨槽位重复，"
                                 "已按真实数据只保留一个；本条记录保留原坐标，但不再生效。",
    "68712b57a1be89347f0d8179": "R19.18：3.5 英寸导轨的重复安装位已移除，"
                                 "其战术子槽随之失效；本条记录保留原坐标，但不再生效。",
    # R19.20：AKM 照门（59d650cf…）的 AKMP 子槽已恢复为并列照门位，记录复活——
    # 从失效表移除，防止重跑本脚本时误标。
}

GENERIC_DEAD_REASON = ("R19.18：对应的真实条件子槽已按游戏实测修正移除；"
                       "本条记录保留原坐标，但不再生效。")

# 真实互斥导致「当前不可用」的槽位（槽位本身还在，只是装了某个配件后失效）
CONFLICTED = {
    "57c44b372459772d2b39b8ce": {"mod_mount_004"},
    "6871284e9a353bb50606f3ed": {"mod_mount_004"},
}
CONFLICT_REASON = ("R19.18：装上 top cover（NB AS VAL MOD.4 套件防尘盖）后，枪身燕尾槽按真实互斥失效；"
                   "本条记录保留，卸下 top cover 后自动恢复。")


def live_slot_paths(gun_id, installed):
    """按真实数据算出该枪当前装配下的**存活槽位路径**（枪槽 + 已装件自带子槽）。"""
    gunslots = json.load(open(os.path.join(ROOT, "data", "gunslots.json"), encoding="utf-8"))["guns"]
    items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]
    out = set()

    def add(rec, prefix, parent_path):
        used = {}
        for slot in ((rec and rec.get("slots")) or []):
            sid = slot.get("sid") or slot.get("id") or "s"
            n = used.get(sid, 0)
            used[sid] = n + 1
            if n > 0:
                sid = "%s#%d" % (sid, n)
            path = (prefix + "/" + sid) if prefix else sid
            out.add(path)
            child = items.get(installed.get(path))
            if child:
                add(child, path, path)

    add(gunslots.get(gun_id) or {}, "", None)
    return out


def default_install(gun_id):
    stats = json.load(open(os.path.join(ROOT, "data", "gun-stats.json"), encoding="utf-8"))
    presets = json.load(open(os.path.join(ROOT, "data", "gun-presets.json"), encoding="utf-8"))["presets"]
    st = (stats.get("guns") or {}).get(gun_id) or {}
    if st.get("preset") and presets.get(st["preset"]):
        return presets[st["preset"]].get("i") or {}
    for pid, p in presets.items():
        if p.get("g") == gun_id:
            return p.get("i") or {}
    return {}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(CALIB, encoding="utf-8") as f:
        doc = json.load(f)
    before_sha = sha256(CALIB)

    marked, unmarked = [], []
    for gid, gun in (doc.get("guns") or {}).items():
        live = live_slot_paths(gid, default_install(gid))
        for key, rec in (gun.get("slots") or {}).items():
            owner = rec.get("ownerItemId") or (key.split("|")[2] if key.count("|") >= 2 else "")
            path = rec.get("slotPath") or key.split("|")[0]
            reason = None
            if path not in live:
                # 真实条件子槽已被移除（按游戏实测修正）→ 记录保留但不再生效
                reason = STALE_OWNERS.get(owner) or GENERIC_DEAD_REASON
            elif path in CONFLICTED.get(gid, set()):
                # 槽位还在，但按真实互斥当前不可用（装了 top cover 等）→ 记录保留，卸下后自动恢复
                reason = CONFLICT_REASON
            old = (rec.get("note") or "").strip()
            if reason:
                if old == reason:
                    continue
                rec["note"] = reason
                marked.append({"gunId": gid, "gun": gun.get("name") or gid, "key": key,
                                "ownerItemId": owner, "slotPath": path, "note": reason})
            elif old.startswith("R19.18："):
                # 之前误标（槽位其实仍然存活）→ 清掉备注
                rec["note"] = ""
                unmarked.append({"gunId": gid, "gun": gun.get("name") or gid, "key": key,
                                 "ownerItemId": owner, "slotPath": path})

    os.makedirs(OUT_DIR, exist_ok=True)
    if (marked or unmarked) and not args.dry_run:
        if not os.path.exists(BACKUP):
            shutil.copy2(CALIB, BACKUP)
        tmp = CALIB + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CALIB)

    with open(CALIB, encoding="utf-8") as f:
        doc2 = json.load(f)
    after_sha = sha256(CALIB)
    total = sum(len((g or {}).get("slots") or {}) for g in (doc2.get("guns") or {}).values())

    out = {
        "generatedFor": "R19.18",
        "dryRun": bool(args.dry_run),
        "backup": os.path.relpath(BACKUP, ROOT).replace("\\", "/") if os.path.exists(BACKUP) else None,
        "sha256Before": before_sha,
        "sha256After": after_sha,
        "recordsBefore": total,
        "recordsAfter": total,
        "markedCount": len(marked),
        "marked": marked,
        "unmarkedCount": len(unmarked),
        "unmarked": unmarked,
        "note": "记录条数不变；只给失效记录补 note 说明回退原因，坐标与身份一律未改。",
    }
    with open(os.path.join(OUT_DIR, "calibration-migration.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in ("dryRun", "recordsBefore", "recordsAfter", "markedCount", "sha256Before", "sha256After")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
