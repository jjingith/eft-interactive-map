# -*- coding: utf-8 -*-
"""R19.14.2 Nightforce 直接槽位修正 + 瞄具/底座专项审计。

数据层（真实槽位树）与画布层必须一致：该底座直接槽位严格 2 个。
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
FETCH = os.path.join(ROOT, "tools", "fetch_data.py")
AUDIT = os.path.join(ROOT, "docs", "r19.14-layout-changes", "nightforce-slot-audit")
MOUNT = "5aa66c72e5b5b00016327c93"
SCOPE_34 = "5aa66c90e5b5b00016327c96"
ONE_X = "5aa66c9ce5b5b00015693125"
DUP_A = "5aa66cabe5b5b055d0630d82"
DUP_B = "5aa66cb7e5b5b0214e506e99"
ATACR = "5aa66be6e5b5b0214e506e97"


def _read(p: str) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _items() -> dict:
    return json.load(open(ITEMS, encoding="utf-8"))["items"]


# --------------------------------------------------------- 1. 数据层槽位数量
def test_mount_has_exactly_two_direct_slots():
    it = _items()[MOUNT]
    slots = it["slots"]
    assert len(slots) == 2, "Nightforce Multimount 必须恰好 2 个直接槽位，实际 %d" % len(slots)
    assert [s["id"] for s in slots] == [SCOPE_34, ONE_X]
    assert slots[0]["sid"] == "mod_scope_000"
    assert slots[1]["sid"] == "mod_scope_001"
    # 重复节点必须从数据里移除，而不是只在 UI 隐藏
    ids = {s["id"] for s in slots}
    assert DUP_A not in ids and DUP_B not in ids
    assert slots[0].get("fix") == "in-game-confirmed"


def test_two_slots_have_correct_purpose_and_allow():
    it = _items()[MOUNT]
    slots = {s["id"]: s for s in it["slots"]}
    # 34mm 光学槽：allow 全部是 34mm 光学瞄具的代表 ATACR 在内
    assert ATACR in slots[SCOPE_34]["allow"]
    assert "34" in slots[SCOPE_34]["label"] or slots[SCOPE_34]["label"] == "瞄准镜"
    # 单倍槽：允许 1 倍反射瞄具与微型底座
    one = slots[ONE_X]
    assert "单倍" in one["label"], one["label"]
    names = [( _items()[a].get("n") or "") for a in one["allow"]]
    assert any("PK-06" in n for n in names), "单倍槽应允许 1 倍反射瞄具"
    assert any("瞄具基座" in n for n in names), "单倍槽应允许单倍瞄具底座"
    # 两个槽不能是同一份 allow（说明不是重复节点）
    assert slots[SCOPE_34]["allow"] != one["allow"]


def test_build_pipeline_has_correction_table():
    src = _read(FETCH)
    assert "OPTIC_SLOT_CORRECTIONS" in src
    assert MOUNT in src
    assert "def _apply_slot_correction(" in src
    assert '_apply_slot_correction(out, item_id)' in src
    # R19.19 升级：修正表挂接点随实现演进（现在是 out = …），R19.18/19 两张表都必须挂上
    assert "R1918_ITEM_SLOT_FIXES" in src and "R1919_ITEM_SLOT_FIXES" in src


def test_layout_dedupes_cells_and_keeps_two_children():
    src = _read(APP)
    assert "同一槽位路径只允许落一次" in src
    assert "if (cells[ci].path === path) { return cells[ci]; }" in src
    # 子槽向上规则
    assert "function placeDescendantsUpward(" in src
    assert "placeDescendantsUpward(kk, sr, scc);" in src


# ------------------------------------------------------------- 2. 审计产物
def test_nightforce_direct_slots_json():
    p = os.path.join(AUDIT, "nightforce-direct-slots.json")
    assert os.path.exists(p), "缺 nightforce-direct-slots.json"
    d = json.load(open(p, encoding="utf-8"))
    assert d["itemId"] == MOUNT
    assert d["directSlotCount"] == 2
    assert [s["slotId"] for s in d["slots"]] == [SCOPE_34, ONE_X]
    assert d["slots"][0]["purpose"] == "34mm 光学瞄准镜槽"
    assert "单倍" in d["slots"][1]["purpose"]
    assert len(d["removedSlots"]) == 2


def test_nightforce_tree_before_after_json():
    p = os.path.join(AUDIT, "nightforce-tree-before-after.json")
    assert os.path.exists(p)
    d = json.load(open(p, encoding="utf-8"))
    assert d["before"]["upstreamSlotCount"] == 4, "修复前必须有 4 槽的上游证据"
    assert d["after"]["declaredSlotCount"] == 2
    assert d["after"]["treeDirectChildren"] == 2
    assert d["checks"] == {"declaredEqualsTwo": True, "treeEqualsTwo": True,
                           "layoutDirectEqualsTwo": True}


def test_optic_slot_audit_json():
    p = os.path.join(AUDIT, "optic-slot-audit.json")
    assert os.path.exists(p)
    d = json.load(open(p, encoding="utf-8"))
    assert d["summary"]["opticFamilyItems"] >= 500
    nf = [x for x in d["items"] if x["id"] == MOUNT]
    assert nf and nf[0]["verified"] == "confirmed-2-slots"
    assert nf[0]["declaredDirectSlots"] == 2
    assert nf[0]["treeDirectChildren"] == 2
    assert nf[0]["layoutRenderedDirectCells"] == 2
    # 其他条目必须是 pending，不能把未实测的规则当成已完成
    pending = [x for x in d["items"] if x["verified"] == "pending"]
    assert len(pending) == d["summary"]["pendingVerification"]
    assert len(pending) >= 500


def test_optic_slot_issues_json():
    p = os.path.join(AUDIT, "optic-slot-issues.json")
    assert os.path.exists(p)
    d = json.load(open(p, encoding="utf-8"))
    fixed = [x for x in d.get("fixed", []) if x["id"] == MOUNT]
    assert fixed and fixed[0]["status"] == "fixed"
    assert fixed[0]["before"]["declaredDirectSlots"] == 4
    assert fixed[0]["after"]["declaredDirectSlots"] == 2
    assert fixed[0]["evidence"] == "in-game-confirmed"
    # 布局重复格缺陷也必须留证据
    assert any(x["kind"] == "layout-duplicate-cell" for x in d.get("fixed", []))
    # 其余不一致必须是可解释原因，不能留空
    for m in d["mismatchDeclaredVsTree"]:
        assert m.get("reason"), m


# --------------------------------------------------------- 3. 浏览器实测
def test_browser_two_slots_and_directions():
    p = os.path.join(AUDIT, "browser-check.json")
    assert os.path.exists(p), "缺 browser-check.json（先跑 tools/r1917_accept.py）"
    d = json.load(open(p, encoding="utf-8"))
    assert "R19.14.2" in (d.get("build") or "")
    assert "v=r19.14.2" in (d.get("appSrc") or "")

    ms = d["mountSlots"]
    assert ms["directSlotCount"] == 2, ms["slots"]
    assert ms["noLegacy002003"] is True
    assert {s["sid"] for s in ms["slots"]} == {"mod_scope_000", "mod_scope_001"}
    assert ms["phantomCount"] == 0

    wb = d["withBase"]
    assert wb["directSlotCount"] == 2
    assert wb["opticsAboveMount"] is True, "34mm 光学槽必须在底座上方"
    assert wb["onexRightOfOptics"] is True, "单倍槽必须在 34mm 槽右侧"
    assert wb["childAboveBase"] is True, "单倍底座的下级瞄具槽必须在底座正上方"
    assert wb["topPad"] == 1 and wb["rows"] == 7

    ext = d["extension"]
    assert ext["rows"] == 7 and ext["topPad"] == 1
    assert ext["afterRemoveRows"] == 6 and ext["afterRemoveTopPad"] == 0


def test_browser_regressions_intact():
    p = os.path.join(AUDIT, "browser-check.json")
    d = json.load(open(p, encoding="utf-8"))
    assert d["bad"]["atR4C6"] is True
    assert d["mpr45"]["allSameCol"] is True
    assert d["phantom"]["phantomCount"] == 0
    assert d["phantom"]["rows"] == 6
    preset = d["flow"]["afterPreset"]
    assert preset["hasLegacy002003"] is False
    assert preset["slotCount"] == preset["treeSlots"]
    # 枪匠大师生成后同样不得出现多余槽位，且挂载点仍只有 2 个直接子槽
    forge = d["flow"]["afterForge"]
    assert forge["generated"] is True
    assert forge["hasLegacy002003"] is False
    assert forge["slotCount"] == forge["treeSlots"]
    assert len(forge["mountChildren"]) == 2, forge["mountChildren"]
    assert forge["phantomCount"] == 0
    # 枪匠大师生成后同样不得出现多余槽位，且挂载点仍只有 2 个直接子槽
    forge = d["flow"]["afterForge"]
    assert forge["generated"] is True
    assert forge["hasLegacy002003"] is False
    assert forge["slotCount"] == forge["treeSlots"]
    assert len(forge["mountChildren"]) == 2, forge["mountChildren"]
    assert forge["phantomCount"] == 0


# ------------------------------------------------- 4. 全枪去重（node 实测）
@pytest.mark.skipif(subprocess.run([sys.executable, "-c", "import shutil,sys;sys.exit(0 if shutil.which('node') else 1)"]).returncode != 0,
                    reason="需要 node")
def test_no_duplicate_cell_paths_all_guns():
    proc = subprocess.run(["node", os.path.join(ROOT, "tools", "r1917_unique.js")],
                          capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    assert d["guns"] >= 150
    assert d["duplicateCount"] == 0, d["duplicates"][:3]
    assert d["nightforce"] == {"declared": 2, "treeKids": 2, "layoutKids": 2}
