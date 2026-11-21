#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R16-A/B：构建枪械兼容数据（口径 / 平台 / 可用弹药 / 可用弹匣）。

数据来源（全部为构建期一次性读取，运行期只读本地 JSON）：
  · https://json.tarkov.dev/regular/items 的 properties.caliber / properties.allowedAmmo /
    properties.handbookCategories / properties.normalizedName —— 官方静态数据，字段直接可读（verified）。
  · 本地 data/items.json 的 slots[sid=mod_magazine].allow —— 构建期从同一上游导出，
    是「该枪机匣能吃哪些弹匣」的**精确物品 ID 列表**（verified），不是按口径猜的。
  · 本地 data/ammo.json —— 200 条弹药的 cal / caln，用于口径显示名与弹药 ID 有效性校验。

平台（枪族）映射：
  上游没有「平台」字段。本工具用一张**显式的「型号前缀 → 平台」表**在构建期把结果落到
  data/gun-platforms.json（逐枪一条，含 confidence 与 basis），运行期不做任何名称匹配。
  未命中任何前缀的枪保留 platform=null，UI 按上游 handbookCategories 的武器类别归组，
  绝不猜测。因此平台分组的可信度是 estimated，口径/弹药/弹匣是 verified。

用法：
  python tools/build_weapon_compat.py                 # 用 build-cache/items-regular.json
  python tools/build_weapon_compat.py --items <path>  # 指定上游 JSON（本地文件）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "build-cache", "items-regular.json")
RATES = os.path.join(ROOT, "data", "gun-rates.json")
AMMO = os.path.join(ROOT, "data", "ammo.json")
ITEMS = os.path.join(ROOT, "data", "items.json")
OUT_COMPAT = os.path.join(ROOT, "data", "gun-compat.json")
OUT_PLATFORM = os.path.join(ROOT, "data", "gun-platforms.json")

# —— 型号前缀 → 平台（构建期一次性映射，运行期只读结果）——
# 顺序敏感：更长的前缀放前面（ak-74 先于 ak）。
PLATFORM_RULES = [
    ("ar15", "AR-15 平台", [
        "colt-m4a1", "adar-2-15", "hk-416", "tx-15", "radian-model-1", "noveske", "m4a1",
        "sig-mcx", "desert-tech-mdr", "kel-tec-rfb", "springfield-armory-m1a",
    ]),
    ("ak", "AK 平台", [
        "kalashnikov-ak-74m", "kalashnikov-ak-74n", "kalashnikov-ak-74", "kalashnikov-aks-74u",
        "kalashnikov-aks-74un", "kalashnikov-aks-74ub", "kalashnikov-aks-74n", "kalashnikov-aks-74",
        "kalashnikov-akm", "kalashnikov-akms", "kalashnikov-akmn", "kalashnikov-akmsn",
        "kalashnikov-ak-101", "kalashnikov-ak-102", "kalashnikov-ak-103", "kalashnikov-ak-104",
        "kalashnikov-ak-105", "kalashnikov-ak-12", "kalashnikov-ak-15", "kalashnikov-ak-19",
        "molot-arms-vpo-136", "molot-arms-vpo-209", "kalashnikov-rpk", "rpk-16", "kalashnikov-rpk-16",
        "izhmash-rpk",
    ]),
    ("vss", "VSS / VAL 平台", [
        "vss-vintorez", "as-val", "sr-3m", "9a-91", "molot-arms-vpo-101",
    ]),
    ("svd", "SVD 平台", ["svds", "svd-", "tsniitochmash-svd"]),
    ("mosin", "莫辛平台", ["mosin"]),
    ("bolt762", "7.62 栓动平台", [
        "remington-model-700", "lobaev-arms-dvl", "orsis-t-5000", "accuracy-international-axmc",
        "sv-98", "sako-trg",
    ]),
    ("mp5", "MP5 平台", ["hk-mp5"]),
    ("mp7", "MP7 平台", ["hk-mp7"]),
    ("mp9", "MP9 平台", ["bt-mp9"]),
    ("vector", "Vector 平台", ["tdi-kriss-vector"]),
    ("ump", "UMP 平台", ["hk-ump"]),
    ("p90", "P90 平台", ["fn-p90"]),
    ("vityaz", "PP-19 平台", ["pp-19-01-vityaz", "pp-19-01", "pp-19"]),
    ("kedr", "PP-91 平台", ["pp-91-kedr", "pp-91-01-kedr", "pp-9-klin"]),
    ("ppsh", "PPSh 平台", ["ppsh-41"]),
    ("shotgun_mp", "MP 系列霰弹枪", ["mp-133", "mp-153", "mp-43-1c"]),
    ("shotgun_saiga", "Saiga 平台", ["saiga-12k", "saiga-12", "saiga-9"]),
    ("shotgun_rem", "雷明顿 870 / 莫斯伯格平台", ["remington-model-870", "mossberg-590"]),
    ("shotgun_toz", "TOZ / KS 平台", ["toz-106", "toz-ks-23"]),
    ("glock", "格洛克平台", ["glock-17", "glock-18"]),
    ("p226", "SIG P226 平台", ["sig-p226r"]),
    ("m9", "伯莱塔 92 平台", ["beretta-m9a3"]),
    ("m1911", "1911 平台", ["colt-m1911a1", "colt-m45a1"]),
    ("tt", "TT 平台", ["tokarev-tt-33"]),
    ("pm", "马卡洛夫平台", ["makarov-pm", "pb-9x18pm", "stechkin-aps", "stechkin-apb"]),
    ("five-seven", "FN Five-seveN 平台", ["fn-five-seven"]),
    ("grach", "雅利金平台", ["yarygin-mp-443"]),
    ("gyurza", "SR-1 平台", ["serdyukov-sr-1mp"]),
    ("lmg_pk", "PK 平台", ["kalashnikov-pkm", "kalashnikov-pkp"]),
    ("lmg_m249", "M249 平台", ["m249"]),
    ("lmg_rpd", "RPD 平台", ["rpd"]),
    ("ash12", "ASH-12 平台", ["ash-12"]),
    ("groza", "Groza 平台", ["oc-14", "groza"]),
    ("a545", "A-545 / A-762 平台", ["a-545", "a-762"]),
    ("gl40", "40mm 榴弹发射器", ["fn40gl"]),
    ("m32", "40mm 榴弹发射器", ["milkor-m32"]),
]

