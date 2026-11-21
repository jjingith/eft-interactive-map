#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_gunsmith.py — 构建期生成 data/gunsmith.json（枪匠任务装配约束，运行期离线使用）

对应参考站 db4tarkov.com/gun 的 **Gunsmith** 页签。该页签每条枪匠任务会给出：
任务等级 / 目标枪 / 属性约束（如 Recoil ≤ 400）/ 必含类别（如 Must include silencer）
/ 必装配件（Mods）。本脚本把这些约束从上游缓存里完整提取出来。

数据来源（全部为本地已缓存的 tarkov.dev 上游数据，构建期一次性读取，不覆盖既有文件）：

    data/tasks/raw/tasks.<mode>.json      ← 原始 objective，含 buildAttributes /
                                            containsAll / containsCategory（**关键**：
                                            构建后的 data/tasks/tasks.<mode>.json 只保留
                                            了 containsAll，属性约束与类别约束在上一次
                                            构建中漏提取，本脚本直接从原始缓存补齐）
    data/tasks/tasks.<mode>.json          ← 中文任务名 / 商人 / 等级
    data/items.json                       ← 物品中文名、子槽定义、类别 id 反查表
    data/gunslots.json                    ← 枪械顶层槽位（装配链的起点）
    data/tasks/raw/tasks_zh.<mode>.json   ← 中文名兜底

产出每条任务的 **装配链**（chain）：从枪根出发，沿槽位逐层展开，
[ {path, slot, id}, ... ]，其中 path 与前端 gun_builder.js 的 buildTree 完全同构
（sid 重复时追加 "#n"），因此前端可以直接写进 installed 映射完成一键装配。

**不编造任何数值**：上游给什么就写什么；上游 buildAttributes 里 value=0 且为 ">="
的项视为「无约束」占位，予以剔除并记入 notes.droppedZeroAttrs 以便追溯。

用法：
    python tools/build_gunsmith.py             # 生成 data/gunsmith.json
    python tools/build_gunsmith.py --check     # 只校验现有文件与缓存是否一致（不写盘）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "gunsmith.json")
MODES = ("regular", "pve", "pvps")

SCHEMA = 1

# buildAttributes 的 10 个属性键（上游固定顺序）
ATTR_KEYS = [
    "accuracy", "durability", "effectiveDistance", "ergonomics", "height",
    "magazineCapacity", "muzzleVelocity", "recoil", "weight", "width",
]
ATTR_ZH = {
    "accuracy": "精度",
    "durability": "耐久度",
    "effectiveDistance": "有效射程",
    "ergonomics": "人机工效",
    "height": "高度",
    "magazineCapacity": "弹匣容量",
    "muzzleVelocity": "枪口初速",
    "recoil": "后坐力",
    "weight": "重量",
    "width": "宽度",
}
OP_ZH = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "="}

# 装配链求解的硬上限：超过就放弃（防止上游数据异常时无限展开）
MAX_DEPTH = 8
MAX_CHAINS_PER_ITEM = 6    # 每个可达配件最多保存几条候选链（用于冲突时回溯）
MAX_EXPAND = 400000        # 单次 BFS 展开节点上限


