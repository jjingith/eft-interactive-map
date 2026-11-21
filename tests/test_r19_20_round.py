# -*- coding: utf-8 -*-
"""R19.20 round 测试（断言已随 R19.21 实测升级）。

R19.20 曾按「AKM 照门与 AKMP 并列双照门位」实现；R19.21 游戏内实测推翻该假设：
AKMP 系统照门装置是 6P1 Sb.2 / 6P20 Sb.2 / 6P44 Sb.1-30 三种标准照门的子配件
（父件正上方同列），AKM 照门 6P1 Sb.2-1 上的子槽为错误建模已删除。
本文件保留 R19.20 验收场景（候选分离 / 装卸互不占位 / 刷新 / 校准器独立拖动 /
回归），断言升级为 R19.21 真值；权威审计见 tools/r1929_audit.js。
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
AUDIT = os.path.join(ROOT, "docs", "r19.21-akmp-parent-fix")
ENGINE_TOOL = os.path.join(ROOT, "tools", "r1929_audit.js")

need_node = subprocess.run(
    [sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]
).returncode != 0

GUNS = {
    "59d6088586f774275f37482f": "AKM",
    "59ff346386f77477562ff5e2": "AKMS",
    "5a0ec13bfcdbcb00165aa685": "AKMN",
    "5abcbc27d8ce8700182eceeb": "AKMSN",
    "59e6152586f77473dc057aa1": "VPO-136",
}
AKMP_RS = "5a0ed824fcdbcb0176308b0d"
AKM_SIGHT = "59d650cf86f7741b846413a4"


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
    assert proc.returncode == 0, "r1929_audit.js 失败：\n%s\n%s" % (proc.stdout[-1500:], proc.stderr[-1500:])
    with open(os.path.join(AUDIT, "engine-audit.json"), encoding="utf-8") as f:
        return json.load(f)


# ============================================================ 并列规则已作废
def test_parallel_rule_superseded(audit):
    """R19.21：并列规则（gwIsAkmpPairSlot）已移除，改为父件正上方同列。"""
    js = open(APP, encoding="utf-8").read()
    assert "gwIsAkmpPairSlot" not in js, "R19.20 并列规则必须移除"
    assert "gwIsAkmpSubSlot" in js and "GW_AKMP_PARENT_SIGHTS" in js
    assert "akmpPair" not in js, "并列落位逻辑必须移除"


def test_akm_family_single_slot_no_akmp(audit):
    """R19.21：AKM 系（AKM 照门 6P1 Sb.2-1 非 AKMP 父照门）单照门槽、无 AKMP。"""
    for gid, name in GUNS.items():
        assert audit["checks"]["F_akm_%s_single_sight_slot" % name], name
        assert audit["checks"]["F_akm_%s_no_akmp_anywhere" % name], name
        assert audit["checks"]["F_akm_%s_sight_record_kept" % name], name


def test_leaf_parent_guns_above_parent(audit):
    """R19.21：装三种标准照门的枪（AK-74N/AK-74/AK-105/AK-74M/AK-103/AK-104/AK-101/AK-102）
    AKMP 子槽在父照门正上方同列（自动与最终布局均成立）。"""
    for row in audit["detail"]["C"]:
        name = row["gun"]
        assert audit["checks"]["C_%s_auto_above_same_col" % name], (name, row["auto"])
        assert audit["checks"]["C_%s_final_above_same_col" % name], (name, row["final"])
        assert audit["checks"]["C_%s_parent_is_confirmed" % name], name


# ============================================================ 装卸 / 刷新场景（引擎级）
def test_conditional_generation(audit):
    """装/换/卸父照门：AKMP 子槽随真实父子关系出现与消失，无残留、无重复。"""
    for sc in ("uninstall", "install_6P1Sb2", "swap_to_akm_sight_unsupported",
               "swap_to_6P44", "swap_to_6P20"):
        assert audit["checks"]["B_%s_sub_presence" % sc], sc
        assert audit["checks"]["B_%s_single_sub_cell" % sc], sc
    assert audit["checks"]["B_no_residue_after_uninstall"] is True


def test_candidates_only_akmp(audit):
    """AKMP 子槽候选只含 AKMP；AKM 照门枪身槽候选不含 AKMP（不混淆）。"""
    assert audit["checks"]["B_install_6P1Sb2_candidate_only_akmp"] is True
    items = _items()
    for gid in GUNS:
        slot = [s for s in items[gid]["slots"] if s.get("sid") == "mod_sight_rear"][0]
        assert AKMP_RS not in (slot.get("allow") or []), gid


# ============================================================ 校准记录
def test_calib_user_adjustments_kept(audit):
    """用户 21:17 调整的坐标（AKM/AKMS 照门 r2c6 等）保持；语料 397 条 0 丢失。"""
    c = audit["detail"]["calib"]
    assert c["totalRecords"] == 397 and c["fallback"] == 0, c
    cal = _calib()
    for gid, name in GUNS.items():
        rec = cal["guns"][gid]["slots"]["mod_sight_rear|mod_sight_rear|"]
        assert rec is not None, name
    assert audit["checks"]["calib_revived_count_10"] is True
    assert audit["checks"]["calib_stale_count_5"] is True


def test_calib_parallel_era_records_stale_not_migrated():
    """并列时代记录（父件=AKM 照门）标失效、坐标留痕、不迁移其他槽位。"""
    c = _calib()
    hits = 0
    for gun in c["guns"].values():
        for key, rec in (gun.get("slots") or {}).items():
            if rec.get("ownerItemId") != AKM_SIGHT:
                continue
            hits += 1
            note = rec.get("note") or ""
            assert "R19.21" in note and "不再生效" in note and "不得迁移" in note, note
            assert rec.get("logicalRow") is not None
    assert hits == 5, hits


# ============================================================ 范围保护 / 版本
def test_scope_guards(audit):
    """VPO-209 现状保留；SVDS/SKS/GP-25 回归锚点不动。"""
    assert audit["checks"]["F_vpo209_sub_untouched"] is True
    assert audit["checks"]["F_vpo209_not_in_rule"] is True
    assert audit["checks"]["F_svds_dovetail_r2c7"] is True
    assert audit["checks"]["F_sks_socom_r4c3"] is True
    assert audit["checks"]["F_gp25_kept"] is True


def test_version_marker():
    js = open(APP, encoding="utf-8").read()
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1) >= "R19.21", m and m.group(1)
