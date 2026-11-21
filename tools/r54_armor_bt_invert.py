# -*- coding: utf-8 -*-
"""R54：tarkovgunsmith 钝伤系数（BT%）覆盖度检查 + 方程反解 + 159 条回归。

用法（项目根目录）：
    python tools/r54_armor_bt_invert.py              # 首次抓取并写库
    python tools/r54_armor_bt_invert.py --refresh    # 忽略缓存重新抓取/重算
    python tools/r54_armor_bt_invert.py --no-write   # 只算不写 data/armor-bt.json

数据源（均为 gunsmith 后端实际接口，前端 main.js 中可见调用）：
    GET  https://api.tarkovgunsmith.com/GetHelmetsDataSheetData
    GET  https://api.tarkovgunsmith.com/GetArmorModulesData
    GET  https://api.tarkovgunsmith.com/GetGetNewArmorStatSheetData
    POST https://api.tarkovgunsmith.com/GetSingleShotBallisticSimulation

反解公式（Ballistics.cs / combat_sim.js 同口径）：
    FactorA      = (121 - 5000/(45 + 2*durPct)) * cls * 0.1
    bluntScale   = clamp(1 - 0.03*(FactorA - pen), 0.2, 1)
    BluntDamage  = D * BT * bluntScale            （单层、格挡分支）
    => BT        = BluntDamage / (D * bluntScale)

只依赖 Python 标准库；外网经 127.0.0.1:7896 代理，本地地址不走代理。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data", "armor-bt.json")
EVIDENCE_JSON = os.path.join(ROOT, "docs", "r54-armor-bt-inversion-evidence.json")

API = "https://api.tarkovgunsmith.com"
PROXY = os.environ.get("R54_PROXY", "http://127.0.0.1:7896")

# 固定弹药：5.45x39mm PS（project data/ammo.json）
AMMO = {
    "id": "56dff3afd2720bba668b4567",
    "n": "5.45x39mm PS",
    "pen": 28,
    "dmg": 56,
    "ard": 40,   # armorDamage%
}

# 耐久档位：满耐久 / 50% / 接近 0（1%，避免 0 产生 0 耐久除零边界）
TIERS = (("full", 1.0), ("half", 0.5), ("near-zero", 0.01))

MAT_NAME = {0: "Aluminium", 1: "Aramid", 2: "Steel", 3: "Ceramic",
            4: "Combined", 5: "Glass", 6: "Titan", 7: "UHMWPE"}
MAT_ID = {v.lower(): k for k, v in MAT_NAME.items()}
MAT_ID.update({"aramid": 1, "armysteel": 2, "combined": 4, "uhmwpe": 7,
               "ceramic": 3, "glass": 5, "titan": 6, "aluminium": 0,
               "armorsteel": 2})


def log(msg):
    print(msg, flush=True)


def http_get(url, retries=3):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=60) as r:
                if r.status != 200:
                    raise RuntimeError("HTTP %s" % r.status)
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (i + 1))
    raise RuntimeError("GET %s 失败: %s" % (url, last))


def http_post(path, payload, retries=3):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    body = json.dumps(payload).encode("utf-8")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                API + path, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=60) as r:
                if r.status != 200:
                    raise RuntimeError("HTTP %s" % r.status)
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (i + 1))
    raise RuntimeError("POST %s 失败: %s" % (path, last))


def collect_rows(obj, out):
    """递归收集所有含 id + bluntThroughput 的行（含 subRows/subModules）。"""
    if isinstance(obj, dict):
        if obj.get("id") and "bluntThroughput" in obj:
            out.append(obj)
        for v in obj.values():
            collect_rows(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_rows(v, out)


def factor_a(cls, dur_pct):
    return (121 - 5000 / (45 + dur_pct * 2)) * cls * 0.1


def blunt_scale(pen, cls, dur_pct):
    return max(0.2, min(1.0, 1 - 0.03 * (factor_a(cls, dur_pct) - pen)))


def invert_bt(blunt, dmg, pen, cls, dur_pct):
    scale = blunt_scale(pen, cls, dur_pct)
    return blunt / (dmg * scale), scale


def sim_layer(cls, mat, bt_pub, dur, max_dur):
    """bt_pub 为数据库中的小数口径（0.26）；接口字段是百分数（26）。"""
    payload = {
        "penetration": AMMO["pen"],
        "damage": AMMO["dmg"],
        "armorDamagePerc": AMMO["ard"],
        "hitPoints": 85,
        "armorLayers": [{
            "isPlate": False,
            "armorClass": cls,
            "bluntDamageThroughput": bt_pub * 100.0,
            "durability": dur,
            "maxDurability": max_dur,
            "armorMaterial": mat,
        }],
    }
    res = http_post("/GetSingleShotBallisticSimulation", payload)
    if not isinstance(res, list) or not res:
        raise RuntimeError("模拟返回为空")
    return res[0]


def tier_durs(max_dur, ratio):
    dur = max(1, round(max_dur * ratio)) if ratio < 1 else max_dur
    return dur, dur / float(max_dur) * 100.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    ap.add_argument("--no-write", action="store_true", help="不写 data/armor-bt.json")
    args = ap.parse_args(argv)

    with open(DATA_JSON, encoding="utf-8") as f:
        db = json.load(f)
    items = db["items"]
    # 目标集合保持稳定：材质兜底条目 + 已反解条目（保证脚本可重复运行）
    fallback_ids = [k for k, v in items.items()
                    if v.get("btSource") in ("material-fallback", "gunsmith-inverted")]

    evidence = {}
    if os.path.exists(EVIDENCE_JSON) and not args.refresh:
        try:
            evidence = json.load(open(EVIDENCE_JSON, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            evidence = {}

    log("[1/4] 抓取 gunsmith 护甲数据源 ...")
    raw = evidence.setdefault("source_rows", {})
    if args.refresh or not raw:
        for key, path in (("helmets", "/GetHelmetsDataSheetData"),
                          ("modules", "/GetArmorModulesData"),
                          ("newArmor", "/GetGetNewArmorStatSheetData")):
            data = http_get(API + path)
            rows = []
            collect_rows(data, rows)
            seen = set()
            for r in rows:
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                rows_out = {
                    "id": r["id"],
                    "name": r.get("name"),
                    "bluntThroughput": r.get("bluntThroughput"),
                    "armorClass": r.get("armorClass"),
                    "armorMaterial": r.get("armorMaterial"),
                    "durability": r.get("durability") or r.get("maxDurability"),
                    "category": r.get("category") or r.get("armorType"),
                }
                raw.setdefault(key, []).append(rows_out)
            raw[key] = [x for x in raw.get(key, []) if isinstance(x, dict)]
            log("  %s: %d 行（%s）" % (key, len(seen), path))
    else:
        for k, v in raw.items():
            log("  缓存 %s: %d 行" % (k, len(v)))

    covered = {}
    for key, rows in raw.items():
        for r in rows:
            if r["id"] in fallback_ids:
                covered.setdefault(r["id"], []).append(dict(r, source=key))

    coverage = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "proxy": PROXY,
        "apis": ["GetHelmetsDataSheetData", "GetArmorModulesData",
                 "GetGetNewArmorStatSheetData"],
        "fallback_ids": fallback_ids,
        "covered_ids": sorted(covered),
        "missing_ids": sorted(set(fallback_ids) - set(covered)),
        "hits": {k: covered.get(k, []) for k in fallback_ids},
    }
    evidence["coverage"] = coverage
    log("  覆盖 %d / %d；缺失 %d" % (len(covered), len(fallback_ids), len(coverage["missing_ids"])))
    for i in fallback_ids:
        hit = covered.get(i)
        log("   %s %-32s %s" % (i, items[i]["n"][:32],
                                ("命中 %s BT=%.4f" % (hit[0]["source"], hit[0]["bluntThroughput"]))
                                if hit else "缺失"))

    log("[2/4] 对可覆盖护甲做三档耐久方程反解 ...")
    inv_cache = evidence.setdefault("sim_cache", {})
    inverted = {}
    sim_jobs = {}
    for iid in coverage["covered_ids"]:
        row = covered[iid][0]
        cls = int(row["armorClass"])
        mat = int(row["armorMaterial"])
        max_dur = int(row["durability"])
        bt_pub = float(row["bluntThroughput"])
        samples = []
        for tier, ratio in TIERS:
            dur, dur_pct = tier_durs(max_dur, ratio)
            key = "%s|%d|%d|%s|%r" % (iid, cls, max_dur, tier, bt_pub)
            sim_jobs[key] = (iid, tier, cls, mat, bt_pub, dur, max_dur, dur_pct)
    log("  模拟请求 %d 个 ..." % len(sim_jobs))

    def run_one(kv):
        key, job = kv
        if key in inv_cache and not args.refresh:
            return key, inv_cache[key]
        iid, tier, cls, mat, bt_pub, dur, max_dur, dur_pct = job
        r = sim_layer(cls, mat, bt_pub, dur, max_dur)
        return key, r

    with ThreadPoolExecutor(max_workers=6) as ex:
        for key, res in ex.map(run_one, list(sim_jobs.items())):
            inv_cache[key] = res

    for iid in coverage["covered_ids"]:
        row = covered[iid][0]
        cls = int(row["armorClass"])
        mat = int(row["armorMaterial"])
        max_dur = int(row["durability"])
        bt_pub = float(row["bluntThroughput"])
        samples = []
        for tier, ratio in TIERS:
            dur, dur_pct = tier_durs(max_dur, ratio)
            key = "%s|%d|%d|%s|%r" % (iid, cls, max_dur, tier, bt_pub)
            r = inv_cache[key]
            blunt = float(r["BluntDamage"])
            bt_inv, scale = invert_bt(blunt, AMMO["dmg"], AMMO["pen"], cls, dur_pct)
            samples.append({
                "tier": tier,
                "durability": dur,
                "maxDurability": max_dur,
                "durPct": round(dur_pct, 4),
                "bluntDamage": blunt,
                "penetrationChance": r.get("PenetrationChance"),
                "bluntScale": round(scale, 8),
                "btInverted": bt_inv,
                "btPublished": bt_pub,
                "delta": bt_inv - bt_pub,
            })
        invs = [s["btInverted"] for s in samples]
        spread = max(invs) - min(invs)
        bt_val = round(sum(invs) / len(invs), 4)
        inverted[iid] = {
            "name": row.get("name"),
            "sourceSheet": row.get("source"),
            "armorClass": cls,
            "armorMaterial": mat,
            "armorMaterialName": MAT_NAME.get(mat),
            "maxDurability": max_dur,
            "btPublished": bt_pub,
            "bt": bt_val,
            "samples": samples,
            "selfConsistent": spread <= 5e-5,
            "spread": spread,
            "deltaPublished": bt_val - bt_pub,
        }
        log("  %-34s BT=%.4f  三档=%s  跨档差=%.2e" %
            (items[iid]["n"][:34], bt_val,
             "/".join("%.4f" % x for x in invs), spread))
    evidence["inverted"] = inverted

    log("[3/4] 159 条已知 BT 回归 ...")
    reg_cache = evidence.setdefault("regression_cache", {})
    reg_items = [(k, v) for k, v in items.items() if v.get("btSource") == "gunsmith"]
    jobs = []
    for iid, v in reg_items:
        cls = int(v["cls"])
        mat = v["mat"]
        if isinstance(mat, str):
            mat_id = MAT_ID.get(mat.lower())
            if mat_id is None:
                raise RuntimeError("未知材质 %r (%s)" % (mat, iid))
        else:
            mat_id = int(mat)
        max_dur = int(v["dur"])
        bt_pub = float(v["bt"])
        for tier, ratio in TIERS:
            dur, dur_pct = tier_durs(max_dur, ratio)
            key = "%s|%d|%d|%s|%r" % (iid, cls, max_dur, tier, bt_pub)
            jobs.append((key, (iid, tier, cls, mat_id, bt_pub, dur, max_dur, dur_pct)))
    log("  模拟请求 %d 个 ..." % len(jobs))

    def run_reg(kv):
        key, job = kv
        if key in reg_cache and not args.refresh:
            return key, reg_cache[key]
        iid, tier, cls, mat, bt_pub, dur, max_dur, dur_pct = job
        r = sim_layer(cls, mat, bt_pub, dur, max_dur)
        return key, r

    with ThreadPoolExecutor(max_workers=6) as ex:
        for key, res in ex.map(run_reg, jobs):
            reg_cache[key] = res

    errors = []
    zero_blunt = []
    per_item = {}
    for iid, v in reg_items:
        cls = int(v["cls"])
        mat = v["mat"]
        mat_id = MAT_ID.get(mat.lower()) if isinstance(mat, str) else int(mat)
        max_dur = int(v["dur"])
        bt_pub = float(v["bt"])
        item_errors = []
        for tier, ratio in TIERS:
            dur, dur_pct = tier_durs(max_dur, ratio)
            key = "%s|%d|%d|%s|%r" % (iid, cls, max_dur, tier, bt_pub)
            r = reg_cache[key]
            blunt = float(r["BluntDamage"])
            if blunt == 0:
                zero_blunt.append((iid, tier))
            bt_inv, _ = invert_bt(blunt, AMMO["dmg"], AMMO["pen"], cls, dur_pct)
            d = abs(bt_inv - bt_pub)
            item_errors.append(d)
            errors.append(d)
        per_item[iid] = {"bt": bt_pub, "maxError": max(item_errors),
                         "errors": item_errors}
    evidence["regression"] = {
        "count": len(reg_items),
        "samples": len(errors),
        "ammo": AMMO,
        "maxError": max(errors) if errors else None,
        "meanError": (sum(errors) / len(errors)) if errors else None,
        "roundedToOneDamageStep": 1.0 / (AMMO["dmg"] * 0.2),
        "zeroBlunt": zero_blunt,
        "perItem": per_item,
    }
    log("  条目 %d / 样本 %d；最大误差 %.3e；零钝伤 %d" %
        (len(reg_items), len(errors), max(errors) if errors else 0, len(zero_blunt)))

    log("[4/4] 写库 ...")
    source = db.setdefault("source", {})
    source["fetched_at"] = time.strftime("%Y-%m-%d")
    source["inversion"] = {
        "round": "R54",
        "endpoint": "https://api.tarkovgunsmith.com/GetSingleShotBallisticSimulation",
        "ammoId": AMMO["id"],
        "ammo": AMMO["n"],
        "durabilityTiers": [t[0] for t in TIERS],
        "formula": "BT = BluntDamage / (damage * bluntScale); bluntScale=clamp(1-0.03*(FactorA-pen),0.2,1); FactorA=(121-5000/(45+2*durPct))*cls*0.1",
        "note": "btSource=gunsmith-inverted 表示由站点模拟输出方程反解并三档自洽；material-fallback 保留为兜底",
    }
    for iid, info in inverted.items():
        ent = items[iid]
        ent["bt"] = info["bt"]
        ent["btSource"] = "gunsmith-inverted"
        ent["btEvidence"] = {
            "endpoint": "GetSingleShotBallisticSimulation",
            "ammoId": AMMO["id"],
            "ammo": AMMO["n"],
            "armorClass": info["armorClass"],
            "armorMaterial": info["armorMaterialName"],
            "maxDurability": info["maxDurability"],
            "published": info["btPublished"],
            "inverted": info["bt"],
            "selfConsistent": info["selfConsistent"],
            "spread": info["spread"],
            "samples": info["samples"],
        }

    if not args.no_write:
        with open(DATA_JSON, "w", encoding="utf-8", newline="\n") as f:
            json.dump(db, f, ensure_ascii=False, indent=1)
            f.write("\n")
        with open(EVIDENCE_JSON, "w", encoding="utf-8", newline="\n") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=1)
            f.write("\n")
        log("  已写入 %s" % os.path.relpath(DATA_JSON, ROOT))
        log("  已写入 %s" % os.path.relpath(EVIDENCE_JSON, ROOT))

    summary = {
        "covered": len(inverted),
        "missing": len(coverage["missing_ids"]),
        "bt": {iid: info["bt"] for iid, info in inverted.items()},
        "regressionMaxError": evidence["regression"]["maxError"],
        "regressionSamples": evidence["regression"]["samples"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
