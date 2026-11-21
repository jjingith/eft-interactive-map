# -*- coding: utf-8 -*-
"""R19.19 数据层套用：AK 照门槽位修复（任务 A2）。

1) 删除「AKM 照门」上不应该独立存在的 AKMP-only 子槽（tools/slotfix.py R1919_ITEM_SLOT_FIXES）；
2) 把 AKMP系统照门装置并入枪身唯一照门槽 mod_sight_rear 的 allow
   （tools/slotfix.py R1919_GUN_SLOT_ALLOW_ADDS）——保留 AKM 枪族合法 AKMP 兼容能力。

带备份（*.r1919.bak.json）+ 报告（docs/r19.19-ak-rear-sight/data-fix.json）。
与 tools/fetch_data.py 共用同一张表，下次刷新上游数据不会回退。
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
REPORT_DIR = os.path.join(ROOT, "docs", "r19.19-ak-rear-sight")


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)

    items_path = os.path.join(DATA, "items.json")
    guns_path = os.path.join(DATA, "gunslots.json")

    for path in (items_path, guns_path):
        bak = path + ".r1919.bak.json"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)

    items_doc = json.load(open(items_path, encoding="utf-8"))
    guns_doc = json.load(open(guns_path, encoding="utf-8"))

    item_report = slotfix.apply_item_slot_fixes(items_doc["items"], slotfix.R1919_ITEM_SLOT_FIXES)
    # allow 并入必须同时写两处：gun_builder.buildTree 读 items.json 里枪械自身的 slots，
    # 而 gunslots.json 是槽位树展示/审计数据源 —— 两处 allow 必须一致。
    gun_report = slotfix.apply_gun_slot_allow_adds(guns_doc["guns"], slotfix.R1919_GUN_SLOT_ALLOW_ADDS)
    gun_report_items = slotfix.apply_gun_slot_allow_adds(items_doc["items"], slotfix.R1919_GUN_SLOT_ALLOW_ADDS)

    # 原子写回
    tmp = items_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(items_doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, items_path)

    tmp = guns_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(guns_doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, guns_path)

    report = {
        "schema": "r19.19-data-fix/1",
        "itemSlotFixes": item_report,
        "gunAllowAdds": gun_report,
        "gunAllowAddsItemsJson": gun_report_items,
    }
    out = os.path.join(REPORT_DIR, "data-fix.json")
    with open(out, "w", encoding="utf-8", newline="") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("items fixed:", json.dumps(item_report, ensure_ascii=False))
    print("guns fixed :", json.dumps(gun_report, ensure_ascii=False))
    print("report ->", out)


if __name__ == "__main__":
    main()
