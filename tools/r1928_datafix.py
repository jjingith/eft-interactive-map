# -*- coding: utf-8 -*-
"""R19.20 数据层恢复：AKM 照门 AKMP 子槽并列布局（任务 3.2）。

游戏内实测：AKM 照门与 AKMP 系统照门装置是**并列的两个照门槽位**（左 AKM / 右 AKMP）。
R19.19 把 AKMP 并入枪身照门槽 allow、删除 AKM 照门的 AKMP 子槽——本轮纠正：

1) 恢复「AKM 照门」的 AKMP-only 子槽（slot id 5a0eda49fcdbcb001912fa61）——
   真实安装语义保留（AKMP 仍是 AKM 照门的子槽件），仅显示层并列右置（见 app.js）；
2) 撤回 R19.19 的 allow 并入：从五把枪（AKM/AKMS/AKMN/AKMSN/VPO-136）的
   mod_sight_rear allow 移除 AKMP RS —— 两个槽位候选不混淆。

作用范围仅限安装「AKM 照门」的枪系；VPO-209 / AK-103 / AK-104 / 5.45·5.56 枪械不动。
带备份（*.r1920.bak.json）+ 报告（docs/r19.20-akm-akmp-parallel/data-fix.json）。
"""
from __future__ import annotations

import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPORT_DIR = os.path.join(ROOT, "docs", "r19.20-akm-akmp-parallel")

AKM_SIGHT = "59d650cf86f7741b846413a4"          # AKM 照门
AKMP_RS = "5a0ed824fcdbcb0176308b0d"            # AKMP系统照门装置
AKMP_SUBSLOT = {
    "id": "5a0eda49fcdbcb001912fa61",
    "sid": "mod_sight_rear",
    "label": "照门",
    "allow": [AKMP_RS],
    "fix": ("R19.20：恢复 AKM 照门的 AKMP 子槽（游戏内与 AKM 照门并列的第二个照门位，"
            "左 AKM / 右 AKMP）；真实父子关系保留，显示层并列右置"),
}
GUNS = {
    "59d6088586f774275f37482f": "AKM",
    "59ff346386f77477562ff5e2": "AKMS",
    "5a0ec13bfcdbcb00165aa685": "AKMN",
    "5abcbc27d8ce8700182eceeb": "AKMSN",
    "59e6152586f77473dc057aa1": "VPO-136",
}


def main() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    items_path = os.path.join(DATA, "items.json")
    guns_path = os.path.join(DATA, "gunslots.json")
    for p in (items_path, guns_path):
        bak = p + ".r1920.bak.json"
        if not os.path.exists(bak):
            shutil.copy2(p, bak)

    items_doc = json.load(open(items_path, encoding="utf-8"))
    guns_doc = json.load(open(guns_path, encoding="utf-8"))
    report = {"schema": "r19.20-data-fix/1", "subSlotRestored": [], "allowReverted": []}

    # ---- 1) 恢复 AKM 照门的 AKMP 子槽（items.json）----
    for src_name, table in (("items.json", items_doc["items"]), ("gunslots-noop", {})):
        rec = table.get(AKM_SIGHT) if table else None
        if rec is None:
            continue
        slots = rec.setdefault("slots", [])
        if not any(s.get("id") == AKMP_SUBSLOT["id"] for s in slots):
            slots.append(dict(AKMP_SUBSLOT))
            report["subSlotRestored"].append({"source": src_name, "itemId": AKM_SIGHT})

    # ---- 2) 撤回 allow 并入（items.json 枪械槽 + gunslots.json 两处）----
    for src_name, table in (("items.json", items_doc["items"]), ("gunslots.json", guns_doc["guns"])):
        for gid, name in GUNS.items():
            gun = table.get(gid)
            if not gun:
                continue
            for slot in gun.get("slots") or []:
                if slot.get("sid") != "mod_sight_rear":
                    continue
                allow = slot.get("allow") or []
                if AKMP_RS in allow:
                    allow.remove(AKMP_RS)
                    slot["allow"] = allow
                    report["allowReverted"].append({"source": src_name, "gun": name, "gunId": gid})
                if (slot.get("fix") or "").startswith("R19.19 A2"):
                    slot["fix"] = ("R19.20：AKMP RS 已从枪身照门槽 allow 撤回——"
                                   "AKMP 走 AKM 照门的并列子槽（左 AKM / 右 AKMP）")

    for path, doc in ((items_path, items_doc), (guns_path, guns_doc)):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)

    out = os.path.join(REPORT_DIR, "data-fix.json")
    with open(out, "w", encoding="utf-8", newline="") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
