# -*- coding: utf-8 -*-
"""R19.18 真实槽位数据修正表（上游 tarkov.dev 快照 vs 游戏内实际安装位）。

背景：`data/items.json` 是 tarkov.dev 的快照（见 data/meta.json）。少数配件的**子槽**
与游戏内实际安装位不一致——要么是游戏里根本不存在的接口，要么是同一条导轨被拆成
多个重复槽位。本模块把这些修正集中成一张表：

  · `drop`：按**真实槽位 id**（上游 slot id）删除该物品的子槽，其余槽位原样保留；
  · 每条修正都写明 `evidence`（游戏内实测结论），便于复核与回滚。

修正只动「多出来的槽位」，不修改任何真实兼容关系（allow 列表）、不改父子结构、
不触碰用户的人工校准数据。

同一张表被两处使用：
  · `tools/fetch_data.py` —— 下次刷新上游数据时自动套用（不会回退）；
  · `tools/r1926_datafix.py` —— 对当前 data/items.json 就地套用（带备份 + 报告）。
"""
from __future__ import annotations

# 物品 id → {drop: [真实槽位 id], evidence: 依据}
R1918_ITEM_SLOT_FIXES = {
    # ---- 问题 2 / 7：AK 照门兼容性 ----
    # R19.21 游戏内实测推翻 R19.18 的「叶式照门无 AKMP 接口」结论：AKMP 系统照门装置
    # 正是 6P1 Sb.2（AK-74 照门 5649b054…）/ 6P20 Sb.2（AK-74M 照门 5ac72e47…）/
    # 6P44 Sb.1-30（AK-105 照门 5ac733a4…）的**子配件**。三条删除项已移除，
    # 子槽随上游数据自然保留（见 R1921_ITEM_SLOT_FIXES 的反向修正说明）。

    # ---- 问题 8：VSK-94 不得出现 VSS/VAL 环形基座槽位 ----
    # 「9A-91 9x39 消音器」（VSK-94 用）的 mod_mount 子槽 allow 只有
    # 「Zenit B-3 VSS/VAL 环形基座」——那是 VSS / VAL 一体式枪管才有的接口。
    # VSS / AS VAL 的一体式枪管（57838c96… / 57c44dd0…）保持原样，不受影响。
    "64527a3a7da7133e5a09ca99": {
        "evidence": "in-game-confirmed: 9A-91 消音器无 VSS/VAL B-3 环形基座接口（R19.18 问题 8）",
        "drop": ["64527a3a7da7133e5a09ca9b"],
    },

    # ---- 问题 9：AS VAL MOD.4 套件护木的 3.5 英寸导轨槽位重复 ----
    # mod_mount_000 与 mod_mount_001 的 allow 完全相同（都只收「NB MOD.4 套件 3.5 英寸导轨」），
    # 游戏内只有**一个** 3.5 英寸导轨位；上游把同一条导轨拆成了两个槽位。
    "687128c4505fed5f370b1625": {
        "evidence": "in-game-confirmed: 3.5 英寸导轨只有一个安装位（R19.18 问题 9）",
        "drop": ["68712a1e505fed5f370b162e"],
    },

    # ---- 问题 4：T-5000 护木的导轨位重复（多出两个战术设备槽位）----
    # mod_mount_000/001/002 的 allow 完全相同（[Oris 长导轨, Oris 中导轨]），
    # 游戏内护木只有两个导轨安装位（一个长/中导轨位 + 一个中导轨位），
    # 上游把同一条导轨拆成 4 个槽位 → 战术设备槽位比游戏实际多两个。
    "5df25d3bfd6b4e6e2276dc9a": {
        "evidence": "in-game-confirmed: T-5000 护木只有两个导轨安装位（R19.18 问题 4）",
        "drop": ["5df25d3bfd6b4e6e2276dc9d", "5df25d3bfd6b4e6e2276dc9e"],
    },

    # ---- 问题 10：TKPD 护木的多余战术设备槽位 ----
    # mod_mount_001 / mod_mount_002 是同一条战术导轨被拆成的左右镜像位
    # （allow 仅差一件 Insight AN/PEQ-2），游戏内护木只有 mod_tactical 一个战术接口；
    # 删除后保留 mod_tactical（真实战术接口）与 mod_mount_003（瞄具基座）。
    "68aee9fe130c00663d08aeb6": {
        "evidence": "in-game-confirmed: TKPD 护木（黑色）只有一个战术接口（R19.18 问题 10）",
        "drop": ["68aee9fe130c00663d08aeba", "68aee9fe130c00663d08aebb"],
    },
    "68d5676f43adc7372a0c8ae0": {
        "evidence": "in-game-confirmed: TKPD 护木（FDE）只有一个战术接口（R19.18 问题 10）",
        "drop": ["68d5676f43adc7372a0c8ae3", "68d5676f43adc7372a0c8ae4"],
    },
}


