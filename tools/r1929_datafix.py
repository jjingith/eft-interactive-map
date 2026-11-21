# -*- coding: utf-8 -*-
"""R19.21 数据层套用：AKMP 真实父子关系修正（任务 3.1/3.2/3.3）。

1) 恢复三种标准照门（6P44 Sb.1-30 / 6P20 Sb.2 / 6P1 Sb.2）的 AKMP 子槽
   （R19.18 修正表误删；原始定义取自 data/items.json.r1918.bak.json）；
2) 删除「AKM 照门 6P1 Sb.2-1」（59d650cf…）上的 AKMP 子槽（并列假设错误建模）。

幂等：已存在同 id 子槽则跳过；重复执行不产生重复子槽。
带备份（*.r1921.bak.json）+ 报告（docs/r19.21-akmp-parent-fix/data-fix.json）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slotfix  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPORT_DIR = os.path.join(ROOT, "docs", "r19.21-akmp-parent-fix")

AKMP_RS = "5a0ed824fcdbcb0176308b0d"
# 三个父照门 → AKMP 子槽定义（原始上游定义，来自 R19.18 备份）
RESTORE = {
    "5ac733a45acfc400192630e2": {   # 6P44 Sb.1-30（AK-105 照门）
        "id": "5ac733a45acfc400192630e4", "sid": "mod_sight_rear", "label": "照门",
        "allow": [AKMP_RS],
        "fix": "R19.21：恢复 AKMP 子槽（AKMP 是 6P44 Sb.1-30 的子配件，父件正上方同列显示）",
    },
    "5ac72e475acfc400180ae6fe": {   # 6P20 Sb.2（AK-74M 照门）
        "id": "5ac72e475acfc400180ae700", "sid": "mod_sight_rear", "label": "照门",
        "allow": [AKMP_RS],
        "fix": "R19.21：恢复 AKMP 子槽（AKMP 是 6P20 Sb.2 的子配件，父件正上方同列显示）",
    },
    "5649b0544bdc2d1b2b8b458a": {   # 6P1 Sb.2（AK-74 照门）
        "id": "5a0ee12cfcdbcb001912fa64", "sid": "mod_sight_rear", "label": "照门",
        "allow": [AKMP_RS],
        "fix": "R19.21：恢复 AKMP 子槽（AKMP 是 6P1 Sb.2 的子配件，父件正上方同列显示）",
    },
}


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    items_path = os.path.join(DATA, "items.json")
    bak = items_path + ".r1921.bak.json"
    if not os.path.exists(bak):
        shutil.copy2(items_path, bak)

    doc = json.load(open(items_path, encoding="utf-8"))
    items = doc["items"]
    report = {"schema": "r19.21-data-fix/1", "restored": [], "dropped": [], "skipped": []}

    # ---- 1) 恢复三个父照门的 AKMP 子槽（幂等）----
    for parent_id, sub in RESTORE.items():
        rec = items.get(parent_id)
        if rec is None:
            report["skipped"].append({"itemId": parent_id, "why": "missing-item"})
            continue
        slots = rec.setdefault("slots", [])
        if any(s.get("id") == sub["id"] for s in slots):
            report["skipped"].append({"itemId": parent_id, "slotId": sub["id"], "why": "already-present"})
            continue
        slots.append(dict(sub))
        report["restored"].append({"itemId": parent_id, "name": rec.get("n"),
                                   "slotId": sub["id"]})

    # ---- 2) 删除 AKM 照门的 AKMP 子槽（R1921 表）----
    for item_id, fix in slotfix.R1921_ITEM_SLOT_FIXES.items():
        rec = items.get(item_id)
        if rec is None:
            report["skipped"].append({"itemId": item_id, "why": "missing-item"})
            continue
        drop = set(fix.get("drop") or [])
        slots = rec.get("slots") or []
        kept = [s for s in slots if s.get("id") not in drop]
        dropped = [s.get("id") for s in slots if s.get("id") in drop]
        if dropped:
            rec["slots"] = kept
            for s in kept:
                s["fix"] = fix.get("evidence")
            report["dropped"].append({"itemId": item_id, "name": rec.get("n"),
                                      "slotIds": dropped, "evidence": fix.get("evidence")})
        else:
            report["skipped"].append({"itemId": item_id, "slotIds": sorted(drop), "why": "already-absent"})

    tmp = items_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, items_path)

    out = os.path.join(REPORT_DIR, "data-fix.json")
    with open(out, "w", encoding="utf-8", newline="") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
