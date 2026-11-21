# -*- coding: utf-8 -*-
"""R19.18 数据层槽位修正执行器：对当前 data/items.json 套用 tools/slotfix.py 的修正表。

用法：python tools/r1926_datafix.py [--dry-run]
输出：docs/r19.18-slot-fix-audit/data-fix-report.json
备份：data/items.json.r1918.bak.json（只备份一次，后续运行不覆盖）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import slotfix  # noqa: E402

ITEMS = os.path.join(ROOT, "data", "items.json")
BACKUP = os.path.join(ROOT, "data", "items.json.r1918.bak.json")
OUT_DIR = os.path.join(ROOT, "docs", "r19.18-slot-fix-audit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(ITEMS, encoding="utf-8") as f:
        payload = json.load(f)
    items = payload.get("items") or {}

    before = {}
    for item_id in slotfix.R1918_ITEM_SLOT_FIXES:
        rec = items.get(item_id) or {}
        before[item_id] = {
            "name": rec.get("n") or item_id,
            "slots": [(s.get("id"), s.get("sid"), len(s.get("allow") or []))
                      for s in (rec.get("slots") or [])],
        }

    report = slotfix.apply_item_slot_fixes(items)

    os.makedirs(OUT_DIR, exist_ok=True)
    if not args.dry_run:
        if not os.path.exists(BACKUP):
            shutil.copy2(ITEMS, BACKUP)
        tmp = ITEMS + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ITEMS)

    after = {}
    for item_id in slotfix.R1918_ITEM_SLOT_FIXES:
        rec = items.get(item_id) or {}
        after[item_id] = {
            "name": rec.get("n") or item_id,
            "slots": [(s.get("id"), s.get("sid"), len(s.get("allow") or []))
                      for s in (rec.get("slots") or [])],
        }

    out = {
        "generatedFor": "R19.18",
        "dryRun": bool(args.dry_run),
        "backup": os.path.relpath(BACKUP, ROOT).replace("\\", "/") if os.path.exists(BACKUP) else None,
        "before": before,
        "after": after,
        "report": report,
    }
    with open(os.path.join(OUT_DIR, "data-fix-report.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"dryRun": out["dryRun"],
                      "fixed": [r["name"] for r in report if r["status"] == "fixed"],
                      "unchanged": [r["name"] for r in report if r["status"] != "fixed"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
