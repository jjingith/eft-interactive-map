# -*- coding: utf-8 -*-
"""r64：按游戏真值修正本地数据（最小范围替换）。
1) data/armor-ricochet.json：6 条 RicochetParams 对齐 data/game-truth/armor_items.json
2) data/items.json：破碎面具补 cl=1（仅该条记录内的一个字段）
只读游戏，写本地数据；改前备份到临时目录。
"""
import json, os, re, shutil, time

ROOT = r"D:\personal\trae\02-塔科夫\eft-interactive-map"
TMP = r"C:\Users\Administrator\Documents\Trae-CN\temp_20261104_02"
RI = os.path.join(ROOT, "data", "armor-ricochet.json")
ITEMS = os.path.join(ROOT, "data", "items.json")
TRUTH = os.path.join(ROOT, "data", "game-truth", "armor_items.json")
DIFF = os.path.join(ROOT, "docs", "r58b-game-truth-diff.json")

MASK_ID = "5b432b2f5acfc4771e1c6622"


def num(v):
    return str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else repr(float(v))


def backup(path):
    dst = os.path.join(TMP, "r64-backup-" + os.path.basename(path) + "." + time.strftime("%H%M%S"))
    shutil.copy2(path, dst)
    return dst


def patch_ricochet():
    truth = json.load(open(TRUTH, encoding="utf-8"))["items"]
    diff = json.load(open(DIFF, encoding="utf-8"))
    ids = [d["id"] for d in diff["diffs"] if d["field"] == "ricochetParams"]
    raw = open(RI, encoding="utf-8").read()
    before = json.loads(raw)
    bk = backup(RI)

    changes = []
    for iid in ids:
        rp = truth[iid]["props"]["RicochetParams"]
        m = re.search(r'("%s": \{)([^}]*)(\})' % iid, raw)
        if not m:
            raise SystemExit("ricochet entry not found: " + iid)
        body = m.group(2)
        old = dict(re.findall(r'"([xyz])": ([0-9.]+)', body))
        newbody = body
        for k in ("x", "y", "z"):
            newbody = re.sub(r'("%s": )([0-9.]+)' % k, lambda mm: mm.group(1) + num(rp[k]), newbody, count=1)
        raw = raw[:m.start(2)] + newbody + raw[m.end(2):]
        changes.append((iid, before["helmets"][iid]["n"],
                        {k: float(v) for k, v in old.items()},
                        {k: rp[k] for k in ("x", "y", "z")}))

    after = json.loads(raw)
    # 其它条目必须逐字节等值（除目标 6 条）
    for k, v in before["helmets"].items():
        if k not in ids and after["helmets"][k] != v:
            raise SystemExit("unexpected change: " + k)
    if len(after["helmets"]) != len(before["helmets"]):
        raise SystemExit("entry count changed")
    with open(RI, "w", encoding="utf-8", newline="\n") as f:
        f.write(raw)
    return changes, bk


def patch_mask():
    st0 = os.stat(ITEMS)
    raw = open(ITEMS, encoding="utf-8").read()
    st1 = os.stat(ITEMS)
    if (st1.st_mtime, st1.st_size) != (st0.st_mtime, st0.st_size):
        raise SystemExit("items.json changed while reading; retry")
    if raw.count('"%s":{' % MASK_ID) != 1:
        raise SystemExit("mask id not unique / not found")

    start = raw.find('"%s":{' % MASK_ID)
    win = raw[start:start + 4000]
    assert '"cl":' not in win.split('"aps"')[0], "cl already present in mask record"
    old = '"dur":40,"cats":'
    if win.count(old) != 1:
        raise SystemExit("anchor ambiguous in mask record: %d" % win.count(old))
    bk = backup(ITEMS)
    new_win = win.replace(old, '"dur":40,"cl":1,"cats":', 1)
    raw2 = raw[:start] + new_win + raw[start + 4000:]
    data = json.loads(raw2)
    rec = data["items"][MASK_ID] if isinstance(data, dict) and "items" in data else data[MASK_ID]
    assert rec.get("cl") == 1 and rec.get("dur") == 40, rec.get("cl")
    with open(ITEMS, "w", encoding="utf-8", newline="\n") as f:
        f.write(raw2)
    st2 = os.stat(ITEMS)
    return {"id": MASK_ID, "cl": rec.get("cl"), "dur": rec.get("dur"),
            "mtime_before": st0.st_mtime, "size_before": st0.st_size,
            "mtime_after": st2.st_mtime, "size_after": st2.st_size}, bk


if __name__ == "__main__":
    ch, bk1 = patch_ricochet()
    print("ricochet patched:", len(ch), "backup:", bk1)
    for iid, n, o, nv in ch:
        print("  %s %-52s %s -> %s" % (iid, n, o, nv))
    info, bk2 = patch_mask()
    print("mask patched:", info, "backup:", bk2)