# ============================================================================
# R19.19：AK 照门槽位修复（任务 A2）
# ============================================================================
# 「AKM 照门」与「VPO-209 照门」各自带了一个 mod_sight_rear 子槽，allow 只有
# 「AKMP系统照门装置」——于是在 AKM/AKMS/AKMN/AKMSN/VPO-136 的默认装配下，
# 照门区域出现**两个**照门安装槽（枪身照门槽 + 这个 AKMP-only 子槽）。
# 游戏内实测（R19.19 任务书）：相关枪械只有一个照门安装槽。
#
# 修法（语义等价迁移，不是视觉隐藏）：
#   1) 删除 AKM 照门上「不应该独立存在」的 AKMP-only 子槽（本表）；
#   2) 把 AKMP系统照门装置并入枪身唯一照门槽 mod_sight_rear 的 allow
#      （R1919_GUN_SLOT_ALLOW_ADDS）——AKMP RS 对 AKM 枪族的合法兼容能力
#      保持不变（R19.18 问题 7 / R19.19 A3 明确 AKM 系合法使用 AKMP RS）。
#
# 作用范围：仅 7.62x39 的五把 AK（AKM/AKMS/AKMN/AKMSN/VPO-136）。
# VPO-209（.366TKM）的同构子槽（id=5a0eeb41…）按任务书口径**保留未动**，
# 在报告中单独列出待用户裁决。
# R19.20 更新：游戏内实测推翻 R19.19 A2 的「单槽合并」结论——AKM 照门与
# AKMP 系统照门装置是**并列的两个照门槽位**（左 AKM / 右 AKMP）。AKM 照门的
# AKMP 子槽（5a0eda49…）已恢复（真实父子语义保留，显示层并列右置），
# 因此 R19.19 的删除表**清空**（保留表名供 fetch_data 挂接点继续引用）。
R1919_ITEM_SLOT_FIXES = {}

# 枪械 id → {槽位 sid → [补入 allow 的物品 id]}
# R19.20 更新：R19.19 的「AKMP 并入枪身照门槽 allow」已作废——AKMP RS 走
# AKM 照门的并列子槽（左 AKM 照门 / 右 AKMP），两槽候选不混淆。表清空。
# R19.21 更新：R19.20 的「AKM 照门/AKMP 并列」假设亦被推翻——AKMP 是
# 6P1 Sb.2 / 6P20 Sb.2 / 6P44 Sb.1-30 三种标准照门的子配件（正上方同列显示）。
AKMP_RS = "5a0ed824fcdbcb0176308b0d"   # AKMP系统照门装置
R1919_GUN_SLOT_ALLOW_ADDS = {}

