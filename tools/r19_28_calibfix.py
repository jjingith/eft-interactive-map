# -*- coding: utf-8 -*-
"""R19.28 需求一：把 AK 照门系里 3 条「照门主槽」的手动校准从 r1c6 改回 r2c6。

范围（先确认再改，改动之外一个字节都不碰）：
  5a0ec13bfcdbcb00165aa685 AKMN   7.62x39 突击步枪
  5abcbc27d8ce8700182eceeb AKMSN  7.62x39 突击步枪
  59e6152586f77473dc057aa1 VPO-136 野猪-KM 7.62x39 卡宾枪
每个枪只改 1 条记录（key = "mod_sight_rear|mod_sight_rear|"）：
  logicalRow 1 -> 2，displayRow 1 -> 2，note 追加 R19.28 说明。
其余 152 把枪、以及这三把枪里的其它记录（含 R19.21 留档的失效 AKMP 子槽记录）保持原样。

用法：python tools/r19_28_calibfix.py            # 只打印差异
      python tools/r19_28_calibfix.py --write    # 落盘
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "gun-layout-calibration.json")

TARGETS = {
    "5a0ec13bfcdbcb00165aa685": "AKMN 7.62x39 突击步枪",
    "5abcbc27d8ce8700182eceeb": "AKMSN 7.62x39 突击步枪",
    "59e6152586f77473dc057aa1": "VPO-136 野猪-KM 7.62x39 卡宾枪",
}
KEY = "mod_sight_rear|mod_sight_rear|"
NOTE = ("R19.28 需求一：AK 照门系统一锚定 r2c6（原手动校准 r1c6 使照门落在第 1 行，"
        "与需求规定的第二行第六列不符）；col 保持 6 不变。")


def main():
    write = "--write" in sys.argv
    with io.open(PATH, encoding="utf-8") as f:
        data = json.load(f)
    guns = data["guns"]
    changes = []
    for gid, name in sorted(TARGETS.items()):
        g = guns.get(gid)
        if not g:
            changes.append((name, gid, "缺失", "", "跳过"))
            continue
        rec = (g.get("slots") or {}).get(KEY)
        if not rec:
            changes.append((name, gid, KEY, "记录缺失", "跳过"))
            continue
        old = (rec.get("logicalRow"), rec.get("col"), rec.get("displayRow"))
        if old[0] == 2 and old[2] == 2:
            changes.append((name, gid, KEY, "r%sc%s/disp%s" % old, "已是 r2c6"))
            continue
        changes.append((name, gid, KEY, "r%sc%s/disp%s" % old, "-> r2c6/disp2"))
        if write:
            rec["logicalRow"] = 2
            rec["col"] = 6
            rec["displayRow"] = 2
            rec["note"] = ((rec.get("note") or "") + " " + NOTE).strip()
            if "autoRow" not in rec:
                rec["autoRow"] = 2
            if "autoCol" not in rec:
                rec["autoCol"] = 6
    for c in changes:
        print("  %-28s %s  %s  %s -> %s" % (c[0], c[1], c[2], c[3], c[4]))
    if write:
        # 原文件是 CRLF，落盘必须保持 CRLF，否则整份数据被判为全量改写
        with io.open(PATH, "w", encoding="utf-8", newline="\r\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print("\n已写入 %s" % PATH)
    else:
        print("\n（只读预览，加 --write 落盘）")


if __name__ == "__main__":
    main()
