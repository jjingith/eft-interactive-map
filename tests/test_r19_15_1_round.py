# -*- coding: utf-8 -*-
"""R19.15.1 槽位语义与布局专项：AXMC 上下机匣/后托、M10 镜座、马林 MXLR 击锤链与扳机、
AK 燕尾槽基座锚点、全量 163 把枪结构回归。

判定全部读真实槽位树 + 布局输出（node 探针），并用真实浏览器 DOM 审计 JSON 做交叉校验。
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
OUT = os.path.join(ROOT, "docs", "r19.15.1-layout-audit")
ASSERT_TOOL = os.path.join(ROOT, "tools", "r1921_assert.js")

pytestmark = pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]).returncode != 0,
    reason="需要 node")


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(["node", ASSERT_TOOL], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def _audit(name):
    return json.load(open(os.path.join(OUT, name), encoding="utf-8"))


# ------------------------------------------------------------------ 引擎规则
def test_engine_declares_visual_roles():
    js = _read(APP)
    for role in ("receiverUpper", "receiverLower", "stockOnGrip", "stockUnderParent",
                 "hammer", "hammerCap", "trigger", "lever", "topOptic", "dovetailMount"):
        assert '"%s"' % role in js, "缺少视觉角色：%s" % role
    # 判定必须基于真实槽位数据（sid/parent/allow/item pt），不得按枪名
    assert "function isDovetailMount(p)" in js and 'String(r.pt || "") === "Scope"' in js
    assert 'REC_BASE.test(baseOfPath(p)) && REC_BASE.test(baseOfPath(par))' in js
    assert 'function isStockBase(b)' in js
    # 主体行只放主体链；上置件的子槽继续向上
    assert "主体行只放主体链角色" in js
    assert "父件已经在第 1/2 行（上置光学链）时" in js


def test_version_marker_synced_to_r19_15_1():
    js = _read(APP)
    html = _read(os.path.join(ROOT, "index.html"))
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    for name in ("style.css", "theme-windows-xp.css", "app.js", "gun_builder.js", "combat_sim.js"):
        assert ("%s?v=" % name + m.group(1).lower()) in html, "%s 版本串未同步" % name


# ------------------------------------------------------------------ AXMC
def test_axmc_upper_lower_and_stock(probe):
    g = probe["guns"]["axmc"]
    assert probe["checks"]["axmcUpperLeftOfBody"], g
    assert probe["checks"]["axmcLowerBelowUpper"], g
    assert probe["checks"]["axmcStockAtAnchor"], g
    assert g["upper"] == {"r": 3, "c": 5}, g
    assert g["lower"] == {"r": 4, "c": 5}, g
    assert g["stock"] == {"r": 3, "c": 9}, g
    assert g["roles"]["receiverUpper"] and g["roles"]["receiverLower"]
    assert g["roles"]["stockOnGrip"], "后托槽真实父件是手枪式握把"


def test_axmc_audit_json_contract():
    d = _audit("axmc-layout-before-after.json")
    assert d["gun"]["id"] == "627e14b21713922ded6f2c15"
    assert d["before"]["receiverUpper"]["row"] == 4 and d["before"]["receiverUpper"]["col"] == 1
    assert d["after"]["receiverUpper"]["row"] == 3 and d["after"]["receiverUpper"]["col"] == 5
    assert d["after"]["receiverLower"]["row"] == 4 and d["after"]["receiverLower"]["col"] == 5
    assert d["after"]["stock"]["row"] == 3 and d["after"]["stock"]["col"] == 9
    assert d["parentRelationsPreserved"] is True


# ------------------------------------------------------------------ M10
def test_m10_mount_and_scope_above_body(probe):
    g = probe["guns"]["m10"]
    assert probe["checks"]["m10MountAboveBody"], g
    assert probe["checks"]["m10ScopeAboveMount"], g
    assert g["mount"] == {"r": 2, "c": 5}, g
    assert g["scope"] == {"r": 1, "c": 5}, g


def test_m10_audit_json_before_was_below_body():
    d = _audit("m10-mount-before-after.json")
    assert d["gun"]["id"] == "673cab3e03c6a20581028bc1"
    assert d["before"]["mount"]["row"] == 4, "修复前镜座在本体行下方"
    assert d["before"]["scope"]["row"] == 5, "修复前瞄具子槽更低"
    assert d["after"]["mount"]["row"] == 2 and d["after"]["scope"]["row"] == 1


# ------------------------------------------------------------------ 马林 MXLR
def test_marlin_hammer_chain(probe):
    g = probe["guns"]["marlin"]
    assert probe["checks"]["marlinHammerAboveStock"], g
    assert probe["checks"]["marlinCapAboveHammer"], g
    assert probe["checks"]["marlinChainSameColumn"], g
    assert g["hammer"] == {"r": 2, "c": 9}, g
    assert g["cap"] == {"r": 1, "c": 9}, g
    assert g["stock"] == {"r": 3, "c": 9}, g


def test_marlin_trigger_at_r4c8_and_no_fake_charge(probe):
    g = probe["guns"]["marlin"]
    assert probe["checks"]["marlinTriggerAtR4C8"], g
    assert g["trigger"] == {"r": 4, "c": 8}, g
    # 真实环状杠杆让出第 9 列上方给击锤链，改锚到枪托正下方
    assert g["lever"] == {"r": 4, "c": 9}, g
    assert probe["checks"]["marlinNoFakeChargeAtR2C9"], g


def test_marlin_audit_json_contract():
    d = _audit("marlin-mxlr-layout.json")
    assert d["gun"]["id"] == "67c6de3ce39861860909e8e5"
    chk = d["checks"]
    for k in ("hammerAboveStock", "hammerCapAboveHammer", "hammerChainSameColumn",
              "triggerAtR4C8", "noPhantomCards"):
        assert chk[k] is True, k
    assert d["after"]["hammer"]["row"] == 2 and d["after"]["hammer"]["col"] == 9
    assert d["after"]["hammerCap"]["row"] == 1 and d["after"]["hammerCap"]["col"] == 9
    assert d["after"]["trigger"]["row"] == 4 and d["after"]["trigger"]["col"] == 8
    # 真实父子链没被改：击锤帽仍是击锤槽的真实子槽
    assert "mod_hammer/mod_tactical" in d["after"]["hammerCap"]["slot"]


# ------------------------------------------------------------------ AK 燕尾槽
def test_dovetail_fixed_anchor_r2c8(probe):
    """R19.15.3：燕尾槽基座固定在 r2c8（R19.15.2 的 r2c3 已被用户明确纠正，不再生效）。
    R19.18 升级：SVDS 按用户指定固定在 r2c7，其余枪械仍必须是 r2c8 —— 两处都要成立。"""
    d = probe["guns"]["dovetail"]
    assert d["guns"] > 0 and d["cells"] > 0, d
    assert probe["checks"]["dovetailPrimaryAtR2C8"], d
    assert d["onFixedAnchor"] + d["svdsAtR2C7"] == d["guns"], d
    assert probe["checks"]["dovetailSvdsAtR2C7"], "SVDS 的燕尾槽必须落在用户指定的 r2c7"
    for s in d["sample"]:
        if s["primary"]:
            if "SVDS" in (s.get("gun") or ""):
                assert s["col"] == 7 and s["row"] == 2, s
            else:
                assert s["col"] == 8 and s["row"] == 2, s
        else:
            assert s["col"] != 8, "第二个燕尾槽接口不得占用主锚点：%s" % s


def test_dovetail_rear_sight_band_c6_c7(probe):
    """兼容燕尾槽的枪械：第一个照门槽 r2c6，第二个真实照门相关槽位 r2c7。"""
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailRearSightAtC6"], d
    assert probe["checks"]["dovetailSecondRearSightAtC7"], d
    assert d["rearSightBad"] == 0, d


def test_dovetail_front_sight_still_above_muzzle(probe):
    """前照门仍必须位于真实枪口槽正上方（不因燕尾槽规则移动）。"""
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailFrontSightAboveMuzzle"], d
    assert d["frontSightAligned"] == d["frontSightChecked"], d


def test_dovetail_optic_above_same_column(probe):
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailOpticAboveSameCol"], d
    assert d["opticAbove"] == d["opticTotal"], d
    for s in d["sample"]:
        if s["optic"]:
            assert s["optic"]["c"] == s["col"], s
            assert s["optic"]["r"] == s["row"] - 1, s


def test_dovetail_side_slots_right_of_optic(probe):
    d = probe["guns"]["dovetail"]
    assert probe["checks"]["dovetailSideRightOfOptic"], d
    assert d["sideRight"] == d["sideTotal"], d
    for s in d["sample"]:
        for side in s["sides"]:
            assert side["c"] > s["col"], s


# ------------------------------------------------------------------ 全量回归
def test_all_guns_structurally_clean(probe):
    d = probe["guns"]["all"]
    assert d["total"] >= 160, d["total"]
    assert d["clean"] == d["total"], d["bad"][:5]
    assert probe["checks"]["allGunsClean"]


def test_all_gun_audit_covers_every_gun():
    d = _audit("all-gun-layout-audit.json")
    assert d["scanned"] >= 160
    assert len(d["guns"]) == d["scanned"]
    s = d["summary"]
    for k in ("domTreeMismatch", "domCoordMismatch", "duplicatePath", "overlapCell",
              "outOfGrid", "zeroRow", "mainRowViolation", "opticBelowBody", "stockOffCol9",
              "receiverPairViolation", "hammerChainViolation", "triggerViolation",
              "dovetailNotAboveBody"):
        assert s[k] == 0, "%s = %s" % (k, s[k])
    assert not d["anomalies"], d["anomalies"][:3]


def test_338_inventory_three_guns():
    d = _audit("338-gun-inventory.json")
    ids = {g["id"] for g in d["guns"]}
    assert ids == {"5fc22d7c187fea44d52eda44", "627e14b21713922ded6f2c15", "673cab3e03c6a20581028bc1"}
    for g in d["guns"]:
        assert g["audited"] is True, g
        assert not g["problems"], g