# ============================================================================
# R19.21：AKMP 真实父子关系修正（任务 3.2）
# ============================================================================
# 游戏内实测确认 AKMP 系统照门装置（5a0ed824…）的父照门是且仅是：
#   6P44 Sb.1-30 = AK-105 照门  5ac733a45acfc400192630e2
#   6P20 Sb.2    = AK-74M 照门  5ac72e475acfc400180ae6fe
#   6P1 Sb.2     = AK-74 照门   5649b0544bdc2d1b2b8b458a
# 三种照门的 AKMP 子槽在 R1918_ITEM_SLOT_FIXES 中被误删 → 已恢复（见上）。
#
# 「AKM 照门 6P1 Sb.2-1」（59d650cf86f7741b846413a4）上的 AKMP 子槽属于
# R19.20 并列假设的错误建模（上游快照虽有此子槽，但与实测确认的三个父照门
# 不符——差异已在 R19.21 交付报告单独列出）→ 按实测数据删除。
R1921_ITEM_SLOT_FIXES = {
    "59d650cf86f7741b846413a4": {
        "evidence": "in-game-confirmed(R19.21): AKMP 系统照门装置的父照门是 6P1 Sb.2 / "
                    "6P20 Sb.2 / 6P44 Sb.1-30 三种标准照门；AKM 照门 6P1 Sb.2-1 上的 "
                    "AKMP 子槽为并列假设时代的错误建模，按实测删除（上游差异见交付报告）",
        "drop": ["5a0eda49fcdbcb001912fa61"],
    },
}

# R19.21 确认的三个 AKMP 父照门（显示层按父件物品 ID 判定，不看枪名）
R1921_AKMP_PARENT_SIGHTS = {
    "5ac733a45acfc400192630e2",   # 6P44 Sb.1-30（AK-105 照门）
    "5ac72e475acfc400180ae6fe",   # 6P20 Sb.2（AK-74M 照门）
    "5649b0544bdc2d1b2b8b458a",   # 6P1 Sb.2（AK-74 照门）
}


def apply_gun_slot_allow_adds(guns: dict, adds: dict | None = None) -> list:
    """把「并入唯一照门槽」的物品补进枪身槽位 allow（去重、不改其他候选）。"""
    adds = R1919_GUN_SLOT_ALLOW_ADDS if adds is None else adds
    report = []
    for gun_id, by_sid in adds.items():
        gun = guns.get(gun_id)
        if not gun:
            report.append({"gunId": gun_id, "status": "missing-gun", "added": []})
            continue
        added = []
        for slot in gun.get("slots") or []:
            sid = slot.get("sid")
            if sid not in by_sid:
                continue
            allow = slot.setdefault("allow", [])
            for item_id in by_sid[sid]:
                if item_id not in allow:
                    allow.append(item_id)
                    added.append({"sid": sid, "itemId": item_id})
        for slot in gun.get("slots") or []:
            if slot.get("sid") in by_sid:
                slot["fix"] = ("R19.19 A2: AKMP RS 并入唯一照门安装槽（等价迁移，"
                               "保留 AKM 枪族合法 AKMP 兼容能力）")
        report.append({"gunId": gun_id, "name": gun.get("n") or gun_id,
                       "status": "fixed" if added else "unchanged", "added": added})
    return report


def apply_item_slot_fixes(items: dict, fixes: dict | None = None) -> list:
    """就地删除 items[id].slots 里被修正掉的真实槽位，返回变更报告列表。"""
    fixes = R1918_ITEM_SLOT_FIXES if fixes is None else fixes
    report = []
    for item_id, fix in fixes.items():
        rec = items.get(item_id)
        if not rec:
            report.append({"itemId": item_id, "status": "missing-item", "dropped": []})
            continue
        slots = rec.get("slots") or []
        drop = set(fix.get("drop") or [])
        kept = [s for s in slots if s.get("id") not in drop]
        dropped = [s.get("id") for s in slots if s.get("id") in drop]
        if dropped:
            rec["slots"] = kept
            for s in kept:
                s["fix"] = fix.get("evidence")
        report.append({
            "itemId": item_id,
            "name": rec.get("n") or item_id,
            "status": "fixed" if dropped else "unchanged",
            "dropped": dropped,
            "droppedSids": [s.get("sid") for s in slots if s.get("id") in drop],
            "evidence": fix.get("evidence"),
        })
    return report


def slot_ids_of(item_id: str, items: dict) -> list:
    rec = items.get(item_id) or {}
    return [s.get("id") for s in (rec.get("slots") or [])]
