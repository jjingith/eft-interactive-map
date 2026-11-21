# -*- coding: utf-8 -*-
"""R19.15.2 专项（已被 R19.15.3 的坐标纠正取代，断言同步升级为 r2c8 体系）。

历史：R19.15.2 曾把燕尾槽基座放在 r2c3 / 瞄具 r1c3 / 额外槽 r1c4。
用户在 R19.15.3 明确纠正为：
    照门带 r2c6（第一个真实照门槽）→ r2c7（第二个真实照门相关槽位）
    燕尾槽基座 r2c8 → 瞄具槽 r1c8（正上方同列）→ 额外配件槽 r1c9（瞄具右侧）
本文件保留原有测试结构，断言改为新坐标，并继续要求「真实槽位树 + 布局输出 + DOM」三方一致。
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
OUT = os.path.join(ROOT, "docs", "r19.15.3-layout-audit")
ASSERT_TOOL = os.path.join(ROOT, "tools", "r1921_assert.js")

pytestmark = pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]).returncode != 0,
    reason="需要 node")


def _json(name):
    return json.load(open(os.path.join(OUT, name), encoding="utf-8"))


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(["node", ASSERT_TOOL], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=900)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- 引擎实现
def test_engine_reserves_fixed_anchors():
    js = open(APP, encoding="utf-8").read()
    assert 'reserve({ row: 2, col: 8 });' in js, "基座固定锚点必须预留 r2c8"
    assert 'reserve({ row: 1, col: 8 });' in js, "瞄具槽固定锚点必须预留 r1c8"
    assert 'reserve({ row: 1, col: 9 });' in js, "额外配件槽固定锚点必须预留 r1c9"
    assert 'reserve({ row: 2, col: 6 });' in js, "照门带第一个槽必须预留 r2c6"
    assert 'reserve({ row: 2, col: 7 });' in js, "照门带第二个槽必须预留 r2c7"
    assert 'fixedAnchor: di === 0 ? "r2c8"' in js
    # 旧的「按该行真实槽位序号取第 3 位」实现必须已移除
    assert "row2Ordinal" not in js
    assert "placeDovetailMounts" not in js
    # R19.15.2 的 r2c3 燕尾槽锚点不得复活（r2c3 仍可作为通用第二行预留格存在，
    # 但不得再被当作燕尾槽基座锚点）
    assert 'fixedAnchor: di === 0 ? "r2c3"' not in js
    assert "dovetailMount" in js and '"r2c8"' in js


def test_version_marker_current():
    js = open(APP, encoding="utf-8").read()
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    for name in ("style.css", "theme-windows-xp.css", "app.js", "gun_builder.js", "combat_sim.js"):
        assert ("%s?v=" % name + m.group(1).lower()) in html, "%s 版本串未同步" % name


# ---------------------------------------------------------------- 硬性坐标
def test_mount_primary_on_r2c8_for_all_compatible_guns(probe):
    d = probe["guns"]["dovetail"]
    assert d["guns"] >= 20, d
    assert probe["checks"]["dovetailPrimaryAtR2C8"], d
    # R19.18：SVDS 是用户指定的例外（r2c7），其余全部必须落在 r2c8
    assert d["onFixedAnchor"] + d["svdsAtR2C7"] == d["guns"], \
        "%d + %d（SVDS 例外）!= %d" % (d["onFixedAnchor"], d["svdsAtR2C7"], d["guns"])
    assert probe["checks"]["dovetailSvdsAtR2C7"], "SVDS 燕尾槽必须落在 r2c7"
    for s in d["sample"]:
        if s["primary"]:
            if "SVDS" in (s.get("gun") or ""):
                assert s["col"] == 7 and s["row"] == 2, s
            else:
                assert s["col"] == 8 and s["row"] == 2, s
        else:
            assert s["col"] != 8, "同一把枪的第二个燕尾槽接口不得占用主锚点：%s" % s


def test_optic_slot_directly_above_mount(probe):
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailOpticAboveSameCol"], d
    for s in d["sample"]:
        if s["optic"]:
            assert s["optic"]["c"] == s["col"], s
            assert s["optic"]["r"] == s["row"] - 1, s


def test_side_slots_right_of_optic_column(probe):
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailSideRightOfOptic"], d
    for s in d["sample"]:
        for side in s["sides"]:
            assert side["c"] == s["col"] + 1, s
            assert side["r"] == s["row"] - 1, s


# ---------------------------------------------------------------- 审计物料
def test_ak_dovetail_final_contract():
    d = _json("ak-dovetail-final.json")
    assert d["rule"]["dovetailMount"].startswith("r2c8")
    assert d["rule"]["opticSlot"].startswith("r1c8")
    assert d["rule"]["sideSlot"].startswith("r1c9")
    assert d["rule"]["rearSight1"].startswith("r2c6")
    assert d["rule"]["rearSight2"].startswith("r2c7")
    s = d["summary"]
    assert s["guns"] >= 20 and s["mountSlots"] >= s["guns"]
    assert s["primaryOnR2C8"] == s["guns"], s
    assert not s["domMismatch"], s["domMismatch"][:3]
    assert s["domChecked"] == s["mountSlots"], "每个基座槽位都必须有 DOM 对照"
    for g in d["compatibleGuns"]:
        prim = [m for m in g["mounts"] if m["primary"]]
        assert prim, g["gun"]
        m = prim[0]
        assert m["actualRow"] == g["bodyRow"] - 1, (g["gun"], m)
        assert m["actualCol"] == 8, (g["gun"], m)
        assert m["dom"]["row"] == m["actualRow"] and m["dom"]["col"] == m["actualCol"], (g["gun"], m)


def test_ak_dovetail_optic_chain_contract():
    d = _json("ak-dovetail-optic-chain.json")
    assert d["summary"]["mismatches"] == []
    for g in d["guns"]:
        if g["optic"]:
            assert g["optic"]["sameColumn"] is True, (g["gun"], g["optic"])
            assert g["optic"]["directlyAbove"] is True, (g["gun"], g["optic"])
        for c in g["chain"]:
            assert c["col"] == g["base"]["col"], (g["gun"], c)


def test_ak_dovetail_sight_band_contract():
    d = _json("ak-dovetail-sight-layout.json")
    assert d["summary"]["rearSightAtC6"] == d["summary"]["withRearSight"]
    assert d["summary"]["secondAtC7"] <= d["summary"]["withRearSight"]
    assert d["summary"]["frontSightAligned"] == d["summary"]["frontSightChecked"]
    assert not d["summary"]["violations"], d["summary"]["violations"][:3]


def test_layout_conflicts_have_no_blocking_items():
    d = _json("layout-conflicts.json")
    assert d["blocking"] == [], d["blocking"][:3]
    assert d["userFixedAnchors"]["r2c8"].startswith("AK 燕尾槽基座")
    # 第二个真实燕尾槽接口必须被显式记录，而不是被合并或隐藏
    kinds = {c["kind"] for c in d["conflicts"]}
    assert "second-dovetail-interface" in kinds


def test_full_audit_clean_and_dovetail_zero():
    d = _json("all-gun-layout-audit.json")
    s = d["summary"]
    for k in ("domTreeMismatch", "domCoordMismatch", "duplicatePath", "overlapCell", "outOfGrid",
              "zeroRow", "mainRowViolation", "stockOffCol9",
              "receiverPairViolation", "hammerChainViolation", "triggerViolation",
              "dovetailOffAnchor", "dovetailOpticOffColumn", "dovetailSideMisplaced",
              "dovetailRearSightBand", "dovetailFrontSightOffMuzzle"):
        assert s[k] == 0, "%s=%s" % (k, s[k])
    assert not d["anomalies"], d["anomalies"][:3]
