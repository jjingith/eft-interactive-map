#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_ammo.py — 构建期生成 data/ammo.json（弹药资料库，运行期离线使用）

数据来源（全部为本地已缓存的 tarkov.dev 上游数据，构建期一次性读取，不覆盖任何既有文件）：

    build-cache/items-regular.json   ← json.tarkov.dev/<mode>/items 的原始缓存
                                       （含 properties：弹道系数 / 初速 / 伤害 / 穿透 / 材质…）
    build-cache/items_zh.json        ← 中文名（"<id> Name"）
    data/items.json                  ← 已发布包的物品摘要（取 trade 商人报价与 src 来源标记）

输出 data/ammo.json 的字段全部来自上游真实字段，**不做任何数值推导与补全**：
缺什么就留空，由前端显示「—」并注明不可用（例如跳蚤市场价 avg24hPrice 上游为 null）。

用法：
    python tools/build_ammo.py             # 生成 data/ammo.json
    python tools/build_ammo.py --check     # 只校验现有文件与缓存是否一致（不写盘）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM = os.path.join(BASE, "build-cache", "items-regular.json")
ZH = os.path.join(BASE, "build-cache", "items_zh.json")
ITEMS = os.path.join(BASE, "data", "items.json")
OUT = os.path.join(BASE, "data", "ammo.json")

SCHEMA = 1

# 口径 → 展示名（由上游口径 id 直接转写，不引入外部资料）
CALIBERS = {
    "Caliber12g": "12g",
    "Caliber20g": "20g",
    "Caliber23x75": "23x75",
    "Caliber26x75": "26x75",
    "Caliber40x46": "40x46",
    "Caliber40mmRU": "40mm RU",
    "Caliber20x1mm": "20x1mm",
    "Caliber9x18PM": "9x18",
    "Caliber9x19PARA": "9x19",
    "Caliber9x21": "9x21",
    "Caliber9x33R": ".357",
    "Caliber1143x23ACP": ".45 ACP",
    "Caliber127x33": ".50 AE",
    "Caliber762x25TT": "7.62x25",
    "Caliber46x30": "4.6x30",
    "Caliber57x28": "5.7x28",
    "Caliber545x39": "5.45x39",
    "Caliber556x45NATO": "5.56x45",
    "Caliber58x42": "5.8x42",
    "Caliber68x51": "6.8x51",
    "Caliber762x35": ".300 Blk",
    "Caliber762x39": "7.62x39",
    "Caliber762x51": "7.62x51",
    "Caliber762x54R": "7.62x54R",
    "Caliber784x49": ".308 ME",
    "Caliber86x70": ".338",
    "Caliber93x64": "9.3x64",
    "Caliber366TKM": ".366 TKM",
    "Caliber9x39": "9x39",
    "Caliber127x55": "12.7x55",
    "Caliber127x99": ".50 BMG",
}

