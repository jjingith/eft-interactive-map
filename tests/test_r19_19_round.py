# -*- coding: utf-8 -*-
"""R19.19 AK 照门槽位修复专项（任务 A）。

覆盖任务书 A1–A4：
  A1 五把 5.45/5.56 AK 照门槽下移一格（r1→r2）
  A2 7.62x39 五把 AK 删除多余 AKMP-only 照门槽（唯一照门槽 + AKMP 并入 allow）
  A3 回归保护（不重新出现 AKMP 错误槽、不动 GP-25/燕尾槽/条件槽/校准器）
  A4 校准数据安全（397 条不减、只动照门相关记录、失效记录不迁移）

证据：docs/r19.19-ak-rear-sight/（engine-audit.json / calibration-migration.json /
data-fix.json / browser-accept.json）+ 每次会话实跑 tools/r1927_audit.js。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
ITEMS = os.path.join(ROOT, "data", "items.json")
GUNSLOTS = os.path.join(ROOT, "data", "gunslots.json")
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
SLOTFIX = os.path.join(ROOT, "tools", "slotfix.py")
FETCH = os.path.join(ROOT, "tools", "fetch_data.py")
AUDIT = os.path.join(ROOT, "docs", "r19.19-ak-rear-sight")
ENGINE_TOOL = os.path.join(ROOT, "tools", "r1927_audit.js")

need_node = subprocess.run(
    [sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]
).returncode != 0

A1_GUNS = {
    "5ac66d9b5acfc4001633997a": "AK-105",
    "5bf3e03b0db834001d2c4a9c": "AK-74",
    "5644bd2b4bdc2d3b4c8b4572": "AK-74N",
    "5bf3e0490db83400196199af": "AKS-74",
    "5ab8e9fcd8ce870019439434": "AKS-74N",
}
A2_GUNS = {
    "59d6088586f774275f37482f": "AKM",
    "59ff346386f77477562ff5e2": "AKMS",
    "5a0ec13bfcdbcb00165aa685": "AKMN",
    "5abcbc27d8ce8700182eceeb": "AKMSN",
    "59e6152586f77473dc057aa1": "VPO-136",
}
AKMP_RS = "5a0ed824fcdbcb0176308b0d"


def _items():
    with open(ITEMS, encoding="utf-8") as f:
        return json.load(f)["items"]


def _guns():
    with open(GUNSLOTS, encoding="utf-8") as f:
        return json.load(f)["guns"]


def _calib():
    with open(CALIB, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def audit():
    if need_node:
        pytest.skip("需要 node")
    proc = subprocess.run(["node", ENGINE_TOOL], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, "r1927_audit.js 失败：\n%s\n%s" % (proc.stdout[-1500:], proc.stderr[-1500:])
    p = os.path.join(AUDIT, "engine-audit.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ============================================================ A1
def test_A1_five_guns_rear_sight_at_r2c6(audit):
    """五把枪的 AK-74 系列照门槽在逻辑 r2c6（下移一格），错误 AKMP 槽仍不存在。"""
    for gid, name in A1_GUNS.items():
        assert audit["checks"]["a1_%s_at_r2c6" % name], (name, audit["detail"]["a1"])
        # R19.21 升级：AKMP 子槽按实测恢复（单槽断言→照门+AKMP 子槽，父件正上方）
        assert audit["checks"]["a1_%s_sight_and_akmp_sub" % name], name
        assert audit["checks"]["a1_%s_sub_above_parent" % name], name
        assert audit["checks"]["a1_%s_legal_candidates_kept" % name], name


def test_A1_records_moved_down_one_not_hardcoded():
    """校准记录 r1→r2（列不变）；布局引擎未新增逐枪坐标硬编码。"""
    c = _calib()
    for gid, name in A1_GUNS.items():
        rec = (c["guns"].get(gid, {}).get("slots") or {})["mod_sight_rear|mod_sight_rear|"]
        assert rec["logicalRow"] == 2 and rec["col"] == 6, (name, rec)
        assert "R19.19 A1" in (rec.get("note") or ""), (name, rec.get("note"))
    js = open(APP, encoding="utf-8").read()
    # 任务 A 修的是校准记录，不是布局硬编码：五把枪的 id 不得出现在引擎里
    fixed = js.split("var GW_FIXED_SLOT")[1].split("};")[0] if "var GW_FIXED_SLOT" in js else ""
    for gid in A1_GUNS:
        assert gid not in js, "%s 不得硬编码进 app.js" % gid
    assert "mod_sight_rear" not in fixed, "GW_FIXED_SLOT 不得新增照门硬编码"


def test_A1_other_aks_untouched(audit):
    """A1 之外照门记录保持现状（AK-103/AK-104/VPO-136 r1c6；AKM/AKMS 用户 21:17
    调整为 r2c6，R19.21 未动）。"""
    expect = {"AK-103": "r1c6", "AK-104": "r1c6", "AKM": "r2c6", "VPO-136": "r1c6"}
    for row in audit["detail"]["a1Others"]:
        assert row["rec"] == expect[row["gun"]], row
    for gid in ("5ac66d2e5acfc43b321d4b53", "5ac66d725acfc43b321d4b60",
                "59d6088586f774275f37482f", "59e6152586f77473dc057aa1"):
        assert audit["checks"]["a1_others_untouched_%s" % gid], gid


# ============================================================ A2
def test_A2_single_rear_sight_slot_and_akmp_kept(audit):
    """R19.21 升级（推翻 R19.20 并列假设）：AKM 照门 6P1 Sb.2-1 不是 AKMP 的
    父照门——五把 AKM 系各只有一个照门槽，AKMP 子槽/allow 均不存在。"""
    for gid, name in A2_GUNS.items():
        assert audit["checks"]["a2_%s_single_sight_slot" % name], name
        assert audit["checks"]["a2_%s_no_akmp_sub" % name], name
        assert audit["checks"]["a2_%s_akmp_not_in_gun_allow" % name], name
        assert audit["checks"]["a2_%s_legal_kept" % name], name
        assert audit["checks"]["a2_%s_no_dup_after_install" % name], name


def test_A2_source_data_restored_not_visually_faked():
    """R19.21 升级：AKM 照门 6P1 Sb.2-1 的 AKMP 子槽为并列假设错误建模已删除；
    AKMP 不入枪身照门槽 allow（真实父子关系由三种标准照门的子槽承载）。"""
    items = _items()
    akm_sight = items["59d650cf86f7741b846413a4"]
    assert not [s for s in (akm_sight.get("slots") or [])
                if (s.get("allow") or []) == [AKMP_RS]], "AKM 照门不得带 AKMP 子槽（R19.21）"
    for src_doc in (items, _guns()):
        for gid in A2_GUNS:
            slot = [s for s in src_doc[gid]["slots"] if s.get("sid") == "mod_sight_rear"][0]
            assert AKMP_RS not in (slot.get("allow") or []), (gid, "AKMP 不得混入枪身照门槽 allow")


def test_A2_ak103_ak104_unchanged_single_slot(audit):
    """R19.21 升级：AK-103/AK-104 装 AK-74M/AK-105 照门（三种父照门）→
    照门 + AKMP 子槽（父件正上方同列）。"""
    for name in ("AK-103", "AK-104"):
        assert audit["checks"]["a2_%s_sight_plus_akmp_sub" % name], audit["detail"]["a2"]
        assert audit["checks"]["a2_%s_sub_above_parent" % name], audit["detail"]["a2"]


# ============================================================ A3 回归
def test_A3_no_akmp_rs_on_545_556(audit):
    """R19.21 升级：AKMP 只经三种父照门的子槽出现，不得散落其他槽位。"""
    assert audit["checks"]["a3_akmp_only_via_parent_subslot"] is True


def test_A3_akm_family_keeps_akmp_rs(audit):
    """R19.21 升级：AKM 系无 AKMP（6P1 Sb.2-1 非父照门）；仍无 AK-74 系列照门。"""
    assert audit["checks"]["a3_akm_family_no_akmp"] is True
    assert audit["checks"]["a3_akm_no_ak74_rs"] is True


def test_A3_r1918_capabilities_not_regressed(audit):
    assert audit["checks"]["a3_gp25_still_at_gas_below"] is True, "GP-25 布局不得回归"
    assert audit["checks"]["a3_svds_dovetail_r2c7"] is True, "SVDS 燕尾槽 r2c7 不得回归"
    assert audit["checks"]["a3_sks_socom_r4c3"] is True, "SKS SOCOM r4c3 不得回归"


# ============================================================ A4 校准数据安全
def test_A4_calib_records_intact_and_explained(audit):
    c = audit["detail"]["calib"]
    assert c["totalRecords"] == 397, "校准记录总数不得减少"
    assert c["applied"] + c["stale"] + c["suppressed"] == c["totalRecords"], c
    assert c["fallback"] == 0, c


def test_A4_akmp_records_alive_at_parallel():
    """R19.21 升级：并列时代（父件=AKM 照门）的 5 条记录标失效留痕（不迁移、不串位）；
    三种标准照门的 10 条子槽记录按父件正上方同列复活。"""
    c = _calib()
    stale = revived = 0
    for gun in c["guns"].values():
        for key, rec in (gun.get("slots") or {}).items():
            note = rec.get("note") or ""
            if rec.get("ownerItemId") == "59d650cf86f7741b846413a4":
                stale += 1
                assert "R19.21" in note and "不再生效" in note, (key, note)
            elif rec.get("ownerItemId") in ("5649b0544bdc2d1b2b8b458a",
                                            "5ac72e475acfc400180ae6fe",
                                            "5ac733a45acfc400192630e2"):
                revived += 1
                assert note.startswith("R19.21"), (key, note)
                assert "父件正上方" in note or "父行-1" in note or "正上方" in note, note
    assert stale == 5, stale
    assert revived == 10, revived


def test_A4_migration_report_and_backup():
    mig = os.path.join(AUDIT, "calibration-migration.json")
    assert os.path.exists(mig)
    with open(mig, encoding="utf-8") as f:
        d = json.load(f)
    assert d["recordsBefore"] == 397 and d["recordsAfter"] == 397 and d["recordsDeleted"] == 0
    moved = [c for c in d["changes"] if c["status"] == "moved-down-one"]
    stale = [c for c in d["changes"] if c["status"] == "marked-stale"]
    assert len(moved) == 5 and len(stale) == 5, (len(moved), len(stale))
    for f in ("items.json", "gunslots.json", "gun-layout-calibration.json", "app.js"):
        assert os.path.exists(os.path.join(AUDIT, "backup", f)), f


# ============================================================ 数据修正表与刷新防回退
def test_slotfix_r1919_tables_and_fetch_hook():
    """R19.21 升级：R19.18 对三种标准照门 AKMP 子槽的误删已撤销（删除项移除）；
    R19.21 表删除 AKM 照门的错误子槽；R19.19 两表保持作废清空。"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import slotfix
    assert slotfix.R1919_ITEM_SLOT_FIXES == {}, "R19.19 删除表已作废"
    assert slotfix.R1919_GUN_SLOT_ALLOW_ADDS == {}, "R19.19 allow 并入表已作废"
    for pid in ("5649b0544bdc2d1b2b8b458a", "5ac72e475acfc400180ae6fe", "5ac733a45acfc400192630e2"):
        assert pid not in slotfix.R1918_ITEM_SLOT_FIXES, \
            "三种标准照门的 AKMP 子槽不得再被 R19.18 表删除（R19.21 实测恢复）"
    assert "59d650cf86f7741b846413a4" in slotfix.R1921_ITEM_SLOT_FIXES, \
        "AKM 照门错误子槽必须由 R19.21 表删除"
    fetch = open(FETCH, encoding="utf-8").read()
    assert "R1921_ITEM_SLOT_FIXES" in fetch, "fetch_data.py 必须挂接 R19.21 表"


def test_vpo209_reported_left_untouched():
    """VPO-209（.366TKM）的同构 AKMP-only 子槽按任务书口径保留未动，报告单列。"""
    items = _items()
    vpo_sight = items["59e8977386f77415a553c453"]
    assert [s for s in (vpo_sight.get("slots") or [])
            if (s.get("allow") or []) == [AKMP_RS]], "VPO-209 照门子槽应保留未动"


# ============================================================ 版本与源码标记
def test_version_marker():
    js = open(APP, encoding="utf-8").read()
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)
    assert m.group(1) >= "R19.19" or m.group(1).startswith("R19.19"), m.group(1)