def jload(*parts):
    with open(os.path.join(BASE, *parts), "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 装配链求解
def sid_at(slot, i, used):
    """复制 gun_builder.js buildTree() 的 path 片段生成规则（含重复 sid 的 #n 后缀）"""
    sid = slot.get("sid") or slot.get("id") or ("s%d" % i)
    n = used.get(sid, 0)
    used[sid] = n + 1
    if n > 0:
        sid = "%s#%d" % (sid, n)
    return sid


def slots_of(rec):
    return (rec or {}).get("slots") or []


def solve_chains(items, gunslots, gun_id, wanted):
    """从枪根 BFS 展开所有可达槽位，返回 {配件id: [chain, ...]}

    chain 形如 [{"path": "mod_handguard/mod_foregrip", "slot": "前握把", "id": "<配件id>"}]
    最后一项即目标配件本身，前面的项是必须先装的中间件（护木 / 导轨 / 基座…）。
    """
    root = gunslots.get(gun_id)
    if not root:
        return {}
    want = set(str(w) for w in wanted)
    found = {w: [] for w in want}
    # 队列元素: (物品记录dict, prefix, 当前链list, 深度)
    q = deque([({"slots": root.get("slots") or []}, "", [], 0)])
    seen = set()
    expanded = 0
    while q:
        rec, prefix, chain, depth = q.popleft()
        if depth > MAX_DEPTH:
            continue
        used = {}
        for i, slot in enumerate(slots_of(rec)):
            sid = sid_at(slot, i, used)
            path = ("%s/%s" % (prefix, sid)) if prefix else sid
            label = slot.get("label") or slot.get("sid") or sid
            for aid in (slot.get("allow") or []):
                aid = str(aid)
                newchain = chain + [{"path": path, "slot": label, "id": aid}]
                if aid in want and len(found[aid]) < MAX_CHAINS_PER_ITEM:
                    found[aid].append(newchain)
                child = items.get(aid) or {}
                if not slots_of(child):
                    continue
                key = (aid, path, depth)
                if key in seen:
                    continue
                seen.add(key)
                expanded += 1
                if expanded > MAX_EXPAND:
                    q.clear()
                    break
                q.append((child, path, newchain, depth + 1))
            if expanded > MAX_EXPAND:
                break
        if expanded > MAX_EXPAND:
            break
    # 每条配件的候选链按长度升序（短的优先，装起来中间件最少）
    for k in found:
        found[k].sort(key=len)
    return found


# ---------------------------------------------------------------- 主流程
def build_mode(mode, items, gunslots, cat_zh, notes):
    raw = jload("data", "tasks", "raw", "tasks.%s.json" % mode)
    raw_tasks = raw["data"]["tasks"] if isinstance(raw, dict) and "data" in raw else raw
    built = jload("data", "tasks", "tasks.%s.json" % mode)["tasks"]
    bname = {tid: (t or {}).get("nameZh") for tid, t in built.items()}

    quests = []
    cache_chains = {}
    for t in raw_tasks.values():
        bt = built.get(t.get("id")) or {}
        for ob in (t.get("objectives") or []):
            if ob.get("type") != "buildWeapon":
                continue
            gun_id = str(ob.get("item") or "")
            gun = items.get(gun_id) or {}

            # --- 属性约束 ---
            ba = ob.get("buildAttributes") or {}
            attrs = []
            for k in ATTR_KEYS:
                v = ba.get(k)
                if not v:
                    continue
                val = v.get("value")
                cm = v.get("compareMethod") or ">="
                # 上游用 value=0 + ">=" 表示「无约束」，剔除
                if cm == ">=" and (val is None or val == 0):
                    notes["droppedZeroAttrs"] += 1
                    continue
                if cm not in OP_ZH:
                    notes["unknownOps"].add("%s:%s" % (k, cm))
                attrs.append({
                    "k": k, "zh": ATTR_ZH.get(k, k),
                    "op": cm, "opZh": OP_ZH.get(cm, cm), "v": val,
                })

            # --- 必含类别 ---
            cats = []
            for c in (ob.get("containsCategory") or []):
                cid = c.get("id") if isinstance(c, dict) else c
                if not cid:
                    continue
                cid = str(cid)
                zh = cat_zh.get(cid)
                if not zh:
                    notes["unknownCats"].add(cid)
                cats.append({"id": cid, "en": (c.get("name") if isinstance(c, dict) else None),
                             "zh": zh or (c.get("name") if isinstance(c, dict) else cid)})

            # --- 必装配件 + 装配链 ---
            all_ids = [str(i) for i in (ob.get("containsAll") or [])]
            if gun_id and all_ids:
                if gun_id not in cache_chains:
                    cache_chains[gun_id] = solve_chains(items, gunslots, gun_id, all_ids)
                chains = cache_chains[gun_id]
            else:
                chains = {}
            must = []
            for i in all_ids:
                it = items.get(i) or {}
                ch = (chains.get(i) or [])
                if not ch:
                    notes["unsolvedParts"].add("%s|%s" % (gun_id, i))
                must.append({
                    "id": i,
                    "name": it.get("n") or i,
                    "chain": ch[0] if ch else [],       # 主链（最短）
                    "alts": ch[1:],                      # 备选链（冲突时回溯）
                })

            quests.append({
                "id": t.get("id"),
                "objId": ob.get("id"),
                "name": bname.get(t.get("id")) or bt.get("nameZh") or t.get("name") or t.get("id"),
                "lvl": bt.get("minLevel", t.get("minPlayerLevel")),
                "trader": bt.get("traderZh") or t.get("traderName") or "",
                "gun": {"id": gun_id, "name": gun.get("n") or gun_id},
                "attrs": attrs,
                "cats": cats,
                "must": must,
            })

    quests.sort(key=lambda q: (q["lvl"] if isinstance(q["lvl"], int) else 0, q["name"] or ""))
    return quests


def build():
    items = jload("data", "items.json")["items"]
    gunslots = jload("data", "gunslots.json")["guns"]
    # 类别 id → 中文（audit.categoryIds 是 name→id，需要反转）
    cat_ids = jload("data", "items.json")["audit"].get("categoryIds") or {}
    rev = {v: k for k, v in cat_ids.items()}
    CAT_ZH = {
        "550aa4cd4bdc2dd8348b456c": "消音器",
        "55818b164bdc2ddc698b456c": "战术组合装置",
        "55818af64bdc2d5b648b4570": "前握把",
    }
    cat_zh = {}
    for cid, en in rev.items():
        cat_zh[cid] = CAT_ZH.get(cid, en)
    # 已知但 audit 未收录的也要有中文
    for cid, zh in CAT_ZH.items():
        cat_zh.setdefault(cid, zh)

    notes = {"droppedZeroAttrs": 0, "unknownOps": set(),
             "unknownCats": set(), "unsolvedParts": set()}

    modes = {}
    for m in MODES:
        qs = build_mode(m, items, gunslots, cat_zh, notes)
        modes[m] = {"count": len(qs), "quests": qs}

    doc = {
        "schema": SCHEMA,
        "generatedAt": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+0800"),
        "source": {
            "raw": "data/tasks/raw/tasks.<mode>.json（原始 objective：buildAttributes / containsAll / containsCategory）",
            "zh": "data/tasks/tasks.<mode>.json（中文任务名 / 商人 / 等级）",
            "items": "data/items.json（中文名、子槽、类别 id 反查）",
            "slots": "data/gunslots.json（枪械顶层槽位）",
            "license": "tarkov.dev 社区公开数据（非官方）",
            "note": "属性约束与类别约束在构建后的 tasks.<mode>.json 中缺失，"
                    "本文件直接从原始缓存补齐，不推导、不补全。",
        },
        "attrKeys": ATTR_KEYS,
        "attrZh": ATTR_ZH,
        "opZh": OP_ZH,
        "categories": cat_zh,
        "modes": modes,
        "notes": {
            "droppedZeroAttrs": notes["droppedZeroAttrs"],
            "unknownOps": sorted(notes["unknownOps"]),
            "unknownCats": sorted(notes["unknownCats"]),
            "unsolvedParts": sorted(notes["unsolvedParts"]),
            "maxDepth": MAX_DEPTH,
        },
    }
    return doc


def fingerprint(doc):
    """--check 用的内容指纹：包含所有会改变前端行为的字段，但不含 generatedAt"""
    fp = {"schema": doc.get("schema")}
    for m in MODES:
        md = (doc.get("modes") or {}).get(m) or {}
        fp[m] = [[
            q.get("id"), q.get("objId"), q.get("name"), q.get("lvl"), q.get("trader"),
            (q.get("gun") or {}).get("id"),
            [(a.get("k"), a.get("op"), a.get("v")) for a in (q.get("attrs") or [])],
            [(c.get("id")) for c in (q.get("cats") or [])],
            [(p.get("id"), tuple((s.get("path"), s.get("id")) for s in (p.get("chain") or [])))
             for p in (q.get("must") or [])],
        ] for q in (md.get("quests") or [])]
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    args = ap.parse_args()

    doc = build()
    text = json.dumps(doc, ensure_ascii=False, indent=None, separators=(",", ":"))

    if args.check:
        # 与 build_ammo.py 同一口径：比**内容语义**而不是文本
        # （generatedAt 每次都变，逐字节比较必然 STALE）
        if not os.path.exists(OUT):
            print("MISSING %s" % OUT)
            return 1
        with open(OUT, "r", encoding="utf-8") as f:
            cur = json.load(f)
        new_fp = fingerprint(doc)
        old_fp = fingerprint(cur)
        if new_fp == old_fp:
            print("OK  %s 与缓存一致（schema=%d, 合计 %d 条）"
                  % (os.path.relpath(OUT, BASE), doc["schema"], sum(v["count"] for v in doc["modes"].values())))
            return 0
        for m in MODES:
            if old_fp.get(m) != new_fp.get(m):
                print("STALE %s 模式 %s 需要重建" % (os.path.relpath(OUT, BASE), m))
        return 1

    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, OUT)

    n = sum(v["count"] for v in doc["modes"].values())
    print("WROTE %s  (%d 字节)" % (OUT, len(text)))
    for m in MODES:
        print("  %-8s %d 条枪匠目标" % (m, doc["modes"][m]["count"]))
    print("  合计 %d 条" % n)
    nn = doc["notes"]
    print("  剔除无约束占位属性 %d 项" % nn["droppedZeroAttrs"])
    if nn["unsolvedParts"]:
        print("  !! 无装配链的必装配件 %d 个: %s" % (
            len(nn["unsolvedParts"]), nn["unsolvedParts"][:5]))
    if nn["unknownCats"]:
        print("  !! 未收录类别: %s" % nn["unknownCats"][:5])
    return 0


if __name__ == "__main__":
    sys.exit(main())
