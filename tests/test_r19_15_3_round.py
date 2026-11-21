# -*- coding: utf-8 -*-
"""R19.15.3 专项：AK 燕尾槽 r2c8 体系、照门带 r2c6/r2c7、全量复核。

硬性验收（用户指定坐标，不得由自动布局改写）：
    照门带：r2c6（第一个真实照门槽）→ r2c7（第二个真实照门相关槽位）
    燕尾槽：r2c8 → 瞄具槽 r1c8（正上方同列）→ 额外配件槽 r1c9（瞄具右侧）
    前照门：真实枪口槽正上方（不变）
    非燕尾槽枪械：照门仍 r2c8、拉机柄 r2c9（不受本规则影响）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
OUT = os.path.join(ROOT, "docs", "r19.15.3-layout-audit")
ASSERT_TOOL = os.path.join(ROOT, "tools", "r1921_assert.js")


def _json(name):
    return json.load(open(os.path.join(OUT, name), encoding="utf-8"))


pytestmark = pytest.mark.skipif(
    subprocess.run([sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]).returncode != 0,
    reason="需要 node")


@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(["node", ASSERT_TOOL], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=900)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


# 1 基座固定在 r2c8
def test_01_mount_fixed_at_r2c8(probe):
    """R19.18 升级：主锚点仍是 r2c8；SVDS 按用户指定固定在 r2c7（唯一例外）。"""
    d = probe["guns"]["dovetail"]
    assert d["guns"] >= 20, d
    assert d["onFixedAnchor"] + d["svdsAtR2C7"] == d["guns"], d
    assert probe["checks"]["dovetailPrimaryAtR2C8"]
    assert probe["checks"]["dovetailSvdsAtR2C7"]


# 2 只对真实兼容的枪械生效（判定依据 = 真实 allow 里直接列着 pt=Scope 的侧轨基座）
def test_02_rule_only_on_true_dovetail_guns():
    d = _json("ak-dovetail-final.json")
    assert d["compatibleGuns"], d
    for g in d["compatibleGuns"]:
        prim = [m for m in g["mounts"] if m["primary"]][0]
        assert prim["allowScopeIds"], "%s 的基座 allow 里没有光学瞄具，不应套用燕尾槽规则" % g["gun"]
        assert prim["slotId"].startswith("mod_mount"), (g["gun"], prim["slotId"])
    # 非燕尾槽枪械不得出现 dovetailMount 角色
    sight = _json("ak-dovetail-sight-layout.json")
    non_dv = {g["id"] for g in sight["nonDovetailSample"]}
    dv = {g["gunId"] for g in d["compatibleGuns"]}
    assert not (non_dv & dv), "同一把枪不能同时被记为燕尾槽与非燕尾槽"


# 3 照门带 r2c6 / r2c7
def test_03_rear_sight_band(probe):
    d = probe["guns"]["dovetail"]
    assert d["rearSightAtC6"] == d["rearSightGuns"], d
    assert d["secondRearSightAtC7"] == d["secondRearSightTotal"], d
    assert d["rearSightBad"] == 0, d
    assert probe["checks"]["dovetailRearSightAtC6"]
    assert probe["checks"]["dovetailSecondRearSightAtC7"]


# 4 不具备燕尾槽的枪械照门位置：非 AK 照门系仍 r2c8；AK 照门系按 R19.28 需求一锚定 r2c6
#   R19.29 任务D：静态产物已用 tools/r1923_audit.js 重新生成（与当前引擎一致），
#   此处按结构签名 akRearFamily 区分，保留「非 AK 非燕尾槽枪械仍 r2c8」的原保护目的。
def test_04_non_dovetail_rear_sight_untouched():
    d = _json("ak-dovetail-sight-layout.json")
    checked = 0
    non_ak = 0
    for g in d["nonDovetailSample"]:
        if not g["rearSight"]:
            continue
        checked += 1
        assert g["rearSight"]["row"] == 2, g
        if g.get("akRearFamily"):
            # R19.28 需求一：AK 照门系（结构签名，不看枪名）统一锚定 r2c6
            assert g["rearSight"]["col"] == 6, g
        else:
            # 其余非燕尾槽枪械仍 r2c8（原测试的实际保护目的，保持不变）
            assert g["rearSight"]["col"] == 8, g
            non_ak += 1
    assert checked >= 3, d["nonDovetailSample"]
    assert non_ak >= 3, "非 AK 非燕尾槽枪械样本不足，无法验证 r2c8 不变量"


# 5 前照门仍在枪口正上方
def test_05_front_sight_above_muzzle(probe):
    d = probe["guns"]["dovetail"]
    assert d["frontSightAligned"] == d["frontSightChecked"], d
    assert probe["checks"]["dovetailFrontSightAboveMuzzle"]
    sight = _json("ak-dovetail-sight-layout.json")
    assert sight["summary"]["frontSightAligned"] == sight["summary"]["frontSightChecked"]
    for g in sight["nonDovetailSample"]:
        assert g["frontSightAligned"] is True, g


# 6 光学槽在基座正上方、同一列
def test_06_optic_above_mount_same_column(probe):
    d = probe["guns"]["dovetail"]
    assert d["opticAbove"] == d["opticTotal"], d
    chain = _json("ak-dovetail-optic-chain.json")
    assert chain["summary"]["sameColumn"] == chain["summary"]["gunsWithOpticSlot"]
    assert chain["summary"]["childAbove"] == chain["summary"]["gunsWithOpticSlot"]


# 7 额外真实配件槽在光学槽右侧
def test_07_side_slots_right_of_optic(probe):
    d = probe["guns"]["dovetail"]
    assert d["sideRight"] == d["sideTotal"], d
    chain = _json("ak-dovetail-optic-chain.json")
    for g in chain["guns"]:
        for s in g.get("sides", []):
            if s.get("rightOfOptic") is not None:
                assert s["rightOfOptic"] is True, (g["gun"], s)


# 8 空坐标不渲染、真实空槽可交互（真实浏览器）
def test_08_phantom_cells_and_real_empty_slots():
    d = _json("browser-check.json")
    for key in ("ak74n", "akm", "saiga"):
        b = d["guns"][key]
        assert b["phantomCount"] == 0, (key, b["phantoms"][:3])
        assert b["realEmptySlots"] > 0, key
        assert b["emptySlotInteractive"] is True, key
        assert b["rows"] >= 6, key
        assert all(h > 20 for h in b["rowHeights"]), (key, b["rowHeights"])


# 9 安装 / 卸载 / 切换枪械 / 预设 / 顶部扩展后布局仍正确
def test_09_flow_stability():
    d = _json("browser-check.json")
    flow = d["flow"]
    for step in ("akBase", "akOpticInstalled", "akOpticRemoved"):
        b = flow[step]
        assert b["mountRow"] == b["bodyRow"] - 1 and b["mountCol"] == 8, (step, b)
        assert b["rearSightCol"] == 6, (step, b)
        if b.get("optic"):
            assert b["optic"]["col"] == 8, (step, b["optic"])
            assert b["optic"]["row"] == b["mountRow"] - 1, (step, b["optic"])
    assert flow["afterOpticInstall"]["rows"] >= flow["akBase"]["rows"]
    assert flow["akOpticRemoved"]["rows"] == flow["akBase"]["rows"], flow


# 10 Nightforce 仍恰好两个直接槽位
def test_10_nightforce_two_direct_slots():
    d = _json("optic-slot-audit-final.json")
    nf = d["nightforce"]
    assert nf["declared"] == 2 and nf["tree"] == 2 and nf["layout"] == 2, nf


# 11 全量审计没有被放宽：163 把枪、结构 + 需求符合性双通过
def test_11_full_audit_not_loosened():
    d = _json("all-gun-layout-audit.json")
    assert d["scanned"] >= 163, d["scanned"]
    s = d["summary"]
    for k in ("domTreeMismatch", "domCoordMismatch", "duplicatePath", "overlapCell", "outOfGrid",
              "zeroRow", "mainRowViolation", "stockOffCol9",
              "receiverPairViolation", "hammerChainViolation", "triggerViolation",
              "dovetailOffAnchor", "dovetailOpticOffColumn", "dovetailSideMisplaced",
              "dovetailRearSightBand", "dovetailFrontSightOffMuzzle"):
        assert s[k] == 0, "%s=%s" % (k, s[k])
    assert not d["anomalies"], d["anomalies"][:3]
    # 每个枪械都必须有「需求符合性」明细，不能只统计结构
    for g in d["guns"]:
        assert "dovetail" in g, g["gun"]
        assert "rearSightBand" in g, g["gun"]
        assert "dovetailFrontSight" in g, g["gun"]


# 12 R19.15 视觉与既有功能回归
def test_12_r19_15_visual_and_feature_regression():
    d = _json("regression-results.json")
    assert d["testSuite"]["failed"] == 0, d["testSuite"]
    assert d["visual"]["buttonHoverOrange"] is True
    assert d["visual"]["connectorLines"] == 0
    assert d["visual"]["skinVisible"] is False
    assert d["features"]["optimizerConflictFree"] is True
    assert d["features"]["magCapacity100"] is True
    assert d["features"]["nightforceTwoSlots"] is True
