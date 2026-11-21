#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R58b：从《逃离塔科夫》客户端 resources.assets 抽取护甲真值（只读）。

用法：
    python tools/r58b_game_truth.py extract   # 生成 data/game-truth/*.json
    python tools/r58b_game_truth.py compare   # 与 data/armor-bt.json / armor-ricochet.json 对照

只读：只 open(... 'rb') + mmap，不写游戏目录、不联网、不依赖第三方库（纯标准库）。
"""

from __future__ import annotations

import hashlib
import json
import mmap
import os
import re
import sys
import time

GAME_DIR = r"D:\GAMES\EFT"
ASSETS = os.path.join(GAME_DIR, "EscapeFromTarkov_Data", "resources.assets")
EXE = os.path.join(GAME_DIR, "EscapeFromTarkov.exe")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "game-truth")
LOCAL_BT = os.path.join(ROOT, "data", "armor-bt.json")
LOCAL_RI = os.path.join(ROOT, "data", "armor-ricochet.json")
DIFF_OUT = os.path.join(ROOT, "docs", "r58b-game-truth-diff.json")

ID_RE = re.compile(rb'"_id"\s*:\s*"([0-9a-f]{24})"')
PRINTABLE = set(range(0x20, 0x100)) | {0x09, 0x0A, 0x0D}
# 只把「护甲板/软甲/头盔片」槽计入耐久合计；mod_nvg / mod_mount / mod_equipment* 是挂件槽，不是防护层。
ARM_SLOT_RE = re.compile(r"(plate|helmet|soft_armor|sofr_armor|collar|shoulder|groin)", re.I)


def exe_version() -> str:
    """取 exe 版本（FileVersion），失败返回 unknown。"""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        path = EXE
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return "unknown"
        buf = ctypes.create_string_buffer(size)
        ver.GetFileVersionInfoW(path, 0, size, buf)
        ptr = ctypes.c_void_p()
        ln = wintypes.UINT()
        ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(ln))
        info = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
        ms, ls = info[2], info[3]
        return "%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:
        return "unknown"


def brace_object(buf, start: int, limit: int = 2_000_000):
    """从 start 处的 '{' 起做字符串感知的括号配对，返回 (payload, end)。"""
    depth = 0
    i = start
    in_str = False
    esc = False
    n = len(buf)
    if start >= n or buf[start:start + 1] != b"{":
        return None, start
    while i < n:
        c = buf[i:i + 1]
        if in_str:
            if esc:
                esc = False
            elif c == b"\\":
                esc = True
            elif c == b'"':
                in_str = False
        else:
            if c == b'"':
                in_str = True
            elif c == b"{":
                depth += 1
            elif c == b"}":
                depth -= 1
                if depth == 0:
                    return buf[start:i + 1], i + 1
        i += 1
        if i - start > limit:
            return None, i
    return None, n


def iter_items(buf):
    """遍历所有 item 模板对象（含嵌套重复，按 _id 去重）。"""
    seen = set()
    for m in ID_RE.finditer(buf):
        item_id = m.group(1).decode()
        if item_id in seen:
            continue
        # _id 前面最近的 '{' 即对象起点
        pos = m.start()
        while pos > 0 and buf[pos:pos + 1] != b"{":
            pos -= 1
            if m.start() - pos > 40:
                break
        if pos <= 0 or buf[pos:pos + 1] != b"{":
            continue
        payload, _ = brace_object(buf, pos)
        if not payload:
            continue
        try:
            obj = json.loads(payload.decode("utf-8", "replace"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if not {"_id", "_name", "_props"} <= set(obj.keys()):
            continue
        seen.add(item_id)
        yield obj


ARMOR_PROPS = (
    "BluntThroughput", "RicochetParams", "armorClass", "MaxDurability", "Durability",
    "ArmorMaterial", "ArmorType", "MaterialType", "Indestructibility",
    "BlindnessProtection", "DeafStrength", "armorColliders", "armorPlateColliders",
    "speedPenaltyPercent", "mousePenalty",
)

# R62：弹药弹道字段（PenetrationPowerDiviation 是官方模板里真实存在的字段名，
# 不是拼写错误；CreateShot 用它做 GetNormalDistributedRandomFloat 的正态浮动）。
AMMO_PROPS = (
    "Damage", "ArmorDamage", "PenetrationPower", "PenetrationPowerDiviation",
    "FragmentationChance", "RicochetChance", "InitialSpeed", "BallisticCoeficient",
    "BulletMassGram", "BulletDiameterMilimeters", "MinFragmentsCount", "MaxFragmentsCount",
    "PenetrationChanceObstacle", "ammoType", "Caliber",
)


def item_record(obj: dict) -> dict:
    p = obj.get("_props") or {}
    rec = {
        "id": obj.get("_id"),
        "name": obj.get("_name"),
        "parent": obj.get("_parent"),
        "type": obj.get("_type"),
        "props": {k: p.get(k) for k in ARMOR_PROPS if k in p},
    }
    if "PenetrationPowerDiviation" in p:
        rec["ammo_props"] = {k: p.get(k) for k in AMMO_PROPS if k in p}
    slots = []
    for s in (p.get("Slots") or []):
        if not isinstance(s, dict):
            continue
        plates = []
        for f in ((s.get("_props") or {}).get("filters") or []):
            for pid in (f.get("Filter") or []):
                if isinstance(pid, str) and len(pid) == 24 and pid not in plates:
                    plates.append(pid)
        slots.append({"slot": s.get("_name"), "plates": plates})
    rec["slots"] = slots
    return rec


def extract_globals(buf):
    """定位并解析客户端 globals 配置 JSON（内嵌 TextAsset）。"""
    anchor = buf.find(b'"BluntDamageReduceFromSoftArmorMod"')
    if anchor < 0:
        return None, "anchor-missing"
    # 向左右扩展到连续可打印文本区
    lo = anchor
    while lo > 0 and buf[lo - 1] in PRINTABLE:
        lo -= 1
    hi = anchor
    n = len(buf)
    while hi < n and buf[hi] in PRINTABLE:
        hi += 1
    blob = bytes(buf[lo:hi])
    # 从第一个 '{' 开始尝试解析，逐步收缩到最后一个 '}'
    start = blob.find(b"{")
    end = blob.rfind(b"}")
    if start < 0 or end <= start:
        return None, "no-braces"
    text = blob[start:end + 1].decode("utf-8", "replace")
    try:
        return json.loads(text), "ok"
    except Exception as exc:
        # 二进制区可能夹在中间：退回按键值提取
        return None, f"json-fail:{exc.__class__.__name__}"


CONST_KEY_RE = re.compile(
    r"(Ballistic|Armor|Penetration|Penetr|Blunt|Ricochet|Durab|Degrad|Damage|Resist)", re.I)


def walk_constants(node, path="", out=None, depth=0):
    if out is None:
        out = []
    if depth > 12:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, (dict, list)):
                walk_constants(v, p, out, depth + 1)
            elif CONST_KEY_RE.search(str(k)) and isinstance(v, (int, float, bool, str)):
                if isinstance(v, str) and len(v) > 80:
                    continue
                out.append({"path": p, "value": v})
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)):
                walk_constants(v, f"{path}[{i}]", out, depth + 1)
    return out


def cmd_extract():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {
        "source": {
            "install": GAME_DIR,
            "assets": ASSETS,
            "assets_bytes": os.path.getsize(ASSETS),
            "exe_version": exe_version(),
        },
        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(ASSETS, "rb") as f, open(ASSETS, "rb") as f2:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        sha = hashlib.sha256()
        while True:
            chunk = f2.read(1 << 24)
            if not chunk:
                break
            sha.update(chunk)
        meta["source"]["sha256"] = sha.hexdigest()

        items = {}
        for obj in iter_items(mm):
            items[obj["_id"]] = item_record(obj)

        globals_json, gstatus = extract_globals(mm)
        mm.close()

    armor_likes = {}
    plates = {}
    ammo_likes = {}
    for iid, rec in items.items():
        if "ammo_props" in rec:
            ammo_likes[iid] = rec
        pr = rec["props"]
        if "BluntThroughput" not in pr and "armorClass" not in pr:
            continue
        armor_likes[iid] = rec
        cls = str(pr.get("armorClass", "0"))
        maxdur = pr.get("MaxDurability") or 0
        if cls not in ("0", "") and float(maxdur) > 0 and rec["name"] and "armor" in (rec["name"] or ""):
            plates[iid] = rec

    # 板槽聚合：只看护甲槽（排除 mod_* 挂件槽），每个槽取「兼容板里最高耐久」为代表
    agg = {}
    structure = {"slotted_base_zero": 0, "slotted_base_nonzero": 0,
                 "monolithic": 0, "no_slots_base_zero": 0}
    for iid, rec in armor_likes.items():
        slots = [s for s in rec["slots"] if s["plates"] and ARM_SLOT_RE.search(s["slot"] or "")]
        base_cls = str(rec["props"].get("armorClass", "0") or "0")
        base_dur = float(rec["props"].get("MaxDurability") or 0)
        has_base = base_cls not in ("0", "None") and base_dur > 0
        if slots:
            if has_base:
                structure["slotted_base_nonzero"] += 1
            else:
                structure["slotted_base_zero"] += 1
        elif has_base:
            structure["monolithic"] += 1
        else:
            structure["no_slots_base_zero"] += 1
        if not slots:
            continue
        rows = []
        for s in slots:
            cls, durs, mats, pbt, ids = set(), [], set(), set(), []
            for pid in s["plates"]:
                it = items.get(pid)
                if not it:
                    continue
                pr = it["props"]
                c = str(pr.get("armorClass", "0") or "0")
                d = float(pr.get("MaxDurability") or 0)
                if c in ("0", "None") and d <= 0:
                    continue
                ids.append(pid)
                if c not in ("0", "None"):
                    cls.add(int(c))
                if d > 0:
                    durs.append(round(d, 2))
                if pr.get("ArmorMaterial"):
                    mats.add(pr["ArmorMaterial"])
                if pr.get("BluntThroughput") is not None:
                    pbt.add(float(pr["BluntThroughput"]))
            if not ids:
                continue
            rows.append({
                "slot": s["slot"], "plate_ids": sorted(set(ids)),
                "classes": sorted(cls), "durs": sorted(set(durs)),
                "rep_dur": max(durs) if durs else 0.0,
                "materials": sorted(mats),
                "plate_bt": sorted(pbt),
            })
        if not rows:
            continue
        agg[iid] = {
            "all_slots": len([s for s in rec["slots"] if s["plates"]]),
            "armor_slots": len(rows),
            "slots": rows,
            "plate_ids": sorted({p for r in rows for p in r["plate_ids"]}),
            "plate_count": len({p for r in rows for p in r["plate_ids"]}),
            "plate_max_class": max([max(r["classes"]) for r in rows if r["classes"]] or [0]),
            "plate_class_set": sorted({c for r in rows for c in r["classes"]}),
            "plate_sum_maxdur": round(sum(r["rep_dur"] for r in rows), 2),
            "base_class": base_cls,
            "base_maxdur": base_dur,
            "base_bt": rec["props"].get("BluntThroughput"),
        }

    out_meta = dict(meta)
    out_meta["counts"] = {
        "items_total": len(items),
        "armor_likes": len(armor_likes),
        "plates": len(plates),
        "ammo_ballistic": len(ammo_likes),
        "with_plate_slots": len(agg),
        "globals_parse": gstatus,
    }
    out_meta["structure"] = structure
    _dump(os.path.join(OUT_DIR, "meta.json"), out_meta)
    _dump(os.path.join(OUT_DIR, "armor_items.json"), {
        "schema": "eftmap.game-truth.armor/1",
        "source": out_meta["source"],
        "extracted_at": out_meta["extracted_at"],
        "items": armor_likes,
        "plate_aggregates": agg,
    })
    _dump(os.path.join(OUT_DIR, "armor_plates.json"), {
        "schema": "eftmap.game-truth.plates/1",
        "source": out_meta["source"],
        "extracted_at": out_meta["extracted_at"],
        "items": plates,
    })
    _dump(os.path.join(OUT_DIR, "ammo_ballistic.json"), {
        "schema": "eftmap.game-truth.ammo-ballistic/1",
        "source": out_meta["source"],
        "extracted_at": out_meta["extracted_at"],
        "items": ammo_likes,
    })

    if globals_json is not None:
        consts = walk_constants(globals_json)
        cfg = globals_json.get("data", {}).get("config", globals_json)
        sub = {}
        for k in ("Ballistic", "BluntDamageReduceFromSoftArmorMod",
                  "BodyPartColliderSettings", "armor", "ArmorMaterials", "RepairSettings"):
            if k in cfg:
                sub[k] = cfg[k]
        if "SkillsSettings" in cfg and "HeavyVests" in (cfg["SkillsSettings"] or {}):
            sub["SkillsSettings.HeavyVests"] = cfg["SkillsSettings"]["HeavyVests"]
        _dump(os.path.join(OUT_DIR, "globals_ballistic.json"), {
            "schema": "eftmap.game-truth.globals/1",
            "source": out_meta["source"],
            "extracted_at": out_meta["extracted_at"],
            "config_path": "data.config",
            "subset": sub,
            "constants": consts,
        })
    else:
        _dump(os.path.join(OUT_DIR, "globals_ballistic.json"), {
            "schema": "eftmap.game-truth.globals/1",
            "source": out_meta["source"],
            "extracted_at": out_meta["extracted_at"],
            "error": gstatus,
        })

    print(json.dumps(out_meta, ensure_ascii=False, indent=2))
    print(f"done in {time.time() - t0:.1f}s")


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_local():
    with open(LOCAL_BT, "r", encoding="utf-8") as f:
        bt = json.load(f)
    with open(LOCAL_RI, "r", encoding="utf-8") as f:
        ri = json.load(f)
    return bt, ri


def cmd_compare():
    with open(os.path.join(OUT_DIR, "armor_items.json"), "r", encoding="utf-8") as f:
        gt = json.load(f)
    items = gt["items"]
    agg = gt.get("plate_aggregates", {})
    bt, ri = _load_local()
    raw = bt.get("items")
    if isinstance(raw, dict):
        local_bt = raw
    else:
        local_bt = {}
        for blk in raw or []:
            local_bt.update(blk)
    raw_ri = ri.get("helmets")
    local_ri = raw_ri if isinstance(raw_ri, dict) else {}

    diffs = []
    same = {"bt": 0, "ricochet": 0}
    missing_in_game = []
    game_only = []
    cls_cmp = {"same": 0, "diff": 0}
    dur_cmp = {"same": 0, "diff": 0}
    bt_layer = []
    ambiguous = []

    for iid, rec in sorted(items.items()):
        pr = rec["props"]
        if "BluntThroughput" not in pr:
            continue
        game_only.append(iid)

    for iid, lv in sorted(local_bt.items()):
        rec = items.get(iid)
        if not rec or "BluntThroughput" not in rec["props"]:
            missing_in_game.append(iid)
            continue
        gv = float(rec["props"]["BluntThroughput"])
        l_bt = float(lv["bt"])
        if abs(gv - l_bt) < 1e-9:
            same["bt"] += 1
        else:
            a0 = agg.get(iid) or {}
            pbt = sorted({v for r in a0.get("slots", []) for v in r.get("plate_bt", [])})
            in_plate = bool(pbt) and any(abs(l_bt - v) < 1e-9 for v in pbt)
            if in_plate:
                bt_layer.append({
                    "id": iid, "name": rec.get("name"),
                    "base_bt": gv, "local_bt": l_bt, "plate_bt": pbt,
                    "note": "游戏本体 BT=%s，本地取的是护甲板/软甲 BT" % gv,
                })
            diffs.append({
                "id": iid, "name": rec.get("name"), "field": "bluntThroughput",
                "game": gv, "local": l_bt, "delta": round(l_bt - gv, 6),
                "severity": "medium" if in_plate else "high",
                "note": "本体 BT != 板 BT，本地取板值" if in_plate else "本体 BT 与本地不一致",
                "plate_bt": pbt,
            })

        gr = (rec["props"].get("RicochetParams") or {})
        lr = local_ri.get(iid)
        if lr and gr:
            gxyz = [float(gr.get(k, 0)) for k in ("x", "y", "z")]
            lxyz = [float(lr.get(k, 0)) for k in ("x", "y", "z")]
            if all(abs(a - b) < 1e-9 for a, b in zip(gxyz, lxyz)):
                same["ricochet"] += 1
            else:
                diffs.append({
                    "id": iid, "name": rec.get("name"), "field": "ricochetParams",
                    "game": gxyz, "local": lxyz,
                    "delta": [round(b - a, 6) for a, b in zip(gxyz, lxyz)],
                    "severity": "medium",
                })

        a = agg.get(iid)
        if a:
            # 只有「每个护甲槽都只有 1 块兼容板」时，聚合值才是唯一真值；
            # 多兼容板的槽（如 IOTV/THOR 的前后板）只能给出兼容上限，不能判错。
            single = all(len(r["plate_ids"]) == 1 for r in a["slots"])
            if not single:
                ambiguous.append({
                    "id": iid, "name": rec.get("name"),
                    "local_cls": lv.get("cls"), "local_dur": lv.get("dur"),
                    "ceiling_cls": a["plate_max_class"], "ceiling_dur": a["plate_sum_maxdur"],
                    "note": "槽内有多种兼容插板，聚合值依赖选板，仅供上限参考",
                })
                continue
            gcls = int(a["plate_max_class"])
            if lv.get("cls") and gcls:
                if int(lv["cls"]) == gcls:
                    cls_cmp["same"] += 1
                else:
                    cls_cmp["diff"] += 1
                    diffs.append({
                        "id": iid, "name": rec.get("name"), "field": "cls",
                        "game_base": a["base_class"], "game_plate_max": gcls,
                        "local": lv["cls"], "severity": "high",
                        "note": "本体 armorClass=0，等级在唯一护甲板",
                    })
            gdur = a["plate_sum_maxdur"]
            if lv.get("dur") and gdur:
                if abs(float(lv["dur"]) - gdur) <= 0.5:
                    dur_cmp["same"] += 1
                else:
                    dur_cmp["diff"] += 1
                    diffs.append({
                        "id": iid, "name": rec.get("name"), "field": "dur",
                        "game_base": a["base_maxdur"], "game_plate_sum": gdur,
                        "local": lv["dur"], "delta": round(float(lv["dur"]) - gdur, 2),
                        "severity": "medium",
                        "note": "本体 MaxDurability=0，本地与各护甲槽耐久之和不一致",
                    })

    out = {
        "schema": "eftmap.r58b.game-truth-diff/1",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": gt.get("source"),
        "summary": {
            "local_bt_entries": len(local_bt),
            "local_ricochet_entries": len(local_ri),
            "game_armor_entries": len(game_only),
            "bt_same": same["bt"],
            "ricochet_same": same["ricochet"],
            "local_with_armor_slots": sum(1 for i in local_bt if i in agg),
            "cls_same": cls_cmp["same"],
            "cls_diff": cls_cmp["diff"],
            "dur_same": dur_cmp["same"],
            "dur_diff": dur_cmp["diff"],
            "bt_layer_conflicts": len(bt_layer),
            "plate_slots_ambiguous": len(ambiguous),
            "diff_count": len(diffs),
            "local_missing_in_game": len(missing_in_game),
            "game_missing_in_local": len(set(game_only) - set(local_bt)),
            "with_plate_structure": len(agg),
        },
        "diffs": diffs,
        "bt_layer_conflicts": bt_layer,
        "plate_slots_ambiguous": ambiguous,
        "local_ids_missing_in_game": missing_in_game,
        "game_ids_missing_in_local": sorted(set(game_only) - set(local_bt)),
        "plate_aggregates": agg,
    }
    os.makedirs(os.path.dirname(DIFF_OUT), exist_ok=True)
    with open(DIFF_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if mode == "extract":
        cmd_extract()
    elif mode == "compare":
        cmd_compare()
    else:
        raise SystemExit(f"unknown mode: {mode}")