# 口径 → 分组（分组名沿用参考站 db4tarkov.com/ammo 的五个分组；本地多出的口径
# 按其实际用途并入最接近的组，并在 audit.notes 里逐条登记，不静默丢弃）
GROUPS = [
    ("pistol", "PISTOL/SMG", "手枪 / 冲锋枪"),
    ("rifle", "RIFLE ROUNDS", "步枪弹"),
    ("pdw", "PDW", "PDW"),
    ("shot", "SHOTGUN ROUNDS", "霰弹"),
    ("gl", "GRENADE LAUNCHER", "榴弹发射器"),
]
GROUP_OF = {
    "Caliber762x25TT": "pistol", "Caliber9x18PM": "pistol", "Caliber9x19PARA": "pistol",
    "Caliber9x21": "pistol", "Caliber127x33": "pistol", "Caliber9x33R": "pistol",
    "Caliber1143x23ACP": "pistol", "Caliber20x1mm": "pistol",
    "Caliber9x39": "rifle", "Caliber93x64": "rifle", "Caliber58x42": "rifle",
    "Caliber545x39": "rifle", "Caliber556x45NATO": "rifle", "Caliber68x51": "rifle",
    "Caliber762x35": "rifle", "Caliber762x39": "rifle", "Caliber762x51": "rifle",
    "Caliber762x54R": "rifle", "Caliber86x70": "rifle", "Caliber784x49": "rifle",
    "Caliber366TKM": "rifle", "Caliber127x55": "rifle", "Caliber127x99": "rifle",
    "Caliber46x30": "pdw", "Caliber57x28": "pdw",
    "Caliber12g": "shot", "Caliber20g": "shot", "Caliber23x75": "shot",
    "Caliber40x46": "gl", "Caliber40mmRU": "gl", "Caliber26x75": "gl",
}
# 口径筛选筹码：k=筹码 id，cal=口径，atyp=只保留该 ammoType（None=全部）
CHIPS = [
    ("pistol", [("7.62x25", "Caliber762x25TT", None), ("9x18", "Caliber9x18PM", None),
                ("9x19", "Caliber9x19PARA", None), ("9x21", "Caliber9x21", None),
                (".50 AE", "Caliber127x33", None), (".357", "Caliber9x33R", None),
                (".45 ACP", "Caliber1143x23ACP", None), ("20x1mm", "Caliber20x1mm", None)]),
    ("rifle", [("9x39", "Caliber9x39", None), ("9.3x64", "Caliber93x64", None),
               ("5.8x42", "Caliber58x42", None), ("5.45x39", "Caliber545x39", None),
               ("5.56x45", "Caliber556x45NATO", None), ("6.8x51", "Caliber68x51", None),
               (".300 Blk", "Caliber762x35", None), ("7.62x39", "Caliber762x39", None),
               ("7.62x51", "Caliber762x51", None), ("7.62x54R", "Caliber762x54R", None),
               (".338", "Caliber86x70", None), (".308 ME", "Caliber784x49", None),
               (".366 TKM", "Caliber366TKM", None), ("12.7x55", "Caliber127x55", None),
               (".50 BMG", "Caliber127x99", None)]),
    ("pdw", [("4.6x30", "Caliber46x30", None), ("5.7x28", "Caliber57x28", None)]),
    ("shot", [("12g Shot", "Caliber12g", "buckshot"), ("12g Slugs", "Caliber12g", "slug"),
              ("20g", "Caliber20g", None), ("23x75", "Caliber23x75", None)]),
    ("gl", [("40x46", "Caliber40x46", None), ("40mm RU", "Caliber40mmRU", None),
            ("26x75", "Caliber26x75", None)]),
]


def _read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cheapest_buy(trades, traders):
    """买价：取 priceRUB 最低的商人报价（并列取等级更低者）。没有返回 None。"""
    best = None
    for t in trades or []:
        if (t or {}).get("k") != "buy":
            continue
        rub = t.get("p")
        lvl = t.get("l")
        tid = t.get("t")
        if rub is None:
            continue
        key = (rub, lvl if isinstance(lvl, (int, float)) else 99)
        if best is None or key < best[0]:
            best = (key, {"t": tid, "l": lvl, "cur": t.get("c"), "rub": rub})
    return best[1] if best else None


def _best_sell(sells, traders):
    """卖价：取 priceRUB 最高的商人报价。没有返回 None。"""
    best = None
    for s in sells or []:
        rub = (s or {}).get("priceRUB")
        if rub is None:
            continue
        if best is None or rub > best["rub"]:
            best = {"t": s.get("trader"), "rub": rub}
    return best


