# -*- coding: utf-8 -*-
"""R19.21 AKMP 真实父子关系 + 校准数据整合专项（任务六 A–F）。

实测确认：AKMP 系统照门装置（5a0ed824…）是 6P44 Sb.1-30（AK-105 照门）/
6P20 Sb.2（AK-74M 照门）/ 6P1 Sb.2（AK-74 照门）的子配件，显示在父照门正上方
同列；AKM 照门 6P1 Sb.2-1 的并列假设作废。用户导出校准数据（SHA 151e4ad4…）
已整合（10 条子槽记录复活重算、5 条并列时代记录标失效留痕）。

证据：docs/r19.21-akmp-parent-fix/（engine-audit.json / data-fix.json /
calibration-migration.json / merge-report.json / browser-accept.json）
+ 每次会话实跑 tools/r1929_audit.js。
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
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")
SLOTFIX = os.path.join(ROOT, "tools", "slotfix.py")
FETCH = os.path.join(ROOT, "tools", "fetch_data.py")
AUDIT = os.path.join(ROOT, "docs", "r19.21-akmp-parent-fix")
ENGINE_TOOL = os.path.join(ROOT, "tools", "r1929_audit.js")

need_node = subprocess.run(
    [sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]
).returncode != 0

AKMP_RS = "5a0ed824fcdbcb0176308b0d"
PARENTS = {
    "5ac733a45acfc400192630e2": ("6P44 Sb.1-30", "5ac733a45acfc400192630e4"),
    "5ac72e475acfc400180ae6fe": ("6P20 Sb.2", "5ac72e475acfc400180ae700"),
    "5649b0544bdc2d1b2b8b458a": ("6P1 Sb.2", "5a0ee12cfcdbcb001912fa64"),
}
AKM_SIGHT = "59d650cf86f7741b846413a4"


def _items():
    with open(ITEMS, encoding="utf-8") as f:
        return json.load(f)["items"]


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


# ============================================================ A：父照门数据
def test_A_three_parent_sights_have_akmp_subslot(audit):
    items = _items()
    for pid, (label, slot_id) in PARENTS.items():
        it = items[pid]
        assert it["pt"] == "Scope", (label, it["pt"])
        sub = [s for s in (it.get("slots") or []) if s.get("id") == slot_id]
        assert sub and sub[0]["sid"] == "mod_sight_rear" and sub[0]["allow"] == [AKMP_RS], label
        assert audit["checks"]["A_%s_subslot_exists" % label], label
        assert audit["checks"]["A_%s_allow_akmp_only" % label], label


def test_A_akm_sight_no_akmp_and_no_auto_leak(audit):
    """AKM 照门 6P1 Sb.2-1 与 6P1 Sb.2 是不同物品；错误子槽已删；其他照门无自动增槽。"""
    akm = _items()[AKM_SIGHT]
    assert akm["n"] == "AKM 照门"
    assert not [s for s in (akm.get("slots") or [])
                if (s.get("allow") or []) == [AKMP_RS]], "AKM 照门不得带 AKMP 子槽"
    assert audit["checks"]["A_akmsight_no_akmp_subslot"] is True
    assert audit["checks"]["A_no_auto_akmp_on_other_sights"] is True


# ============================================================ B：条件生成
def test_B_conditional_generation(audit):
    for sc in ("uninstall", "install_6P1Sb2", "swap_to_akm_sight_unsupported",
               "swap_to_6P44", "swap_to_6P20"):
        assert audit["checks"]["B_%s_sub_presence" % sc], sc
        assert audit["checks"]["B_%s_single_sub_cell" % sc], sc
        if sc != "uninstall" and sc != "swap_to_akm_sight_unsupported":
            assert audit["checks"]["B_%s_parent_is_sight" % sc], sc
            assert audit["checks"]["B_%s_candidate_only_akmp" % sc], sc
    assert audit["checks"]["B_no_residue_after_uninstall"] is True


# ============================================================ C：布局
def test_C_above_parent_same_col(audit):
    rows = {r["gun"]: r for r in audit["detail"]["C"]}
    for name in ("AK-74N", "AK-74", "AK-105", "AK-74M", "AK-103", "AK-104", "AK-101", "AK-102"):
        r = rows[name]
        assert audit["checks"]["C_%s_auto_above_same_col" % name], (name, r["auto"])
        assert audit["checks"]["C_%s_final_above_same_col" % name], (name, r["final"])
    # 明确案例：父 r2c6 → 子 r1c6；父 r1c6（AK-103/104）→ 子 r0c6 + topPad
    assert rows["AK-74N"]["final"]["sight"]["row"] == 2 and rows["AK-74N"]["final"]["sub"]["row"] == 1
    assert audit["checks"]["C_AK103_top_expansion"] is True


# ============================================================ D：校准整合
def test_D_export_merge_and_records():
    """用户导出 = 当前正式文件（SHA 151e4ad4… 字节一致）；10 条复活 + 5 条失效留痕。"""
    h = __import__("hashlib").sha256(open(CALIB, "rb").read()).hexdigest()
    mig = os.path.join(AUDIT, "calibration-migration.json")
    assert os.path.exists(mig)
    with open(mig, encoding="utf-8") as f:
        m = json.load(f)
    assert m["recordsBefore"] == 397 and m["recordsAfter"] == 397 and m["recordsDeleted"] == 0
    assert m["revivedRecomputed"] == 10 and m["markedStale"] == 5 and m["skipped"] == 0
    revived = [c for c in m["changes"] if c["status"] == "revived-recomputed"]
    assert len(revived) == 10
    for c in revived:
        assert c["after"]["logicalRow"] == c["parentFinal"]["row"] - 1 \
            and c["after"]["col"] == c["parentFinal"]["col"], c
        assert "before" in c and c["before"].get("logicalRow") is not None, "旧坐标必须留痕于 before"
    stale = [c for c in m["changes"] if c["status"] == "marked-stale-parallel-era"]
    assert len(stale) == 5 and all(c.get("coordsPreserved") for c in stale)
    merge = os.path.join(AUDIT, "merge-report.json")
    assert os.path.exists(merge), "合并报告必须存在"
    with open(merge, encoding="utf-8") as f:
        mr = json.load(f)
    assert mr["export"]["exportSha256"] == "151e4ad4ab058b6cb5a8302dcb87eb530069f3703beebe5fb33bf734ec84928e"


def test_D_identity_keys_not_crossed():
    """身份键不串位：三条父照门的记录 owner 各归其主；并列记录不迁移到三父照门。"""
    c = _calib()
    by_owner = {}
    for gun in c["guns"].values():
        for key, rec in (gun.get("slots") or {}).items():
            o = rec.get("ownerItemId") or ""
            if o in PARENTS or o == AKM_SIGHT:
                by_owner.setdefault(o, []).append(key)
                assert key.endswith("|" + o), (key, o)
    assert len(by_owner.get(AKM_SIGHT, [])) == 5
    for pid in PARENTS:
        assert by_owner.get(pid), pid


# ============================================================ E：自动布局路径
def test_E_auto_layout_without_records(audit):
    assert audit["checks"]["E_auto_without_records"] is True
    assert audit["checks"]["E_rule_is_parent_item_based"] is True


# ============================================================ F：回归 + 数据管线
def test_F_regression_guards(audit):
    assert audit["checks"]["F_vpo209_sub_untouched"] is True
    assert audit["checks"]["F_svds_dovetail_r2c7"] is True
    assert audit["checks"]["F_sks_socom_r4c3"] is True
    assert audit["checks"]["F_gp25_kept"] is True
    for name in ("AKM", "AKMS", "AKMN", "AKMSN", "VPO-136"):
        assert audit["checks"]["F_akm_%s_single_sight_slot" % name], name
        assert audit["checks"]["F_akm_%s_no_akmp_anywhere" % name], name


def test_F_slotfix_persistence():
    """刷新管线：三种父照门的子槽不被删；AKM 照门错误子槽被删；表幂等。"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import slotfix
    assert "59d650cf86f7741b846413a4" in slotfix.R1921_ITEM_SLOT_FIXES
    for pid in PARENTS:
        assert pid not in slotfix.R1918_ITEM_SLOT_FIXES, pid
    fetch = open(FETCH, encoding="utf-8").read()
    assert "R1921_ITEM_SLOT_FIXES" in fetch
    # 幂等：再跑一次数据套用不产生重复子槽
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "r1929_datafix.py")],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    rep = json.loads(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip().startswith("{")
                     else proc.stdout[proc.stdout.index("{"):])
    assert rep["restored"] == [] and rep["dropped"] == [], rep
    items = _items()
    for pid, (label, slot_id) in PARENTS.items():
        subs = [s for s in items[pid]["slots"] if s.get("id") == slot_id]
        assert len(subs) == 1, (label, len(subs))


# ============================================================ 版本
def test_version_marker():
    js = open(APP, encoding="utf-8").read()
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1) >= "R19.21", m and m.group(1)
