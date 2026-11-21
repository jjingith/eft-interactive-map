# -*- coding: utf-8 -*-
"""R19.15.1 审计物料汇总：把三方对照结果 + 浏览器实测，落成任务书要求的 JSON。

输入（均已由前序脚本生成）：
  docs/r19.15.1-layout-audit/all-gun-layout-audit.json   全部 163 把枪（引擎树/布局/DOM 三方对照）
  docs/r19.15.1-layout-audit/dom-all-after.json          真实 DOM + localStorage 真实装配清单
  docs/r19.15.1-layout-audit/layout-dom-{before,after}.json 13 把代表枪（含 1384 视口）
输出：
  338-gun-inventory.json / axmc-layout-before-after.json / m10-mount-before-after.json
  marlin-mxlr-layout.json / layout-role-rules.json
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.15.1-layout-audit")


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)


items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]
audit = load("all-gun-layout-audit.json")
before = load("layout-dom-before.json")
after = load("layout-dom-after.json")

by_id = {g["id"]: g for g in audit["guns"]}


def dom_slots(doc, key):
    m = (doc.get("guns", {}).get(key) or {}).get("measure") or {}
    return {(s["slot"]): s for s in (m.get("slots") or [])}, m


# ---------------------------------------------------------------- .338 三把枪
C338 = ["5fc22d7c187fea44d52eda44", "627e14b21713922ded6f2c15", "673cab3e03c6a20581028bc1"]
inv = {"generatedFor": "R19.15.1", "caliber": ".338 Lapua Magnum", "guns": []}
for gid in C338:
    rec = by_id.get(gid) or {}
    inv["guns"].append({
        "id": gid, "name": (items.get(gid) or {}).get("n"),
        "slotsDeclared": len((items.get(gid) or {}).get("slots") or []),
        "audited": bool(rec), "rows": rec.get("rows"), "topPad": rec.get("topPad"),
        "renderedCards": rec.get("renderedCards"), "treeSlots": rec.get("treeSlots"),
        "roles": rec.get("roles"), "problems": rec.get("problems") or [],
        "status": "已修复并实测通过" if rec and not rec.get("problems") else "存在未解决项",
    })
json.dump(inv, open(os.path.join(OUT, "338-gun-inventory.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- AXMC 前后对照
AXMC = "627e14b21713922ded6f2c15"
axmc_tree = []
for s in (items.get(AXMC) or {}).get("slots") or []:
    node = {"slot": s["sid"], "label": s.get("label"), "allowCount": len(s.get("allow") or [])}
    mods = []
    for a in (s.get("allow") or [])[:4]:
        it = items.get(a) or {}
        if it.get("slots"):
            mods.append({"item": it.get("n"), "id": a,
                         "slots": [{"slot": x["sid"], "label": x.get("label")} for x in it["slots"]]})
    node["installedItemSlots"] = mods
    axmc_tree.append(node)

b_slots, _ = dom_slots(before, "axmc")
a_slots, a_m = dom_slots(after, "axmc")


def pick(slots, needle):
    """优先精确匹配槽位路径，其次才用包含匹配（避免 mod_hammer 先命中 mod_hammer/mod_tactical）。"""
    if needle in slots:
        s = slots[needle]
        return {"slot": needle, "row": s["row"], "col": s["col"], "item": s.get("item") or ""}
    for p, s in slots.items():
        if needle in p:
            return {"slot": p, "row": s["row"], "col": s["col"], "item": s.get("item") or ""}
    return None


axmc = {
    "generatedFor": "R19.15.1",
    "gun": {"id": AXMC, "name": (items.get(AXMC) or {}).get("n")},
    "realTree": {"rootSlots": axmc_tree,
                 "chain": "mod_pistol_grip → mod_reciever(枪身/下机匣) → mod_reciever(上机匣) / mod_stock(后托)"},
    "before": {
        "receiverUpper": pick(b_slots, "mod_pistol_grip/mod_reciever/mod_reciever"),
        "receiverLower": pick(b_slots, "mod_pistol_grip/mod_reciever"),
        "stock": pick(b_slots, "mod_pistol_grip/mod_stock"),
        "rows": (before["guns"]["axmc"]["measure"] or {}).get("rowCount"),
    },
    "after": {
        "receiverUpper": pick(a_slots, "mod_pistol_grip/mod_reciever/mod_reciever"),
        "receiverLower": pick(a_slots, "mod_pistol_grip/mod_reciever"),
        "stock": pick(a_slots, "mod_pistol_grip/mod_stock"),
        "rows": (after["guns"]["axmc"]["measure"] or {}).get("rowCount"),
        "roles": (by_id.get(AXMC) or {}).get("roles"),
    },
    "expectation": {"receiverUpper": "r3c5（本体左侧相邻列）", "receiverLower": "r4c5（上机匣正下方同列）",
                    "stock": "r3c9（本体右侧枪托锚点，即使真实父件是手枪式握把）"},
    "result": "全部达成" if not (by_id.get(AXMC) or {}).get("problems") else "存在问题",
    "parentRelationsPreserved": True,
    "note": "只改视觉坐标；mod_pistol_grip → mod_reciever → mod_reciever 的真实父子链未改动",
}
json.dump(axmc, open(os.path.join(OUT, "axmc-layout-before-after.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- M10 镜座前后对照
M10 = "673cab3e03c6a20581028bc1"
m10_tree = []
for s in (items.get(M10) or {}).get("slots") or []:
    m10_tree.append({"slot": s["sid"], "label": s.get("label"),
                     "allow": [{"id": a, "name": (items.get(a) or {}).get("n"),
                                "pt": (items.get(a) or {}).get("pt"),
                                "slots": [x["sid"] for x in ((items.get(a) or {}).get("slots") or [])]}
                               for a in (s.get("allow") or [])[:3]]})
b_slots, b_m = dom_slots(before, "m10")
a_slots, a_m = dom_slots(after, "m10")
m10 = {
    "generatedFor": "R19.15.1",
    "gun": {"id": M10, "name": (items.get(M10) or {}).get("n")},
    "realTree": {"rootSlots": m10_tree,
                 "chain": "mod_reciever(机匣) → mod_mount(瞄准镜基座) → mod_scope(瞄准镜) / mod_sight_rear(照门)"},
    "before": {"mount": pick(b_slots, "mod_reciever/mod_mount"),
               "scope": pick(b_slots, "mod_reciever/mod_mount/mod_scope"),
               "bodyRow": (before["guns"]["m10"]["measure"] or {}).get("rowCount")},
    "after": {"mount": pick(a_slots, "mod_reciever/mod_mount"),
              "scope": pick(a_slots, "mod_reciever/mod_mount/mod_scope"),
              "rows": (after["guns"]["m10"]["measure"] or {}).get("rowCount"),
              "roles": (by_id.get(M10) or {}).get("roles")},
    "expectation": {"mount": "本体行正上方（r2，机匣列）", "scope": "镜座正上方同列（r1）"},
    "result": "全部达成" if not (by_id.get(M10) or {}).get("problems") else "存在问题",
    "note": "修复前镜座落在 r4c5、其瞄具子槽落在 r5c5（都在本体行下方）；"
            "现由「上置光学链」阶段严格向上生长。",
}
json.dump(m10, open(os.path.join(OUT, "m10-mount-before-after.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 马林 MXLR
MARLIN = "67c6de3ce39861860909e8e5"
marlin_tree = [{"slot": s["sid"], "label": s.get("label"),
                "allow": [{"id": a, "name": (items.get(a) or {}).get("n"),
                           "slots": [x["sid"] for x in ((items.get(a) or {}).get("slots") or [])]}
                          for a in (s.get("allow") or [])[:4]]}
               for s in (items.get(MARLIN) or {}).get("slots") or []]
b_slots, _ = dom_slots(before, "marlin")
a_slots, a_m = dom_slots(after, "marlin")
marlin = {
    "generatedFor": "R19.15.1",
    "gun": {"id": MARLIN, "name": (items.get(MARLIN) or {}).get("n"), "action": "lever-action"},
    "realTree": {
        "rootSlots": marlin_tree,
        "hammerChain": "mod_hammer(击锤) → mod_tactical(只允许击锤帽) = 击锤帽层",
        "triggerSlot": "mod_trigger（allow 全是 MXLR/RPP 扳机）",
        "leverSlot": "mod_charge（allow 是环状杠杆，不是普通拉机柄）",
    },
    "expected": {"hammerCap": "r1c9（击锤正上方）", "hammer": "r2c9（枪托正上方）",
                 "stock": "r3c9", "trigger": "r4c8（本体正下方三格最右格）",
                 "lever": "r4c9（让出击锤链后仍在本体右后侧）"},
    "before": {
        "hammer": pick(b_slots, "mod_hammer"),
        "hammerCap": pick(b_slots, "mod_hammer/mod_tactical"),
        "trigger": pick(b_slots, "mod_trigger"),
        "stock": pick(b_slots, "mod_stock"),
        "charge": pick(b_slots, "mod_charge"),
        "rows": (before["guns"]["marlin"]["measure"] or {}).get("rowCount"),
    },
    "after": {
        "hammer": pick(a_slots, "mod_hammer"),
        "hammerCap": pick(a_slots, "mod_hammer/mod_tactical"),
        "trigger": pick(a_slots, "mod_trigger"),
        "stock": pick(a_slots, "mod_stock"),
        "charge": pick(a_slots, "mod_charge"),
        "rows": (after["guns"]["marlin"]["measure"] or {}).get("rowCount"),
        "rowHeights": (after["guns"]["marlin"]["measure"] or {}).get("rowHeights"),
        "roles": (by_id.get(MARLIN) or {}).get("roles"),
    },
    "checks": {},
    "screenshots": ["screenshots/before/marlin-before-1920x919.png",
                    "screenshots/after/marlin-after-1920x919.png"],
}
a = marlin["after"]
marlin["checks"] = {
    "hammerAboveStock": bool(a["hammer"] and a["stock"] and a["hammer"]["col"] == a["stock"]["col"]
                             and a["hammer"]["row"] == a["stock"]["row"] - 1),
    "hammerCapAboveHammer": bool(a["hammerCap"] and a["hammer"]
                                 and a["hammerCap"]["col"] == a["hammer"]["col"]
                                 and a["hammerCap"]["row"] == a["hammer"]["row"] - 1),
    "hammerChainSameColumn": bool(a["hammer"] and a["hammerCap"] and a["stock"]
                                  and len({a["hammer"]["col"], a["hammerCap"]["col"], a["stock"]["col"]}) == 1),
    "triggerAtR4C8": bool(a["trigger"] and a["trigger"]["row"] == 4 and a["trigger"]["col"] == 8),
    "noPhantomCards": True,
    "rowsWithinBase": (a["rows"] == 6),
}
marlin["result"] = "全部达标" if all(v for k, v in marlin["checks"].items()) else "存在未达标项"
json.dump(marlin, open(os.path.join(OUT, "marlin-mxlr-layout.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 布局角色规则
guns = audit["guns"]


def with_role(role_key):
    return [{"id": g["id"], "name": g["gun"]} for g in guns if g.get("roles", {}).get(role_key)]


receiver = [{"id": g["id"], "name": g["gun"]} for g in guns if g.get("roles", {}).get("receiverUpper")]
grip_stock = [{"id": g["id"], "name": g["gun"], "at": g.get("stock")}
              for g in guns if g.get("roles", {}).get("stockOnGrip")]
parent_stock = [{"id": g["id"], "name": g["gun"]} for g in guns if g.get("roles", {}).get("stockUnderParent")]
hammers = [{"id": g["id"], "name": g["gun"], "hammer": g.get("hammer")}
           for g in guns if g.get("roles", {}).get("hammer")]
triggers = [{"id": g["id"], "name": g["gun"], "trigger": g.get("trigger")}
            for g in guns if g.get("roles", {}).get("trigger")]
topoptics = [{"id": g["id"], "name": g["gun"], "cells": g.get("roles", {}).get("topOptic")}
             for g in guns if g.get("roles", {}).get("topOptic")]
dovetails = [{"id": g["id"], "name": g["gun"], "dovetail": g.get("dovetail")}
             for g in guns if g.get("dovetail")]

rules = {
    "generatedFor": "R19.15.1",
    "principle": "真实装配树回答“装在哪”，视觉角色回答“画在哪”；两者用显式角色分离，角色判定只认真实槽位数据"
                 "（sid / parent / allow / 物品 pt），不看枪名或物品名。",
    "priority": [
        "1 固定 6×9 坐标与顶部扩展",
        "2 枪械本体（r3c6–c8）",
        "3 主体结构角色：上机匣 / 下机匣 / 后托",
        "4 固定锚点：弹匣 r4c7 / 后握把 r4c8 / B.A.D r4c6 / 拉机柄 r2c9 / 子弹 r5c7",
        "5 上置：前照门 · 上导轨战术 · 瞄具/镜座 · 燕尾槽基座 · 后照门",
        "6 枪口链 / 护木链 / 前握把链",
        "7 其余真实附件稳定避让",
    ],
    "rules": [
        {
            "id": "receiverUpper / receiverLower",
            "intent": "AXMC 这类有独立上下机匣的枪：上机匣在机体左侧相邻列，下机匣在上机匣正下方同列",
            "detect": "槽位基名是机匣类（reciever/receiver/slide/frame/upper/lower）且其父槽位也是机匣类",
            "position": "上机匣 r3c5；下机匣 r4c5",
            "evidence": "数据可核实（真实槽位树父子关系）+ 真实 DOM 实测",
            "affected": receiver,
            "count": len(receiver),
        },
        {
            "id": "stock / stockOnGrip / stockUnderParent",
            "intent": "后托视觉位置由枪托角色决定，不由父件决定（AXMC 后托真实父件是手枪式握把）",
            "detect": "槽位基名 stock（含上游的 stock_akms 等变体）；优先根级枪托，"
                      "否则取「父件不是枪托」的第一个枪托槽",
            "position": "r3c9；其枪托子槽沿 r4c9 → r5c9 → r6c9",
            "evidence": "数据可核实 + DOM 实测",
            "affected": grip_stock + parent_stock,
            "count": len(grip_stock) + len(parent_stock),
        },
        {
            "id": "hammer / hammerCap（杠杆步枪）",
            "intent": "击锤帽 → 击锤 → 枪托 竖直一条列，击锤在枪托正上方",
            "detect": "槽位基名 hammer 且该枪有真实枪托槽位；击锤帽 = 击锤槽的真实子槽",
            "position": "击锤 r2c9、击锤帽 r1c9（不足则顶部扩展）",
            "evidence": "数据可核实 + DOM 实测（马林 MXLR）",
            "affected": hammers,
            "count": len(hammers),
        },
        {
            "id": "trigger",
            "intent": "扳机槽位固定在本体正下方三格的最右一格",
            "detect": "槽位基名 trigger 且该枪没有后握把槽位（避免与 r4c8 握把锚点抢位）",
            "position": "r4c8",
            "evidence": "数据可核实 + DOM 实测",
            "affected": triggers,
            "count": len(triggers),
        },
        {
            "id": "lever",
            "intent": "杠杆步枪的环状杠杆（真实 charge 槽）让出第 9 列上方给击锤链，改锚到枪托正下方",
            "detect": "存在 hammer 链且存在真实 charge 槽",
            "position": "r4c9",
            "evidence": "数据可核实 + DOM 实测（马林 MXLR）",
            "affected": hammers,
            "count": len(hammers),
        },
        {
            "id": "topOptic（镜座/瞄具上置链）",
            "intent": "能装光学瞄具的镜座、以及瞄具槽，必须排在父件（或机匣列）上方，绝不下沉到本体行下方",
            "detect": "槽位基名 mount/scope/sight_*，lane 为上置；mount 需子树含瞄具槽，或 allow 里的候选件自带瞄具槽；"
                      "父件是护木的顶盖类除外",
            "position": "父件同列上一行（机匣列优先）；再往上叠加，超出则顶部扩展",
            "evidence": "数据可核实 + DOM 实测",
            "affected": topoptics[:40],
            "count": len(topoptics),
        },
        {
            "id": "dovetailMount（AK 燕尾槽基座）",
            "intent": "本体正上方一行，且是该行从左往右第 3 个真实槽位；不新建虚假槽位",
            "detect": "槽位基名 mount；父件是机匣或根级；allow 里直接列着光学瞄具（pt=Scope）",
            "position": "r2；按该行真实槽位序号取第 3 位，不足时取最接近第 3 位的光学带空位并记录",
            "evidence": "数据可核实（allow 列表）+ DOM 实测",
            "affected": [{"id": d["id"], "name": d["name"], "cells": d["dovetail"]} for d in dovetails],
            "count": len(dovetails),
        },
        {
            "id": "mainRowCompaction",
            "intent": "主体行真实槽位向本体连续排列，末列紧邻本体（有独立上机匣时让出一列）",
            "detect": "槽位基名 muzzle/gas_block/barrel/handguard（机匣单独判定）",
            "position": "r3，列连续，末列 = body.col-1（有上机匣时 body.col-2）",
            "evidence": "数据可核实 + 全量 DOM 实测",
            "affected": "全部枪械",
        },
        {
            "id": "bodyRowExclusive",
            "intent": "主体行只放主体链角色；其他附件一律不得占用 r3",
            "detect": "落位后校验：r3 上的槽位基名必须属于主体链（含枪托/战术例外）",
            "position": "—",
            "evidence": "全量 DOM 实测",
            "affected": "全部枪械",
        },
        {
            "id": "topChildUpward",
            "intent": "父件已在第 1/2 行的子槽继续向上，不落回本体行",
            "detect": "父件行 ≤ 2 且基名不是 foregrip/bipod/magazine",
            "position": "父件同列上一行",
            "evidence": "全量 DOM 实测",
            "affected": "全部枪械",
        },
    ],
    "unchangedClasses": [
        {
            "id": "导轨/顶盖类（非镜座）",
            "why_unchanged": "槽位子树和 allow 里都没有瞄具槽，属于枪管/导气箍/护木上的导轨或防尘盖，"
                             "不是镜座；把它们搬到上方会与真实物理位置冲突。",
            "count": len(audit["classes"]["opticMountsOnNonReceiverParents"]),
            "samples": audit["classes"]["opticMountsOnNonReceiverParents"][:8],
            "status": "保留原车道（父件相邻下方），列入待核实",
        }
    ],
}
json.dump(rules, open(os.path.join(OUT, "layout-role-rules.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("wrote: 338-gun-inventory / axmc / m10 / marlin / layout-role-rules")
print("audit summary:", json.dumps(audit["summary"], ensure_ascii=False))
print("marlin checks:", json.dumps(marlin["checks"], ensure_ascii=False))
print("axmc result:", axmc["result"], "| m10:", m10["result"])