def build(upstream, zh, items_payload):
    items = (upstream.get("data") or {}).get("items") or {}
    zhmap = (zh or {}).get("data") or {}
    summary = (items_payload or {}).get("items") or {}
    traders = (items_payload or {}).get("traders") or {}

    recs = []
    audit_notes = []
    for iid, rec in items.items():
        props = rec.get("properties") or {}
        atyp = props.get("ammoType")
        if not atyp:
            continue                      # 无弹道属性的记录（弹匣包 / 发射器等）不算弹药
        cal = props.get("caliber")
        if cal not in CALIBERS:
            audit_notes.append("未知口径 %s（%s），已按 none 跳过" % (cal, iid))
            continue
        rec_sum = summary.get(iid) or {}
        buy = _cheapest_buy(rec_sum.get("trade"), traders)
        sell = _best_sell(rec.get("sellToTrader"), traders)
        recs.append({
            "id": iid,
            "n": zhmap.get(iid + " Name") or rec.get("name") or iid,
            "cal": cal,
            "caln": CALIBERS[cal],
            "t": atyp,
            "g": GROUP_OF.get(cal, "rifle"),
            "dmg": props.get("damage"),
            "ard": props.get("armorDamage"),
            "pen": props.get("penetrationPower"),
            "v0": props.get("initialSpeed"),
            "bc": props.get("ballisticCoeficient"),
            "m": props.get("bulletMassGrams"),
            "dia": props.get("bulletDiameterMilimeters"),
            "frag": props.get("fragmentationChance"),
            "ric": props.get("ricochetChance"),
            "acc": props.get("accuracyModifier"),
            "rec": props.get("recoilModifier"),
            "pc": props.get("projectileCount"),
            "stack": props.get("stackMaxSize"),
            "pch": props.get("penetrationChance"),
            "tr": bool(props.get("tracer")),
            "w": rec.get("weight"),
            "base": rec.get("basePrice"),
            "buy": buy,
            "sell": sell,
            "src": rec_sum.get("src") or [],
            "flea": rec.get("avg24hPrice"),
        })
    recs.sort(key=lambda r: (r["g"], r["caln"], -(r["pen"] or 0), r["n"]))

    # 审计：字段覆盖 / 缺口
    def cov(key):
        return sum(1 for r in recs if r.get(key) not in (None, "", []))

    cal_used = sorted(set(r["cal"] for r in recs))
    audit = {
        "source": {
            "battle": "build-cache/items-regular.json（tarkov.dev 上游缓存，构建期读取）",
            "names": "build-cache/items_zh.json",
            "prices": "data/items.json 的 trade / src（构建期已提取的商人报价）",
        },
        "count": len(recs),
        "calibers": len(cal_used),
        "calibersMissingLabel": [c for c in cal_used if c not in CALIBERS],
        "byType": {t: sum(1 for r in recs if r["t"] == t) for t in sorted(set(r["t"] for r in recs))},
        "coverage": {k: cov(k) for k in ("dmg", "ard", "pen", "v0", "bc", "m", "dia", "frag",
                                         "ric", "acc", "rec", "pc", "stack", "base", "buy", "sell", "flea")},
        "unavailable": {
            "flea": "avg24hPrice 上游为 null（无跳蚤市场价），界面显示「—」，不得按 0 处理",
        },
        "notes": audit_notes,
        "groupDelta": "本地口径与参考站的对应关系：.308 ME→参考站的 .308；40mm RU / 26x75 / 20x1mm 为参考站未列出的本地口径，分别并入榴弹发射器 / 手枪组",
    }
    return {
        "schema": SCHEMA,
        "count": len(recs),
        "groups": [{"k": k, "n": n, "zh": z} for k, n, z in GROUPS],
        "chips": [{"g": g, "items": [{"k": k, "cal": c, "atyp": a} for k, c, a in lst]}
                  for g, lst in CHIPS],
        "calibers": [{"k": c, "n": CALIBERS[c], "g": GROUP_OF.get(c, "rifle")} for c in cal_used],
        "traders": traders,
        "ammo": recs,
        "audit": audit,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    args = ap.parse_args()

    for p in (UPSTREAM, ZH, ITEMS):
        if not os.path.exists(p):
            print("缺少构建期缓存：%s" % p, file=sys.stderr)
            return 2
    payload = build(_read(UPSTREAM), _read(ZH), _read(ITEMS))
    text = json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":"))

    if args.check:
        if not os.path.exists(OUT):
            print("data/ammo.json 不存在", file=sys.stderr)
            return 1
        cur = _read(OUT)
        same = (cur.get("count") == payload["count"]
                and [a["id"] for a in cur.get("ammo", [])] == [a["id"] for a in payload["ammo"]])
        print("count=%d 一致=%s" % (payload["count"], same))
        return 0 if same else 1

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("写入 %s：%d 件弹药 / %d 种口径 / %.1f KB"
          % (os.path.relpath(OUT, BASE), payload["count"], payload["audit"]["calibers"],
             len(text.encode("utf-8")) / 1024.0))
    print("字段覆盖：" + ", ".join("%s=%d" % (k, v) for k, v in payload["audit"]["coverage"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
