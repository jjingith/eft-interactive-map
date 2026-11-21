# -*- coding: utf-8 -*-
"""R19.14 画布显示语义：六行坐标系稳定 + 不存在的槽位不渲染占位。

两条硬规则（本文件同时锁住）：
  1. 六行九列坐标系稳定：行轨道固定 6 条且有非零最小高度（空行不塌缩）。
  2. 不存在真实槽位的坐标**不渲染任何可见格框/占位**；真实空槽必须保留可交互。

背景：
  R19.13.1 曾为 54 个空坐标画 .gw-cell-ghost 占位格——视觉上可数出网格，
  但用户明确要求「不存在的槽位位置不显示任何格框、背景、占位卡片」。
  行轨道存在 ≠ 每个坐标都要画一个可见格子。
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
HTML = os.path.join(ROOT, "index.html")
AUDIT = os.path.join(ROOT, "docs", "r19.14-layout-changes")
SIX = os.path.join(ROOT, "docs", "r19.14-six-rows")


def _read(p: str) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _grid_block(css: str) -> str:
    i = css.index(".gun-workbench .gw-canvas.gw-grid {")
    return css[i:css.index("}", i) + 1]


# ---------------------------------------------------------------- 1. 行轨道
def test_rows_six_with_nonzero_min_height():
    """6 行固定 + 非零最小行高：空行不塌缩，但不等于要画占位格。"""
    grid = _grid_block(_read(CSS))
    assert "repeat(var(--gw-cols, 9)" in grid
    assert "repeat(var(--gw-rows, 6)" in grid, "行轨道必须固定为 6"
    assert "minmax(var(--gw-row-min" in grid, "空行必须有最小行高"
    assert "minmax(0, auto))" not in grid, "minmax(0, auto) 会让空行塌缩成 0 高"


# ------------------------------------------------- 2. 不存在的槽位不渲染
def test_no_visible_placeholder_for_nonexistent_slots():
    """无真实槽位的坐标：不得渲染格框/占位卡片/背景元素。"""
    js = _read(APP)
    css = _read(CSS)
    render = js[js.index("function renderGunTree() {"):js.index("function renderGunFocus(")]

    # 占位 DOM 循环必须不存在
    assert "gw-cell-ghost" not in js, "不得再为不存在的槽位渲染占位格"
    assert "data-ghost" not in render, "画布渲染路径不得输出占位标记"
    assert "gw-cell-ghost" not in css, "不得保留占位格可见样式"

    # 双层循环刷格位的写法不得回来（针对画布渲染）
    assert not re.search(r"for \(var r = 1; r <= rows; r\+\+\)", render), \
        "renderGunTree 不应按行列刷占位格"

    # 真实空槽样式必须保留
    assert "gw-part-empty" in css, "真实空槽样式被误删"
    assert "gw-part-empty" in js, "真实空槽类名被误删"


def test_real_empty_slots_still_interactive():
    """真实存在但未安装配件的槽位：空槽卡片仍可点、可 hover、可右键。"""
    js = _read(APP)
    card = js[js.index("function gwPartCard(path)"):js.index("function gwDrawLinks(")]
    assert 'card.className = "gw-part"' in card
    assert "gw-part-empty" in card
    assert "card.addEventListener(\"click\"" in card
    assert "card.addEventListener(\"contextmenu\"" in card
    assert "card.addEventListener(\"mouseenter\"" in card
    # 空槽判定来自槽位树，不是「当前有没有配件」
    assert "installedId ? \"\" : \" gw-part-empty\"" in card
    assert "g.slots.nodes[path]" in card, "必须按槽位树取节点"


# ------------------------------------------------- 3. 坐标系与锚点不漂移
def test_anchor_coords_unchanged():
    """固定槽位坐标不得被本次修订改动。"""
    eng = _read(APP)
    eng = eng[eng.index("var GW_GRID_ROWS = 6"):eng.index("function renderGunTree()")]
    for frag in ("body:      { row: 3, col: 6, span: 3 }",
                 "stock:     { row: 3, col: 9 }",
                 "mag:       { row: 4, col: 7 }",
                 "grip:      { row: 4, col: 8 }",
                 "ammo:      { row: 5, col: 7 }",
                 "charge:    { row: 2, col: 9 }"):
        assert frag in eng, "锚点被改动：" + frag
    assert "GW_GRID_ROWS = 6" in eng and "GW_GRID_COLS = 9" in eng


def test_build_marker_and_cache_bust_synced():
    """AM_BUILD 与 index.html 资源版本必须同步（防旧缓存）。"""
    js = _read(APP)
    html = _read(HTML)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m, "缺 AM_BUILD"
    assert ("?v=" + m.group(1).lower()) in html, "index.html 资源版本未与 AM_BUILD 同步"


# ------------------------------------------------- 4. 浏览器实测审计
def test_browser_audit_no_phantom_cells():
    """真实浏览器：无真实槽位坐标零可见 DOM；真实空槽仍可交互。"""
    p = os.path.join(AUDIT, "slots-visibility.json")
    if not os.path.exists(p):
        raise AssertionError("缺 %s（请先跑 python tools/r1915_accept.py）" % p)
    d = json.load(open(p, encoding="utf-8"))
    assert d.get("build", "").find("R19.14") >= 0, d.get("build")

    cases = d["cases"]
    assert len(cases) >= 5
    for key, c in cases.items():
        assert c.get("phantomCount") == 0, "%s 出现占位格: %s" % (key, c.get("phantoms"))
        assert c.get("rowCount") == 6 and c.get("colCount") == 9, key
        heights = c.get("rowHeights") or []
        assert len(heights) == 6 and min(heights) >= 24, "%s 行高塌缩: %s" % (key, heights)
        # 真实空槽必须仍在（除非该枪全部装满）
        if c.get("realEmptySlots") is not None:
            assert c["realEmptySlotsVisible"] == c["realEmptySlots"], \
                "%s 真实空槽未全部可见: %s/%s" % (key, c.get("realEmptySlotsVisible"), c["realEmptySlots"])
            assert c.get("emptySlotInteractive") is True, "%s 空槽不可交互" % key
        # 坐标不漂移
        assert c.get("coordDrift") == 0, "%s 坐标漂移: %s" % (key, c.get("coordDriftDetail"))


def test_browser_audit_top_expansion_no_phantom():
    """MPR45 / Nightforce 多层上置展开时，空坐标仍不画格框。"""
    p = os.path.join(AUDIT, "slots-visibility.json")
    if not os.path.exists(p):
        raise AssertionError("缺 %s" % p)
    d = json.load(open(p, encoding="utf-8"))
    top = d.get("topExpansion") or {}
    for key in ("mpr45", "nightforce"):
        t = top.get(key)
        assert t, "缺 %s 顶部展开用例" % key
        assert t.get("phantomCount") == 0, "%s 顶部展开出现占位格" % key
        assert t.get("rowHeights") and min(t["rowHeights"]) >= 24


def test_browser_audit_preset_and_switch_consistent():
    """安装/卸载/切枪/加载预设后，空槽显示与真实槽位树一致。"""
    p = os.path.join(AUDIT, "slots-visibility.json")
    if not os.path.exists(p):
        raise AssertionError("缺 %s" % p)
    d = json.load(open(p, encoding="utf-8"))
    flow = d.get("flow") or {}
    for key in ("afterInstall", "afterUninstall", "afterGunSwitch", "afterPreset"):
        f = flow.get(key)
        assert f, "缺 %s 流程测量" % key
        assert f.get("phantomCount") == 0, "%s 出现占位格" % key
        assert f.get("slotCount") == f.get("treeSlotCount"), \
            "%s DOM 槽位数与槽位树不一致: %s vs %s" % (key, f.get("slotCount"), f.get("treeSlotCount"))