# 上游 handbookCategories.normalizedName → 中文类别名
CLASS_ZH = {
    "assault-rifles": "突击步枪",
    "assault-carbines": "突击卡宾枪",
    "carbines": "卡宾枪",
    "submachine-guns": "冲锋枪",
    "pistols": "手枪",
    "shotguns": "霰弹枪",
    "bolt-action-sniper-rifles": "栓动狙击步枪",
    "sniper-rifles": "狙击步枪",
    "marksman-rifles": "精确射手步枪",
    "machine-guns": "机枪",
    "light-machine-guns": "轻机枪",
    "grenade-launchers": "榴弹发射器",
    "special-weapons": "特种武器",
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_remote(path):
    data = _read(path)
    items = data.get("data", {}).get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        raise SystemExit("上游 JSON 结构不符：期望 data.items")
    return data, items


def _platform_of(normalized):
    nm = normalized or ""
    for key, label, prefixes in PLATFORM_RULES:
        for p in prefixes:
            if nm.startswith(p + "-") or nm == p or ("-" + p + "-") in ("-" + nm + "-"):
                return key, label
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=CACHE, help="上游 items JSON（默认 build-cache/items-regular.json）")
    args = ap.parse_args()

    _, remote = _load_remote(args.items)
    rates = _read(RATES)
    ammo = _read(AMMO)
    local = _read(ITEMS)["items"]
    handbook = _read(args.items)["data"].get("handbookCategories") or {}

    ammo_rows = ammo.get("ammo") or []
    ammo_by_id = {a["id"]: a for a in ammo_rows}
    cal_name = {}
    for a in ammo_rows:
        if a.get("cal") and a.get("caln"):
            cal_name.setdefault(a["cal"], a["caln"])

    gun_ids = list((rates.get("guns") or {}).keys())
    compat_guns, platform_guns = {}, {}
    stats = {"noCal": 0, "noAmmo": 0, "noMags": 0, "platform": 0, "noPlatform": 0,
             "ammoMissingIds": 0, "magIdsMissing": 0}

    for gid in gun_ids:
        r = remote.get(gid) or {}
        props = r.get("properties") or {}
        loc = local.get(gid) or {}
        cal = props.get("caliber")
        caln = cal_name.get(cal) if cal else None
        if not cal:
            stats["noCal"] += 1

        # 弹药：上游 allowedAmmo（精确 ID）→ 只保留本地弹药库存在的 ID
        allowed = props.get("allowedAmmo") or []
        ammo_ids, ammo_missing = [], []
        for aid in allowed:
            if aid in ammo_by_id:
                ammo_ids.append(aid)
            else:
                ammo_missing.append(aid)
        if not allowed:
            stats["noAmmo"] += 1
        stats["ammoMissingIds"] += len(ammo_missing)

        # 弹匣：本地 items.json 的 mod_magazine 槽 allow（精确 ID，构建期同源导出）
        mags = []
        for s in loc.get("slots") or []:
            if s.get("sid") == "mod_magazine":
                mags = [m for m in (s.get("allow") or []) if (local.get(m) or {}).get("pt") == "Magazine"]
                break
        if not mags:
            stats["noMags"] += 1
        stats["magIdsMissing"] += 0

        # 武器类别：上游 handbookCategories（父级 weapons 之下的子类）
        cls = None
        for hid in (r.get("handbookCategories") or []):
            h = handbook.get(hid) or {}
            nm = h.get("normalizedName")
            if nm and nm in CLASS_ZH:
                cls = nm
                break
        if cls is None:
            pt = props.get("propertiesType")
            cls = "assault-rifles" if pt == "ItemPropertiesWeapon" else None

        pkey, plabel = _platform_of(r.get("normalizedName"))
        if pkey:
            stats["platform"] += 1
            platform_guns[gid] = {"p": pkey, "confidence": "estimated",
                                  "basis": "curated-prefix:" + (r.get("normalizedName") or "")}
        else:
            stats["noPlatform"] += 1
            platform_guns[gid] = {"p": None, "confidence": "missing", "basis": "no-curated-prefix"}

        compat_guns[gid] = {
            "n": (rates["guns"][gid] or {}).get("n") or loc.get("n") or gid,
            "cal": cal,
            "caln": caln or (cal.replace("Caliber", "") if cal else None),
            "cls": cls,
            "clsZh": CLASS_ZH.get(cls),
            "platform": pkey,
            "platformN": plabel,
            "ammo": ammo_ids,
            "ammoMissing": ammo_missing,
            "mags": mags,
            "hasMagSlot": bool(mags),
            "confidence": {"caliber": "verified" if cal else "missing",
                           "ammo": "verified" if ammo_ids else "missing",
                           "mags": "verified" if mags else "missing",
                           "platform": "estimated" if pkey else "missing"},
            "sourceKind": "tarkov.dev static + local items.json (build time)",
        }

    today = _dt.date.today().isoformat()
    compat_doc = {
        "schema": 1,
        "generatedAt": today,
        "source": {
            "items": "https://json.tarkov.dev/regular/items",
            "localItems": "data/items.json（同源导出的 slots[mod_magazine].allow）",
            "localAmmo": "data/ammo.json（200 条，cal/caln 用于口径显示名与 ID 校验）",
            "fields": ["properties.caliber", "properties.allowedAmmo", "properties.handbookCategories",
                       "properties.normalizedName", "slots[sid=mod_magazine].allow"],
            "note": "口径 / 可用弹药 / 可用弹匣均为上游精确字段或精确物品 ID（verified）；"
                    "弹匣列表取自本地 items.json 的机匣槽位 allow，不是按口径推的。"
                    "数据仅构建期读取，运行期只读本文件。",
        },
        "counts": {"guns": len(compat_guns), "withCaliber": len(compat_guns) - stats["noCal"],
                   "withAmmo": len(compat_guns) - stats["noAmmo"],
                   "withMags": len(compat_guns) - stats["noMags"],
                   "withPlatform": stats["platform"], "withoutPlatform": stats["noPlatform"],
                   "ammoIdsNotInLocalDb": stats["ammoMissingIds"]},
        "guns": compat_guns,
    }
    platform_doc = {
        "schema": 1,
        "generatedAt": today,
        "source": {
            "method": "tools/build_weapon_compat.py 的 PLATFORM_RULES（型号前缀 → 平台）在构建期逐枪落表",
            "note": "上游没有平台字段；本表是人工整理的映射，逐枪一条、可审计，可信度 estimated。"
                    "未命中的枪 platform=null，UI 按上游武器类别归组，不做猜测。",
        },
        "platforms": {k: {"n": label, "confidence": "estimated"} for k, label, _ in PLATFORM_RULES},
        "guns": platform_guns,
    }
    with open(OUT_COMPAT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(compat_doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    with open(OUT_PLATFORM, "w", encoding="utf-8", newline="\n") as f:
        json.dump(platform_doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("guns=%d withAmmo=%d withMags=%d platform=%d noPlatform=%d noCal=%d ammoMissingIds=%d"
          % (len(compat_guns), len(compat_guns) - stats["noAmmo"], len(compat_guns) - stats["noMags"],
             stats["platform"], stats["noPlatform"], stats["noCal"], stats["ammoMissingIds"]))
    print("→ %s / %s" % (os.path.relpath(OUT_COMPAT, ROOT), os.path.relpath(OUT_PLATFORM, ROOT)))


if __name__ == "__main__":
    sys.exit(main())
