# -*- coding: utf-8 -*-
"""生成中文显示名表 + 覆盖率检查（R19.22）。

产物
----
data/i18n/names.json      商人 / 任务 / 地图 / 槽位的「英文（或 id）→ 中文」表，
                          供 i18n.js 在显示层查表；原始数据一个字节都不改。
data/i18n/items-zh.json   仍为英文名的物品（主要是弹种）→ 中文显示名。
docs/r19.22-tasks-i18n/i18n-coverage.json
                          覆盖率报告：界面扫描到的英文 → 是否有映射 / 是否白名单。

用法
----
    python tools/build_i18n.py            # 生成 + 报告
    python tools/build_i18n.py --check    # 只检查（有未覆盖英文则退出码 1）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
I18N = os.path.join(DATA, "i18n")
TASKS = os.path.join(DATA, "tasks")
OUT_DOCS = os.path.join(ROOT, "docs", "r19.22-tasks-i18n")

CJK = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]{2,}")

# 槽位 id → 中文显示名（与 app.js 的 GUN_SLOT_LABELS 同源；任务模块 / 校准器提示用）
SLOTS = {
    "mod_reciever": "机匣", "mod_barrel": "枪管", "mod_handguard": "护木",
    "mod_muzzle": "枪口装置", "mod_sight_rear": "照门", "mod_sight_front": "准星",
    "mod_stock": "枪托", "mod_pistol_grip": "握把", "mod_magazine": "弹匣",
    "mod_mount": "安装座", "mod_mount_000": "安装座 1", "mod_mount_001": "安装座 2",
    "mod_mount_002": "安装座 3", "mod_mount_003": "安装座 4", "mod_mount_004": "安装座 5",
    "mod_scope": "瞄具", "mod_tactical": "战术配件", "mod_tactical_000": "战术配件 1",
    "mod_tactical_001": "战术配件 2", "mod_tactical_002": "战术配件 3",
    "mod_tactical_003": "战术配件 4", "mod_charge": "拉机柄", "mod_gas_block": "导气箍",
    "mod_launcher": "榴弹发射器", "mod_foregrip": "前握把", "mod_flashlight": "战术灯",
    "mod_laser": "激光指示器", "mod_suppressor": "消音器", "mod_bipod": "两脚架",
    "mod_trigger": "扳机", "mod_hammer": "击锤", "mod_nvg": "夜视仪座",
    "mod_equipment": "装备座", "mod_equipment_000": "装备座 1",
    "mod_equipment_001": "装备座 2", "mod_equipment_002": "装备座 3",
    "mod_catch": "机匣盖", "mod_ammo": "弹药", "mod_pistol_grip_akms": "AKMS 握把",
    "mod_stock_000": "枪托 1", "mod_stock_001": "枪托 2",
}

# 弹种后缀 → 中文（只翻「弹种」，口径与品牌型号保留原文，避免失去辨识度）
PROJECTILE = [
    ("Hollow Point", "空尖弹"), ("Soft Point", "软尖弹"), ("Lasermatch FMJ", "激光匹配全被甲弹"),
    ("TAC-X", "TAC-X 铜弹"), ("Hydra-Shok", "Hydra-Shok 空尖弹"),
    ("FMJ", "全金属被甲弹"), ("AP", "穿甲弹"), ("JHP", "空尖弹"), ("JSP", "软尖弹"),
    ("SP", "软尖弹"), ("HP", "空尖弹"), ("CBJ", "CBJ 弹"), ("BPZ", "BPZ 弹"),
    ("V-Max", "V-Max 弹"), ("UCW", "UCW 弹"), ("Geksa", "Geksa 弹"),
    ("EKO", "EKO 弹"), ("LOKT", "LOKT 弹"), ("Bull", "牛头弹"), ("RIP", "RIP 弹"),
]

# 少数需要人工定名的（不按规则拼）
ITEM_OVERRIDES = {
    ".300 Whisper": ".300 Whisper（低噪弹）",
    ".366 AP": ".366 AP 穿甲弹",
    "M14 DCSB": "M14 DCSB 枪托",
}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def ammo_zh(name: str) -> str:
    """英文弹名 → 中文显示名：保留口径 + 品牌，翻译弹种后缀。"""
    if name in ITEM_OVERRIDES:
        return ITEM_OVERRIDES[name]
    for suffix, zh in PROJECTILE:
        if name.endswith(" " + suffix):
            head = name[: -(len(suffix) + 1)].strip()
            return "%s %s" % (head, zh)
    # 没有可识别弹种：保留型号并补一个中文量词，避免整条英文裸奔
    return "%s 弹" % name


def build_names() -> dict:
    traders_term = (load_json(os.path.join(I18N, "traders.json"), {}) or {}).get("traders") or {}
    items_doc = load_json(os.path.join(DATA, "items.json"), {}) or {}
    items = items_doc.get("items") or {}
    raw_traders = items_doc.get("traders") or {}
    raw_tasks = items_doc.get("tasks") or {}

    traders = {}
    # 先并入人工维护的商人表（含上游占位名里没有的新商人：BTR Driver / Ref …）
    for slug, term in traders_term.items():
        if term.get("nameEn") and term.get("nameZh"):
            traders[term["nameEn"]] = term["nameZh"]
            traders[slug] = term["nameZh"]
    for tid, rec in raw_traders.items():
        slug = (rec.get("nn") or "").lower()
        term = traders_term.get(slug) or {}
        en = rec.get("n") or term.get("nameEn")
        zh = term.get("nameZh")
        if en and zh:
            traders[en] = zh
        if slug and zh:
            traders[slug] = zh

    # 任务：items.json 里的英文名（125 条）与任务数据的同 ID 中文名对接
    tasks = {}
    pve = load_json(os.path.join(TASKS, "tasks.regular.json"), {}) or {}
    for tid, rec in (pve.get("tasks") or {}).items():
        en = raw_tasks.get(tid)
        if en and rec.get("nameZh"):
            tasks[en] = rec["nameZh"]
    for mode in ("regular", "pve"):
        doc = load_json(os.path.join(TASKS, "tasks.%s.json" % mode), {}) or {}
        for tid, rec in (doc.get("tasks") or {}).items():
            if tid in raw_tasks and rec.get("nameZh"):
                tasks[raw_tasks[tid]] = rec["nameZh"]

    maps = {}
    maps_doc = load_json(os.path.join(DATA, "maps.json"), {}) or {}
    for m in maps_doc.get("maps") or []:
        if m.get("id") and m.get("name"):
            maps[m["id"]] = m["name"]
        if m.get("key") and m.get("name"):
            maps[m["key"]] = m["name"]

    # 仍为英文的物品名（当前 49 条，绝大多数是弹种）
    items_zh = {}
    for iid, rec in items.items():
        name = rec.get("n") or ""
        if name and LATIN.search(name) and not CJK.search(name):
            items_zh[name] = ammo_zh(name)

    return {
        "schema": 1,
        "note": "英文（或内部 id）→ 中文显示名。仅用于显示层，原始数据保持英文/ID 不变。",
        "generatedBy": "tools/build_i18n.py",
        "traders": traders,
        "tasks": tasks,
        "maps": maps,
        "slots": SLOTS,
        "items": {},
    }, items_zh


def coverage_report(names: dict, items_zh: dict) -> dict:
    inv = load_json(os.path.join(OUT_DOCS, "i18n-inventory.json"), {}) or {}
    ui = load_json(os.path.join(I18N, "ui-zh.json"), {}) or {}
    entries = {re.sub(r"\s+", " ", k).strip(): v for k, v in (ui.get("entries") or {}).items()}
    poi = load_json(os.path.join(I18N, "poi-zh.json"), {}) or {}
    for k, v in (poi.get("entries") or {}).items():
        entries.setdefault(k, v)
    patterns = ui.get("patterns") or []
    kept = (ui.get("keptEnglish") or {})

    def kept_reason(s: str):
        """判定是否属于「合理保留英文」：型号 / 口径 / 罗马数字 / 版本号 / 内部 id / 来源。"""
        if re.match(r"^rev R\d", s):
            return "version"
        # 口径 + 数量（.45 ACP · 5）：口径型号保留，数字已本地化
        if re.match(r"^[\d\.][\w\.\s]*·\s*\d+$", s):
            return "caliber"
        # 校准器坐标差（mod_scope r2c5 → r2c6）：槽位内部 id + 坐标，必须原样可核对
        if re.match(r"^[\w/]+ r-?\d+c\d+ → r-?\d+c\d+$", s):
            return "slotId"
        if re.match(r"^[IVX]+$", s):
            return "romanLevel"
        if re.match(r"^[IVX]+ · [\d\s  ₽]+$", s):
            return "romanLevel"
        if re.match(r"^[\d\.\s]*[A-Za-z]{0,6}[\dxX]*[\sA-Za-z\.]*$", s) and re.search(r"\d", s) and not re.search(r"[a-z]{3,}", s):
            return "caliber"
        if re.match(r"^[A-Za-z0-9_]+$", s) and "_" in s:          # mod_scope 之类
            return "slotId"
        if re.match(r"^[0-9a-f]{24}$", s):
            return "slotId"
        if s in ("LEDX", "PvP", "Scav", "PDW"):
            return "brandItem"
        if "tarkov-dev" in s or "the-hideout" in s:
            return "source"
        if re.search(r"\d", s) and re.search(r"[A-Z][a-z]+", s):   # Kel-Tec RFB 7.62x51
            return "weaponModel"
        if s.endswith(".") and re.match(r"^[A-Z][A-Za-z]+( [A-Za-z]+)*\.$", s):
            return "weaponModel"
        return None

    rows = []
    stats = {"seen": 0, "mapped": 0, "kept": 0, "missing": 0, "originalTooltip": 0}

    # 属性文本：title / placeholder / aria-label。
    # 我们自己写入的「原文浮窗」形如「<英文名> · <24 位任务 ID>」，属于机制本身，不算缺口。
    def attr_status(s: str):
        if re.match(r"^.+( · [0-9a-f]{24})+$", s):
            return "originalTooltip"
        if s in entries:
            return "mapped"
        if s in items_zh or s in names.get("tasks", {}) or s in names.get("traders", {}):
            return "mapped"
        why = kept_reason(s)
        if why:
            return "kept"
        return "missing"

    for rec in inv.get("attrs") or []:
        s = rec["text"]
        # 同一段英文如果既是界面文字又出现在属性里，按界面文字的口径判（避免重复计数）
        cls = attr_status(s)
        stats["seen"] += 1
        stats[cls] = stats.get(cls, 0) + 1
        if cls == "missing":
            rows.append({"text": s, "status": "missing", "where": rec["where"], "attr": True})
    for rec in inv.get("texts") or []:
        s = rec["text"]
        if s in entries:
            stats["seen"] += 1
            stats["mapped"] += 1
            rows.append({"text": s, "status": "mapped", "zh": entries[s], "where": rec["where"]})
            continue
        if any(re.match(p["pattern"], s) for p in patterns):
            stats["seen"] += 1
            stats["mapped"] += 1
            rows.append({"text": s, "status": "pattern", "where": rec["where"]})
            continue
        if s in items_zh or s in names.get("tasks", {}) or s in names.get("traders", {}):
            stats["seen"] += 1
            stats["mapped"] += 1
            rows.append({"text": s, "status": "dataName", "where": rec["where"]})
            continue
        why = kept_reason(s)
        if why:
            stats["seen"] += 1
            stats["kept"] += 1
            rows.append({"text": s, "status": "kept", "reason": why, "where": rec["where"]})
            continue
        stats["seen"] += 1
        stats["missing"] += 1
        rows.append({"text": s, "status": "missing", "where": rec["where"]})

    report = {
        "schema": 1,
        "scannedAt": inv.get("scannedAt"),
        "views": inv.get("scannedViews") or [],
        "nodes": {"total": inv.get("totalNodes"), "latinOnly": inv.get("latinOnlyNodes")},
        "unique": {"text": inv.get("uniqueLatinTexts"), "attrs": inv.get("uniqueLatinAttrs")},
        "stats": stats,
        "dict": {"uiEntries": len(entries), "poiEntries": len(poi.get("entries") or {}),
                 "patterns": len(patterns),
                 "traders": len(names.get("traders", {})), "tasks": len(names.get("tasks", {})),
                 "maps": len(names.get("maps", {})), "items": len(items_zh),
                 "slots": len(names.get("slots", {}))},
        "keptReasons": kept.get("why") or {},
        "rows": rows,
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查覆盖率，不写文件")
    args = ap.parse_args(argv)
    names, items_zh = build_names()
    report = coverage_report(names, items_zh)
    if not args.check:
        write_json(os.path.join(I18N, "names.json"), names)
        write_json(os.path.join(I18N, "items-zh.json"),
                   {"schema": 1, "note": "英文物品名 → 中文显示名（型号保留 + 弹种翻译）",
                    "items": items_zh})
        write_json(os.path.join(OUT_DOCS, "i18n-coverage.json"), report)
    st = report["stats"]
    print("字典：ui=%d patterns=%d 商人=%d 任务=%d 地图=%d 物品=%d 槽位=%d"
          % (report["dict"]["uiEntries"], report["dict"]["patterns"], report["dict"]["traders"],
             report["dict"]["tasks"], report["dict"]["maps"], report["dict"]["items"],
             report["dict"]["slots"]))
    print("扫描到的唯一英文文本/属性 %d 条：已映射 %d / 原文浮窗 %d / 合理保留 %d / 未覆盖 %d"
          % (st["seen"], st["mapped"], st.get("originalTooltip", 0), st["kept"], st["missing"]))
    for row in report["rows"]:
        if row["status"] == "missing":
            print("  MISSING:", row["text"], "|", ",".join(row["where"])[:40])
    return 0 if (st["missing"] == 0 or not args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
