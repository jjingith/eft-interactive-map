# -*- coding: utf-8 -*-
"""R19.14.1 布局规则：B.A.D. r4c6 / MPR45 竖直链 / Nightforce 主链+侧分支 / 顶部扩展 / 外观隐藏。

判定只认真实槽位树与浏览器实测数据（docs/r19.14-layout-changes/layout-rules.json）。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
AUDIT = os.path.join(ROOT, "docs", "r19.14-layout-changes")


def _read(p: str) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _engine() -> str:
    js = _read(APP)
    return js[js.index("var GW_GRID_ROWS = 6"):js.index("function renderGunSkin(")]


# ------------------------------------------------------------ 1. B.A.D. 锚点
def test_bad_anchor_is_r4c6():
    eng = _engine()
    assert "bad:         { row: 4, col: 6 }" in eng, "B.A.D 锚点必须是 r4c6"
    assert "reserve(GW_ANCHOR.bad);" in eng, "B.A.D 锚点格必须预留"
    assert "gwIsBadSlot(nodes[p])" in eng, "B.A.D 判定必须基于真实 allow 数据"
    assert "take(wantRow, GW_ANCHOR.bad.col, p, true)" in eng


# --------------------------------------------------------- 2. MPR45 竖直链
def test_mpr45_children_stack_upward_same_column():
    eng = _engine()
    assert "var railTop = 1;" in eng
    assert "take(railTop, 4, k, true)" in eng, "MPR45 子槽必须固定在第 4 列向上"
    assert "for (var c = 3; c >= 1; c--)" not in eng, "不得横向挪列规避空间不足"
    assert "GW_TOP_MAX" in eng, "顶部扩展上限必须显式定义"


# ------------------------------------------- 3. Nightforce 主链 + 侧分支
def test_scope_main_chain_and_side_branch_split():
    eng = _engine()
    assert "var isPureScope = function (k)" in eng, "必须按 allow 是否全为纯瞄具区分主链"
    assert 'String(ar.pt || "") !== "Scope"' in eng
    assert "var mainKids = kids.filter(isPureScope);" in eng
    assert "var sideKids = kids.filter(function (k) { return !isPureScope(k); });" in eng
    # 主链沿 c5 向上；侧分支从 c6 起
    assert "take(topCursor, 5, k, true)" in eng
    assert "for (var scc = 6; scc <= GW_GRID_COLS" in eng


# ------------------------------------------------------- 4. 顶部扩展收口
def test_top_extension_shifts_rows_and_reports():
    eng = _engine()
    assert "var topPad = minRow < 1 ? (1 - minRow) : 0;" in eng
    assert "var totalRows = GW_GRID_ROWS + topPad;" in eng
    assert "rows: totalRows" in eng and "topPad: topPad" in eng
    assert "body: { row: GW_ANCHOR.body.row + topPad" in eng, "枪身必须随扩展整体下移"
    assert "ammoRow: GW_ANCHOR.ammo.row + topPad" in eng


def test_base_canvas_still_six_by_nine():
    eng = _engine()
    assert "GW_GRID_ROWS = 6" in eng and "GW_GRID_COLS = 9" in eng
    css = _read(CSS)
    grid = css[css.index(".gun-workbench .gw-canvas.gw-grid {"):]
    grid = grid[:grid.index("}") + 1]
    assert "repeat(var(--gw-rows, 6)" in grid
    assert "minmax(var(--gw-row-min" in grid


# ------------------------------------------------------- 5. 外观合成已隐藏
def test_live_appearance_hidden_but_implementation_kept():
    js = _read(APP)
    assert "var GW_SKIN_ENABLED = false;" in js, "外观合成默认关闭"
    assert "if (GW_SKIN_ENABLED) { renderGunSkin(shot); }" in js
    assert "function renderGunSkin(host)" in js, "实现必须保留"


# ------------------------------------------------------- 6. 浏览器实测审计
def test_browser_audit_layout_rules():
    p = os.path.join(AUDIT, "layout-rules.json")
    if not os.path.exists(p):
        raise AssertionError("缺 %s（先跑 tools/r1916_accept.py）" % p)
    d = json.load(open(p, encoding="utf-8"))

    # 资源版本
    assert "R19.14.1" in (d.get("build") or ""), d.get("build")
    assert "v=r19.14.1" in (d.get("appSrc") or ""), d.get("appSrc")

    # B.A.D. 必须在 r4c6
    bad = d.get("bad") or {}
    assert bad.get("atR4C6") is True, bad
    for c in bad.get("cells") or []:
        assert c["row"] == 4 and c["col"] == 6, c

    # MPR45 三层：同列向上、顶部扩展
    m = d.get("mpr45") or {}
    assert m.get("allSameCol") is True, m.get("chain")
    assert m.get("strictlyUpward") is True, m.get("chain")
    assert len(m.get("chain") or []) >= 3, m.get("chain")
    assert (m.get("rows") or 0) == 7, "三层链必须触发顶部扩展为 7 行"
    assert (m.get("topPad") or 0) == 1
    assert m.get("phantomCount") == 0

    # 移除后收缩回 6 行
    c = d.get("contraction") or {}
    assert c.get("shrunk") is True, c
    assert (c.get("rowsAfter") or 0) == 6 and (c.get("topPadAfter") or 0) == 0

    # Nightforce 主链 + 侧分支
    nf = d.get("nightforce") or {}
    assert nf.get("hasMainChain") is True, nf
    assert nf.get("hasSideBranch") is True, nf
    main = nf.get("mainChainAbove") or []
    assert main and main[0]["col"] == 5, "主光学链必须在 c5"
    assert "ATACR" in (main[0].get("item") or ""), main
    for b in nf.get("sideBranchesRight") or []:
        assert b["col"] > 5, "侧分支必须在主链右侧"

    # 占位 / 空槽 / 外观
    ph = d.get("phantom") or {}
    assert ph.get("phantomCount") == 0, ph.get("phantoms")
    assert ph.get("rows") == 6
    assert min(ph.get("rowHeights") or [0]) >= 24
    assert ph.get("emptySlotClickable") is True

    sk = d.get("skin") or {}
    assert sk.get("skinPresent") is False, sk
    assert sk.get("skinTag") is None, sk
    assert sk.get("hasBodyCell") is True and sk.get("bodyRow") == 3
