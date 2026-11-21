# -*- coding: utf-8 -*-
"""R19.20 校准记录迁移：AKM 照门 / AKMP 并列坐标。

R19.19 把 AKMP 子槽记录标了失效（坐标 r2c6 = AKM 照门正下方）。本轮恢复子槽后：
- 身份键不变（mod_sight_rear/mod_sight_rear|mod_sight_rear|59d650cf… = AKM 照门的子槽）；
- 坐标由 r2c6（正下方，R19.19 遗留）迁至 **r1c7**（照门记录 r1c6 的同行右格 = 并列位）；
- 失效备注替换为 R19.20 迁移说明。

五把枪：AKM / AKMS / AKMN / AKMSN / VPO-136。其余记录一律不动。
输出：docs/r19.20-akm-akmp-parallel/calibration-migration.json。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
REPORT_DIR = os.path.join(ROOT, "docs", "r19.20-akm-akmp-parallel")

GUNS = {
    "59d6088586f774275f37482f": "AKM",
    "59ff346386f77477562ff5e2": "AKMS",
    "5a0ec13bfcdbcb00165aa685": "AKMN",
    "5abcbc27d8ce8700182eceeb": "AKMSN",
    "59e6152586f77473dc057aa1": "VPO-136",
}
KEY = "mod_sight_rear/mod_sight_rear|mod_sight_rear|59d650cf86f7741b846413a4"
SIGHT_KEY = "mod_sight_rear|mod_sight_rear|"
NOTE = ("R19.20：AKMP 并列位（AKM 照门右侧同行）；R19.19 曾标失效的坐标 r2c6 为正下方遗留位，"
        "已迁至并列位 r1c7。身份键不变（AKM 照门的子槽）。")


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    doc = json.load(open(CALIB, encoding="utf-8"))
    guns = doc.get("guns") or {}
    before = sum(len((g.get("slots") or {})) for g in guns.values())
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    changes = []

    for gid, name in GUNS.items():
        gun = guns.get(gid) or {}
        slots = gun.get("slots") or {}
        sight = slots.get(SIGHT_KEY)
        rec = slots.get(KEY)
        if rec is None:
            changes.append({"gun": name, "status": "missing-record", "key": KEY})
            continue
        sight_pos = (sight or {}).get("logicalRow"), (sight or {}).get("col")
        old = {"logicalRow": rec.get("logicalRow"), "col": rec.get("col"),
               "note": (rec.get("note") or "")[:20]}
        if rec.get("logicalRow") == 1 and rec.get("col") == 7:
            changes.append({"gun": name, "status": "already-parallel", "before": old})
            continue
        rec["logicalRow"] = 1
        rec["col"] = 7
        rec["displayRow"] = 1
        rec["topPad"] = 0
        rec["note"] = NOTE
        rec["updatedAt"] = now
        changes.append({"gun": name, "status": "moved-to-parallel", "key": KEY,
                        "before": old, "after": {"logicalRow": 1, "col": 7},
                        "sightRecordAt": {"logicalRow": sight_pos[0], "col": sight_pos[1]}})

    after = sum(len((g.get("slots") or {})) for g in guns.values())
    report = {
        "schema": "r19.20-calibration-migration/1",
        "recordsBefore": before, "recordsAfter": after, "recordsDeleted": 0,
        "changes": changes,
    }
    with open(CALIB, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(REPORT_DIR, "calibration-migration.json"), "w",
              encoding="utf-8", newline="") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "changes"}, ensure_ascii=False))
    for c in changes:
        print(" ", c.get("status"), "|", c.get("gun"), "|", c.get("before"), "->", c.get("after"))


if __name__ == "__main__":
    main()
