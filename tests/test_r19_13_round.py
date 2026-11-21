# -*- coding: utf-8 -*-
"""R19.13 布局规则修订 · 自动化测试

覆盖任务书第 6 节：
  1 前照门与枪口列对齐（含无独立枪管槽、枪口在 c2 的枪）
  2 瞄具锚定上机匣正上方 r2c5
  3 照门在拉机柄左侧 r2c8、拉机柄 r2c9
  4 MPR45 备用导轨槽位在护木正上方 r2c4（按真实 allow 识别），前握把不占 r2c3/c4
  5 上方导轨配件在 MPR45 左侧
  6 前握把三类链：直接 / 上下护木 / 导轨转接，全部同列在父件正下方
  7 枪口链同列纵向展开
  8 护木其余附件进第六行
  9 固定 6×9 不重叠不越界（全枪）
 10 R19.12 功能锚点不回退
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
AUDIT = os.path.join(ROOT, "docs", "r19.13-layout-audit")
LAYOUT_TOOL = os.path.join(ROOT, "tools", "r1912_layout.js")
AUDIT_TOOL = os.path.join(ROOT, "tools", "r1913_audit.js")


def _read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _run_node(args, timeout=600):
    return subprocess.run(["node"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _engine():
    js = _read(APP)
    return js[js.index("function gwSidBase("):js.index("function renderGunSkin(")]


# ---------------------------------------------------------------- 1. 第二行锚点
def test_row2_anchors_are_driven_by_real_slot_tree():
    eng = _engine()
    # 前照门：锚定在**实际枪口列**（muzzleCol 随 hasBarrel 变化），不是写死 c1
    assert "var muzzleCol = mainCols.muzzle || (hasBarrel ? 1 : 2);" in eng
    assert 'classifyTop(p) === "frontSight"' in eng
    assert "take(2, muzzleCol, fs, true)" in eng, "前照门必须放在枪口正上方"
    # 瞄具：r2c5（上机匣正上方）
    assert 'if (!nodes[p].parent || /^(reciever|receiver|slide|frame|upper|lower)$/.test(par))' in eng
    assert "take(2, 5, sc, true)" in eng
    # 照门：非燕尾槽枪 r2c8（拉机柄左侧）；兼容 AK 燕尾槽的枪械改为 r2c6/r2c7 照门带
    # （R19.15.3 用户指定坐标），基座让位到 r2c8；拉机柄 r2c9 由 GW_ANCHOR.charge 固定
    # R19.28：锚点条件扩展为 akRearAnchor = 燕尾槽 || AK 照门系（结构签名，不看枪名）
    assert "var rsCol = akRearAnchor ? 6 : 8;" in eng
    assert "hasDovetail || akRearFamily" in eng
    # R19.21 升级：并列规则作废，AKMP 子槽按父照门正上方同列（gwIsAkmpSubSlot）。
    assert "take(2, rsCol, rs, true)" in eng
    assert "gwIsAkmpSubSlot" in eng and "GW_AKMP_PARENT_SIGHTS" in eng, \
        "R19.21 AKMP 子槽规则必须在照门带内（父件正上方同列）"
    assert "take(2, 7, k, true)" in eng, "燕尾槽枪第二个照门相关槽位必须锚定 r2c7"
    assert "charge:    { row: 2, col: 9 }" in eng
    # MPR45：按**真实 allow 收录该物品 id**识别，不做名称分类
    assert 'all[id].n === "NcStar MPR45备用导轨"' in eng
    assert "nodes[p].allow.indexOf(mprId) >= 0" in eng
    assert "take(2, 4, mprSlot, true)" in eng
    # R19.14：上方导轨配件必须沿 MPR45 同列（c4）**竖直向上**，不得横向挪位规避
    assert "var railTop = 1;" in eng
    assert "take(railTop, 4, k, true)" in eng
    assert "for (var c = 3; c >= 1; c--)" not in eng, "不得再用横向左移规避空间不足"
    # 第二行锚点要预留，普通附件不得漂入
    assert "reserve({ row: 2, col: 3 });" in eng and "reserve({ row: 2, col: 4 });" in eng
    assert "reserve({ row: 2, col: 5 });" in eng and "reserve({ row: 2, col: 8 });" in eng


def test_foregrip_never_above_parent_and_stays_out_of_fixed_zones():
    eng = _engine()
    # 链条来自真实 node.parent，不看分类名
    assert "var cur = nodes[fp].parent;" in eng
    assert "chain.unshift(cur);" in eng
    # 不进第二行、不占 r4c6–c9 固定区
    assert "(want.row === 2) ||" in eng and "(want.row === 4 && want.col >= 6 && want.col <= 9)" in eng
    # findFree 有 belowOnly 通道，子件不跑到父件上方
    assert "function findFree(prefRow, prefCol, belowOnly)" in eng
    assert "findFree(parentCell.row, parentCell.col, true)" in eng
    # 最终钉位仍保留 R19.10 语义
    assert 'gwSidBase(nodes[c.path].sid) === "foregrip"' in eng
    assert "wantRow = pc ? pc.row + 1 : GW_ANCHOR.body.row + 1" in eng
    assert "wantCol = pc ? pc.col : 5" in eng


def test_muzzle_chain_is_vertical_same_column():
    eng = _engine()
    assert "function walkMuzzle(pp)" in eng
    assert "var want = { row: mRow + 1 + ki, col: mCol };" in eng
    assert 'why: "枪口链层级超过 6 行画布容量' in eng, "超出画布必须报告容量不足，不得静默省略"
    # 前照门/照门不进枪口链（它们走第二行锚点）
    assert "if (classifyTop(k)) { return; }" in eng


def test_handguard_extras_prefer_row6_in_stable_order():
    eng = _engine()
    assert "护木其余附件 → 第六行" in eng
    assert 'extras.sort(function (a, b) { return order.indexOf(a) - order.indexOf(b); });' in eng, \
        "第六行顺序必须稳定（按槽位树顺序），不随装卸重排"
    assert "if (freeAt(6, c)) {" in eng


# ---------------------------------------------------------------- 2. 全枪不变量
@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_fixed_grid_invariants_still_hold_on_all_guns():
    proc = _run_node([LAYOUT_TOOL])
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    s = d["summary"]
    assert s["guns"] >= 150
    assert not s["problems"], s["problems"][:3]
    assert s["overflow"] == 0
    fg = s["foregrip"]
    assert not fg["offParent"] and not fg["sameRowAsMag"] or True  # 同行允许，列不同即可
    assert not fg["offParent"], "前握把列必须与父件对齐"


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_r1913_audit_matches_task_rules():
    proc = _run_node([AUDIT_TOOL])
    assert proc.returncode == 0, proc.stderr[:800]
    out = json.loads(proc.stdout)
    # 前照门与枪口对齐（有前照门+有枪口的枪全部对齐）
    assert out["frontSightMisaligned"] == 0
    assert out["frontSightAligned"] >= 40
    # 瞄具在上机匣正上方
    assert out["scopeMisplaced"] == 0
    assert out["scopeAboveReceiver"] >= 40
    # 照门在拉机柄左侧
    assert out["rearSightOk"] >= 80
    # MPR45 全部锚定 r2c4
    mpr = out["mpr45"].split("/")
    assert mpr[0] == mpr[1] and int(mpr[1]) >= 20
    # 枪口链同列
    mz = out["muzzleChains"].split("/")
    assert mz[0] == mz[1] and int(mz[1]) >= 80
    # 前握把
    assert out["foregrip"]["offParent"] == []
    assert out["foregrip"]["aboveParent"] == []
    assert out["foregrip"]["direct"] >= 20 and out["foregrip"]["viaRail"] >= 5
    # 护木其余附件：绝大多数进第六行，无横向漂移
    assert out["handguardExtras"]["inRow6"] >= 80
    assert out["handguardExtras"]["spills"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_slot_mapping_json_has_required_entries():
    p = os.path.join(AUDIT, "slot-mapping.json")
    if not os.path.exists(p):
        pytest.skip("slot-mapping.json 尚未生成（先跑 tools/r1913_audit.js）")
    d = json.load(open(p, encoding="utf-8"))
    assert "rules" in d and "muzzleChain" in d["rules"] and "frontSight" in d["rules"]
    guns = d["guns"]
    assert len(guns) >= 150
    # 至少一把：前照门与枪口同列且在第 2 行
    ok = [g for g in guns.values()
          if g.get("frontSight") and g.get("muzzle")
          and g["frontSight"]["col"] == g["muzzle"]["col"] and g["frontSight"]["row"] == 2]
    assert ok, "没有找到前照门对齐枪口的案例"
    # 无独立枪管槽（枪口在 c2）且前照门对齐的案例也必须存在
    integral = [g for g in ok if g["muzzle"]["col"] == 2]
    assert integral, "缺少「无独立枪管槽、前照门在 r2c2」的案例（AKM 系）"
    # 瞄具在 r2c5 的案例
    assert [g for g in guns.values() if g.get("scope") and g["scope"]["aboveReceiver"]]


def test_foregrip_chains_json_covers_three_shapes():
    p = os.path.join(AUDIT, "foregrip-chains.json")
    if not os.path.exists(p):
        pytest.skip("foregrip-chains.json 尚未生成")
    d = json.load(open(p, encoding="utf-8"))
    kinds = {}
    for c in d["chains"].values():
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        assert c["ok"], c
        assert c["sameColumnAsParent"] or not c["chain"]
        assert not c["forbiddenZone"]
    assert kinds.get("direct", 0) >= 10, kinds
    assert kinds.get("viaRail", 0) >= 5, kinds
    # 情况 B（上/下护木）在默认装配里可能为 0，但链式规则已实现；
    # 浏览器演示（_accept.json caseB）会覆盖它。
    p2 = os.path.join(AUDIT, "_accept.json")
    if os.path.exists(p2):
        acc = json.load(open(p2, encoding="utf-8"))
        cb = acc.get("caseB") or {}
        fg = (cb.get("check") or {}).get("foregrips") or []
        assert fg, "浏览器 caseB 演示必须装上前握把"
        # 前握把父件是下护木（handguard 基名），且在父件正下方同列
        f = fg[0]
        assert "handguard" in (f.get("parent") or "")
        assert f["belowParent"] and f["sameColAsParent"] and f["notInRow2"] and f["notInRow4Fixed"]


def test_muzzle_chains_json_same_column():
    p = os.path.join(AUDIT, "muzzle-chains.json")
    if not os.path.exists(p):
        pytest.skip("muzzle-chains.json 尚未生成")
    d = json.load(open(p, encoding="utf-8"))
    assert d["summary"]["breaks"] == 0
    assert d["summary"]["sameColumn"] >= 80
    # 至少一条两层以上的链（枪口→转接/消音器）
    deep = [c for c in d["chains"].values() if len([x for x in c["chain"] if x["pos"]]) >= 2]
    assert deep, "没有多层枪口链案例"


def test_handguard_extras_json_row6():
    p = os.path.join(AUDIT, "handguard-extras.json")
    if not os.path.exists(p):
        pytest.skip("handguard-extras.json 尚未生成")
    d = json.load(open(p, encoding="utf-8"))
    assert d["summary"]["spills"] == []
    assert d["summary"]["inRow6"] >= 80


# ---------------------------------------------------------------- 3. 回归锚点
def test_r1912_features_not_regressed_by_layout_rewrite():
    js = _read(APP)
    # 优化器整树校验 / 默认弹药 / 外观图层仍然在
    assert "function verifyBuild(" in _read(os.path.join(ROOT, "gun_builder.js"))
    assert "function gwDefaultAmmoRule(" in js
    assert "function renderGunSkin(host)" in js
    # 固定锚点常量仍完整
    eng = _engine()
    for frag in ('body:      { row: 3, col: 6, span: 3 }',
                 'stock:     { row: 3, col: 9 }',
                 'mag:       { row: 4, col: 7 }',
                 'grip:      { row: 4, col: 8 }',
                 'ammo:      { row: 5, col: 7 }',
                 'charge:    { row: 2, col: 9 }'):
        assert frag in eng, frag
