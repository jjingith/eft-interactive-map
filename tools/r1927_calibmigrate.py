# -*- coding: utf-8 -*-
"""R19.19 校准记录迁移（任务 A1 / A2）。

A1：五把 5.45x39 / 5.56x45 AK（AK-105 / AK-74 / AK-74N / AKS-74 / AKS-74N）的
    照门槽人工记录 `mod_sight_rear|mod_sight_rear|` 当前钉在逻辑 r1c6，而自动布局
    本就在 r2（照门带）——用户实测要求下移一格（r1→r2，列不变）。
    按任务书 A4 授权**只修改与 AK 照门直接相关的校准记录**，不动其他枪械。

A2：AKM 照门的 AKMP-only 子槽已按真实数据删除（tools/slotfix.py R19.19），其
    子槽记录（owner=59d650cf…）标注失效原因、保留原坐标、**不迁移到其他槽位**。

输出：docs/r19.19-ak-rear-sight/calibration-migration.json（含前后对照与逐条变更）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
REPORT_DIR = os.path.join(ROOT, "docs", "r19.19-ak-rear-sight")

# A1：照门下移一格的五把枪（键 = gunId）
A1_GUNS = {
    "5ac66d9b5acfc4001633997a": "AK-105",
    "5bf3e03b0db834001d2c4a9c": "AK-74",
    "5644bd2b4bdc2d3b4c8b4572": "AK-74N",
    "5bf3e0490db83400196199af": "AKS-74",
    "5ab8e9fcd8ce870019439434": "AKS-74N",
}
A1_KEY = "mod_sight_rear|mod_sight_rear|"
A1_NOTE = ("R19.19 A1：AK-74 系列照门槽人工校准坐标下移一格（逻辑 r1→r2，列不变）；"
           "自动布局本在 r2，此前被本记录钉在 r1。")

# A2：AKMP-only 子槽记录失效说明（owner = AKM 照门）
A2_OWNER = "59d650cf86f7741b846413a4"
A2_NOTE = ("R19.19 A2：AKM 照门的 AKMP-only 独立子槽已按游戏实测删除（AKM 系只保留"
           "一个照门安装槽，AKMP RS 并入枪身照门槽 allow）；本条记录保留原坐标、"
           "不再生效，且不得迁移到其他槽位。")


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    doc = json.load(open(CALIB, encoding="utf-8"))
    guns = doc.get("guns") or {}

    before_records = sum(len((g.get("slots") or {})) for g in guns.values())
    before_guns = len(guns)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    changes = []

    # ---- A1：五把枪的照门记录下移一格 ----
    for gid, name in A1_GUNS.items():
        gun = guns.get(gid) or {}
        rec = (gun.get("slots") or {}).get(A1_KEY)
        if rec is None:
            changes.append({"gun": name, "gunId": gid, "key": A1_KEY,
                            "status": "missing-record"})
            continue
        old = {"logicalRow": rec.get("logicalRow"), "col": rec.get("col"),
               "displayRow": rec.get("displayRow"), "topPad": rec.get("topPad")}
        if rec.get("logicalRow") == 2 and rec.get("col") == 6:
            changes.append({"gun": name, "gunId": gid, "key": A1_KEY,
                            "status": "already-at-r2c6", "before": old})
            continue
        if rec.get("logicalRow") != 1:
            # 与预期不符：不动坐标，报告出来（不强行套用统一坐标）
            changes.append({"gun": name, "gunId": gid, "key": A1_KEY,
                            "status": "unexpected-coords-untouched", "before": old})
            continue
        rec["logicalRow"] = 2
        rec["displayRow"] = 2
        rec["note"] = A1_NOTE
        rec["updatedAt"] = now
        changes.append({"gun": name, "gunId": gid, "key": A1_KEY,
                        "status": "moved-down-one", "before": old,
                        "after": {"logicalRow": 2, "col": rec.get("col"),
                                  "displayRow": 2}})

    # ---- A2：AKMP-only 子槽记录标记失效（保留、不迁移） ----
    for gid, gun in guns.items():
        for key, rec in (gun.get("slots") or {}).items():
            owner = rec.get("ownerItemId") or (key.split("|")[2] if key.count("|") >= 2 else "")
            if owner != A2_OWNER:
                continue
            old_note = (rec.get("note") or "").strip()
            if old_note == A2_NOTE:
                changes.append({"gun": gun.get("name"), "gunId": gid, "key": key,
                                "status": "already-marked"})
                continue
            rec["note"] = A2_NOTE
            rec["updatedAt"] = now
            changes.append({"gun": gun.get("name"), "gunId": gid, "key": key,
                            "status": "marked-stale", "beforeNote": old_note,
                            "coords-preserved": {"logicalRow": rec.get("logicalRow"),
                                                 "col": rec.get("col")}})

    after_records = sum(len((g.get("slots") or {})) for g in guns.values())
    report = {
        "schema": "r19.19-calibration-migration/1",
        "gunsBefore": before_guns,
        "gunsAfter": len(guns),
        "recordsBefore": before_records,
        "recordsAfter": after_records,
        "recordsDeleted": 0,
        "changes": changes,
    }
    with open(CALIB, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(REPORT_DIR, "calibration-migration.json"), "w",
              encoding="utf-8", newline="") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "changes"},
                     ensure_ascii=False))
    for c in changes:
        print(" ", c.get("status"), "|", c.get("gun"), "|", c.get("key", "")[:52])


if __name__ == "__main__":
    main()
